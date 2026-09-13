"""MockSimulator — STRICTLY for unit/interface/plumbing tests (blueprint §1, PROBLEM 1).

The MOCK environment produces synthetic observations and synthetic legal actions.
It is UNAVAILABLE for gameplay evidence: provenance.assert_gameplay_evidence()
rejects any EvaluationResult carrying environment_type 'MOCK'.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import DecisionOutcome, FailureCategory, FailureRecord
from .cabt_types import CabtObservation, CabtState
from .verified_adapter import BaseBattle, SimulatorStartData


@dataclass
class _MockSelect:
    type: int
    context: int
    minCount: int
    maxCount: int
    option: list[dict[str, Any]]
    deck: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "context": self.context,
            "minCount": self.minCount,
            "maxCount": self.maxCount,
            "option": list(self.option),
            "deck": self.deck,
        }


class MockSimulator(BaseBattle):
    """Interface-compatible stand-in. environment_type is always MOCK."""

    ENVIRONMENT_TYPE = "MOCK"

    def __init__(self, deck0: list[int], deck1: list[int], seed: int = 0, *, fixture_script: str = ""):
        rng = random.Random(seed)
        if len(deck0) != 60 or len(deck1) != 60:
            raise ValueError("mock decks must be 60 cards")
        self._rng = rng
        self._deck0 = list(deck0)
        self._deck1 = list(deck1)
        self._obs: dict[str, Any] = {}
        self._finished = False
        self._step = 0
        self._script: list[dict] = []
        if fixture_script:
            script = Path(fixture_script)
            if script.exists():
                blocks = json.loads(script.read_text(encoding="utf-8"))
                self._script = blocks if isinstance(blocks, list) else [blocks]

    def start(self, deck0: list[int] | None = None, deck1: list[int] | None = None) -> tuple[dict[str, Any], SimulatorStartData]:
        d0 = deck0 or self._deck0
        d1 = deck1 or self._deck1
        if len(d0) != 60 or len(d1) != 60:
            return {}, SimulatorStartData(errorPlayer=0)
        self._obs = self._fixture_step("start")
        return self._obs, SimulatorStartData(errorPlayer=-1)

    def select(self, indices: list[int]) -> dict[str, Any]:
        if isinstance(indices, (int, float)):
            indices = [indices]
        if not isinstance(indices, list) or not all(isinstance(i, int) for i in indices):
            raise ValueError("select_list is not list[int]")
        n = len(self._obs.get("select", {}).get("option", [])) if self._obs.get("select") else 0
        if any(i < 0 or i >= n for i in indices):
            raise IndexError("mock invalid option index")
        self._obs = self._fixture_step("select")
        return self._obs

    def _fixture_step(self, kind: str) -> dict[str, Any]:
        if self._script and self._step < len(self._script):
            step = self._script[self._step]
            self._step += 1
            return step
        self._step += 1
        your = self._step % 2
        # A tiny synthetic MAIN-turn structure. Not a real rules step-flow.
        options = [
            {"type": 14, "index": None},  # END
            {"type": 7, "index": 0},      # PLAY
            {"type": 8, "area": 4, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},  # ATTACH
            {"type": 13, "attackId": 0},  # ATTACK
        ]
        if self._step == 1:
            sel = _MockSelect(
                type=9, context=41, minCount=1, maxCount=1,
                option=[{"type": 1}, {"type": 2}],
            )
        elif self._step <= 3:
            sel = _MockSelect(type=1, context=1, minCount=1, maxCount=1, option=[{"type": 3, "area": 2, "index": 0, "playerIndex": your}])
        else:
            sel = _MockSelect(type=0, context=0, minCount=1, maxCount=1, option=options)
        self._finished = self._step > 30
        return {
            "select": sel.to_dict(),
            "logs": [],
            "current": {
                "turn": self._step // 2,
                "turnActionCount": 0,
                "yourIndex": your,
                "firstPlayer": 0,
                "supporterPlayed": False,
                "stadiumPlayed": False,
                "energyAttached": False,
                "retreated": False,
                "result": (0 if self._finished else -1),
                "stadium": [],
                "looking": None,
                "players": [
                    {
                        "active": [None], "bench": [], "benchMax": 5, "deckCount": 50,
                        "discard": [], "hand": None, "handCount": 4,
                        "prize": [None] * 6, "poisoned": False, "burned": False,
                        "asleep": False, "paralyzed": False, "confused": False,
                    }
                    for _ in range(2)
                ],
            },
        }

    def finish(self) -> None:
        self._finished = True

    def observation(self) -> CabtObservation:
        return CabtObservation.from_dict(self._obs)

    def visualize(self) -> str:
        return json.dumps(self._obs)

    @property
    def pending(self) -> bool:
        return not self._finished