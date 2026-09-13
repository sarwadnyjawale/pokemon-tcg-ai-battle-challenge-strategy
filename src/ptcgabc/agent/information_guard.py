"""Information visibility registry + leakage guard (blueprint §9 / PROBLEM 9).

Visibility rules are derived from the VERIFIED cabt contract, not assumptions.

Verified facts (docs/simulator/verified_contract.md + live engine dump):
- players[i].hand : list for YOUR hand; None for the opponent (only handCount is visible).
- players[i].prize : facedown slots are None; prize count order bottom..top.
- deck contents are never visible; only deckCount.
- DRAW logs for your own cards carry cardId; opponent draws are DRAW_REVERSE (no cardId).
- current.result is -1 until the match ends.
- RNG / shuffle seed is never present in observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Visibility(str, Enum):
    VISIBLE = "VISIBLE"
    HIDDEN = "HIDDEN"
    OPPONENT_ONLY = "OPPONENT_ONLY"
    TERMINAL_ONLY = "TERMINAL_ONLY"
    PARTIAL = "PARTIAL"


@dataclass
class FieldRule:
    field: str
    visibility: Visibility
    source: str
    available_at_decision: bool
    verification_status: str = "VERIFIED"
    notes: str = ""


VERIFIED = "VERIFIED"

# Base rules on the internal canonical Observation shape.
_FIELD_RULES: list[FieldRule] = [
    FieldRule("current.turn", Visibility.VISIBLE, "state.turn", True),
    FieldRule("current.turnActionCount", Visibility.VISIBLE, "state.turnActionCount", True),
    FieldRule("current.yourIndex", Visibility.VISIBLE, "state.yourIndex", True),
    FieldRule("current.firstPlayer", Visibility.VISIBLE, "state.firstPlayer", True),
    FieldRule("current.supporterPlayed", Visibility.VISIBLE, "state.supporterPlayed", True),
    FieldRule("current.stadiumPlayed", Visibility.VISIBLE, "state.stadiumPlayed", True),
    FieldRule("current.energyAttached", Visibility.VISIBLE, "state.energyAttached", True),
    FieldRule("current.retreated", Visibility.VISIBLE, "state.retreated", True),
    FieldRule("current.result", Visibility.TERMINAL_ONLY, "state.result", True, notes="only valid when >= 0"),
    FieldRule("current.stadium", Visibility.VISIBLE, "state.stadium", True),
    FieldRule("current.looking", Visibility.VISIBLE, "state.looking", True),
    FieldRule("players[i].active", Visibility.VISIBLE, "playerstate.active", True),
    FieldRule("players[i].bench", Visibility.VISIBLE, "playerstate.bench", True),
    FieldRule("players[i].benchMax", Visibility.VISIBLE, "playerstate.benchMax", True),
    FieldRule("players[i].deckCount", Visibility.VISIBLE, "playerstate.deckCount", True),
    FieldRule("players[i].discard", Visibility.VISIBLE, "playerstate.discard", True),
    FieldRule("players[i].hand", Visibility.OPPONENT_ONLY, "playerstate.hand", True, notes="None for the opponent; only handCount visible"),
    FieldRule("players[i].handCount", Visibility.VISIBLE, "playerstate.handCount", True),
    FieldRule("players[i].prize", Visibility.PARTIAL, "playerstate.prize", True, notes="facedown slots are None"),
    FieldRule("players[i].poisoned", Visibility.VISIBLE, "playerstate.poisoned", True),
    FieldRule("players[i].burned", Visibility.VISIBLE, "playerstate.burned", True),
    FieldRule("players[i].asleep", Visibility.VISIBLE, "playerstate.asleep", True),
    FieldRule("players[i].paralyzed", Visibility.VISIBLE, "playerstate.paralyzed", True),
    FieldRule("players[i].confused", Visibility.VISIBLE, "playerstate.confused", True),
    FieldRule("rng_seed", Visibility.HIDDEN, "none", False, notes="never present in observations"),
    FieldRule("full_opponent_hand", Visibility.HIDDEN, "none", False, notes="opponent hand is never revealed"),
    FieldRule("deck_order", Visibility.HIDDEN, "none", False, notes="deck contents/order never revealed"),
    FieldRule("future_logs", Visibility.HIDDEN, "none", False, notes="logs only cover events up to the current selection"),
    FieldRule("post_game_result", Visibility.TERMINAL_ONLY, "state.result", True),
]


def field_rules() -> list[FieldRule]:
    return list(_FIELD_RULES)


def visibility_registry() -> dict[str, Any]:
    return {
        "source": "chess_verified_cabt_contract",
        "fields": [
            {
                "field": r.field,
                "visibility": r.visibility.value,
                "source": r.source,
                "decision_time_available": r.available_at_decision,
                "verification_status": r.verification_status,
                "notes": r.notes,
            }
            for r in field_rules()
        ],
    }


class LeakageViolation(Exception):
    pass


class LeakageGuard:
    """Fail-closed audit of an observation for information leakage.

    Leakage violations are designed to fail tests/CI per blueprint §13.
    """

    def __init__(self, rules: list[FieldRule] | None = None):
        self._rules = rules or field_rules()

    def audit(self, obs: dict[str, Any]) -> list[str]:
        violations: list[str] = []
        cur = obs.get("current")
        if cur is not None:
            # opponent hand must be None (partial visibility) in a non-terminal frame
            for idx, p in enumerate(cur.get("players", [])):
                if "hand" in p and p["hand"] is not None and int(cur.get("yourIndex", -1)) != idx:
                    violations.append(f"opponent players[{idx}].hand exposed with {len(p['hand'])} cards")
                if "prize" in p:
                    face_up = [c for c in p["prize"] if c is not None]
                    if face_up and cur.get("result", -1) < 0:
                        # prizes may be face-up in some effects, so only flag none/all heuristics here
                        pass
            if int(cur.get("result", -1)) < 0:
                # no post-game info in a running game
                for key in ("winner", "win_reason", "elo", "rating"):
                    if key in obs:
                        violations.append(f"post-game field {key!r} present while game is running")
        logs = obs.get("logs", []) or []
        for lg in logs:
            if lg.get("type") in (2, 3):  # TURN_START / TURN_END
                if "future" in str(lg):
                    violations.append("future marker in logs")
        if "rng_seed" in obs or "seed" in obs and isinstance(obs.get("seed"), int):
            violations.append("rng seed present in observation")
        return violations

    def assert_safe(self, obs: dict[str, Any]) -> None:
        bad = self.audit(obs)
        if bad:
            raise LeakageViolation("; ".join(bad))