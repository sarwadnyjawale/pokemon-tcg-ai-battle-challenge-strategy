"""Verified adapter for the real cabt engine (blueprint §2 / PROBLEM 2).

Responsibilities:
- wrap the kaggle-environments cabt binding (game.battle_start/select/finish);
- expose one lossless, validated battle lifecycle;
- translate raw engine observations into CabtObservation (see cabt_types.py);
- never send an impossible selection into the native DLL (out-of-range indices
  crash it with a native access violation / OSError), and surface any failure
  that does leak out as a SIMULATOR_EXCEPTION / INVALID_ACTION record.

Verified against the bundled engine: a known-legal 60-card deck starts a battle
(errorPlayer=-1), the first selection is YES_NO/IS_FIRST (select type 9), and a
duplicate-heavy deck is rejected (errorType=3) before battle_ptr is set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..contracts import Action, GameState, Observation, PlayerState
from ..errors import FailureCategory, FailureRecord
from ..provenance import EnvironmentType, ResultSource
from .cabt_types import CabtObservation

try:  # import guard so the package can be used for data-only work
    from kaggle_environments.envs.cabt.cg import game as _cg_game  # type: ignore

    _ENGINE_AVAILABLE = True
    _IMPORT_ERROR = ""
except Exception as e:  # pragma: no cover
    _cg_game = None  # type: ignore
    _ENGINE_AVAILABLE = False
    _IMPORT_ERROR = f"{type(e).__name__}: {e}"


class CapabilityError(RuntimeError):
    pass


@dataclass
class SimulatorStartData:
    errorPlayer: int = -1
    errorType: int = -1


class EngineUnavailable(Exception):
    reason: str

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BattleStepError(Exception):
    """Raised when a battle step fails at or before the engine level."""

    category = FailureCategory.SIMULATOR_EXCEPTION

    def __init__(self, message: str, indices: list[int]):
        super().__init__(message)
        self.indices = list(indices)
        self.detail = message


def engine_capability() -> dict[str, Any]:
    if _ENGINE_AVAILABLE:
        return {
            "available": True,
            "environment_type": EnvironmentType.VERIFIED_REAL.value,
            "implementation": "kaggle_environments.envs.cabt.cg.game",
        }
    return {
        "available": False,
        "environment_type": EnvironmentType.REAL_SIMULATOR_UNAVAILABLE.value,
        "reason": _IMPORT_ERROR,
    }


class BaseBattle:
    """Abstract battle lifecycle shared by the real adapter and the strict mock."""

    ENVIRONMENT_TYPE = "UNSET"

    def start(self, deck0: list[int] | None = None, deck1: list[int] | None = None):
        raise NotImplementedError

    def select(self, indices: list[int]):
        raise NotImplementedError

    def finish(self) -> None:
        raise NotImplementedError

    def observation(self) -> CabtObservation:
        raise NotImplementedError

    def visualize(self) -> str:
        raise NotImplementedError


class RealCabtBattle(BaseBattle):
    """One battle against the real engine. environment_type = VERIFIED_REAL."""

    ENVIRONMENT_TYPE = EnvironmentType.VERIFIED_REAL.value

    def __init__(self):
        if not _ENGINE_AVAILABLE:
            raise EngineUnavailable(_IMPORT_ERROR)
        self._last_raw: dict[str, Any] | None = None

    # -- lifecycle -----------------------------------------------------------

    def start(self, deck0: list[int] | None = None, deck1: list[int] | None = None) -> SimulatorStartData:
        if deck0 is None or deck1 is None:
            raise ValueError("RealCabtBattle.start requires both decks")
        if len(deck0) != 60 or len(deck1) != 60:
            raise ValueError("The deck must contain 60 cards.")
        obs, start_data = _cg_game.battle_start(list(deck0), list(deck1))
        self._last_raw = obs
        return SimulatorStartData(errorPlayer=int(start_data.errorPlayer), errorType=int(start_data.errorType))

    def select(self, indices: list[int]) -> CabtObservation:
        if not isinstance(indices, list) or not all(isinstance(i, int) for i in indices):
            raise BattleStepError("select_list is not list[int]", indices)

        # Pre-validate against the last observation so an impossible selection
        # never reaches the native DLL (which would segfault).
        n_options = self._option_count()
        if n_options is not None and any(i < 0 or i >= n_options for i in indices):
            raise BattleStepError(
                f"selection {indices} out of range (0..{n_options - 1})", indices
            )

        try:
            raw = _cg_game.battle_select(indices)
        except (IndexError, ValueError) as e:
            raise BattleStepError(f"engine rejected selection {indices}: {e}", indices)
        except OSError as e:  # native access violation from a malformed selection
            raise BattleStepError(f"engine crashed on selection {indices}: {e}", indices)
        self._last_raw = raw
        return CabtObservation.from_dict(raw)

    def finish(self) -> None:
        try:
            _cg_game.battle_finish()
        except Exception:  # pragma: no cover - engine teardown is best-effort
            pass

    def observation(self) -> CabtObservation:
        if self._last_raw is None:
            raise RuntimeError("battle not started")
        return CabtObservation.from_dict(self._last_raw)

    def visualize(self) -> str:
        return _cg_game.visualize_data()

    @property
    def pending(self) -> bool:
        if self._last_raw is None:
            return True
        cur = self._last_raw.get("current") or {}
        return int(cur.get("result", -1)) < 0

    # -- helpers -------------------------------------------------------------

    def _option_count(self) -> int | None:
        """None when the engine is in the deck-selection phase (select is None)."""
        if self._last_raw is None:
            return None
        sel = self._last_raw.get("select")
        if not sel:
            return None
        return len(sel.get("option", []))


def run_reachable_game(
    deck0: list[int],
    deck1: list[int],
    policy: Callable[[dict[str, Any]], list[int]],
    *,
    max_steps: int = 2000,
) -> dict[str, Any]:
    """Drive one VERIFIED_REAL battle to completion with an external policy.

    policy receives the raw observation dict and returns:
      - the 60-card deck (list of card IDs) when obs['select'] is None;
      - otherwise a list of option indices.
    Engine rejections are recorded as failures; a failed or crashed step is a loss.
    """
    battle = RealCabtBattle()
    start = battle.start(deck0, deck1)
    if start.errorPlayer >= 0:
        battle.finish()
        return {
            "decks_legal": False,
            "error_player": start.errorPlayer,
            "error_type": start.errorType,
            "steps": 0,
            "result": -2,
            "failures": [
                FailureRecord(FailureCategory.INVALID_ACTION, "illegal deck").to_dict()
            ],
            "environment": EnvironmentType.VERIFIED_REAL.value,
            "source": ResultSource.LOCAL_EXPERIMENT.value,
        }

    steps = 0
    failures: list[FailureRecord] = []
    result = -1
    obs = battle.observation()
    while steps < max_steps:
        cur = obs.raw.get("current") or {}
        if int(cur.get("result", -1)) >= 0:
            result = int(cur["result"])
            break
        try:
            action = policy(obs.raw)
        except Exception as e:
            failures.append(FailureRecord(FailureCategory.AGENT_EXCEPTION, f"policy raised: {e}", step=steps))
            # emergency fallback: end turn using the first option
            action = [0]
        try:
            obs = battle.select(list(action))
        except BattleStepError as e:
            failures.append(FailureRecord(FailureCategory.INVALID_ACTION, e.detail, step=steps))
            break
        steps += 1
    else:
        failures.append(FailureRecord(FailureCategory.SIMULATOR_EXCEPTION, "step budget exceeded", step=steps))

    battle.finish()
    return {
        "decks_legal": True,
        "steps": steps,
        "result": result,
        "failures": [f.to_dict() for f in failures],
        "environment": EnvironmentType.VERIFIED_REAL.value,
        "source": ResultSource.LOCAL_EXPERIMENT.value,
    }


# ---- canonical translation (raw -> internal canonical Observation) ----

def translate_raw(raw: dict[str, Any], source: ResultSource = ResultSource.LOCAL_EXPERIMENT) -> Observation:
    """Translate a raw engine observation into a typed canonical Observation.

    Reserved for the real adapter path (MOCK observations should go through the
    same shape-checked path so the policy layer is environment-agnostic).
    """
    parsed = CabtObservation.from_dict(raw)
    legal_actions: list[Action] = []
    if parsed.select is not None:
        for i, opt in enumerate(parsed.select.option):
            legal_actions.append(
                Action(
                    action_id=f"opt{i}",
                    action_type=f"type:{opt.type}",
                    parameters={
                        "area": opt.area, "index": opt.index, "playerIndex": opt.playerIndex,
                        "attackId": opt.attackId, "cardId": opt.cardId, "serial": opt.serial,
                        "count": opt.count, "inPlayArea": opt.inPlayArea, "inPlayIndex": opt.inPlayIndex,
                        "energyIndex": opt.energyIndex, "toolIndex": opt.toolIndex, "number": opt.number,
                    },
                    source_index=i,
                    raw_option=raw,
                )
            )
    gs = _translate_state(parsed.current) if parsed.current is not None else None
    return Observation(
        raw=raw,
        visible_state=gs,
        legal_actions=legal_actions,
        metadata={
            "select_type": parsed.select.type if parsed.select else None,
            "select_context": parsed.select.context if parsed.select else None,
            "select_min_count": parsed.select.minCount if parsed.select else 0,
            "select_max_count": parsed.select.maxCount if parsed.select else 0,
            "logs": [log.type for log in parsed.logs],
            "ship_source": "verified_adapter.translate_raw",
        },
        source=source,
    ).validate()


def _translate_state(cur) -> GameState:
    players: list[PlayerState] = []
    for idx, p in enumerate(cur.players):
        players.append(
            PlayerState(
                player_index=idx,
                active=_first_or_empty(p.active),
                bench=list(p.bench),
                hand=list(p.hand) if p.hand is not None else None,
                hand_count=p.handCount,
                prize=list(p.prize),
                deck_count=p.deckCount,
                discard=list(p.discard),
                bench_max=p.benchMax,
                poisoned=p.poisoned,
                burned=p.burned,
                asleep=p.asleep,
                paralyzed=p.paralyzed,
                confused=p.confused,
            ).validate()
        )
    return GameState(
        turn=cur.turn,
        turn_action_count=cur.turnActionCount,
        your_index=cur.yourIndex,
        first_player=cur.firstPlayer,
        supporter_played=cur.supporterPlayed,
        stadium_played=cur.stadiumPlayed,
        energy_attached=cur.energyAttached,
        retreated=cur.retreated,
        result=cur.result,
        stadium=list(cur.stadium),
        looking=list(cur.looking) if cur.looking is not None else None,
        players=players,
    ).validate()


def _first_or_empty(lst: list):
    return [lst[0] if lst[0] is not None else None] if lst else []