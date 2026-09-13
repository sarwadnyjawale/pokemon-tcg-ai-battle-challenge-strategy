"""Error taxonomy (blueprint §11, §14). Agent/system failures are never hidden."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FailureCategory(str, Enum):
    # Agent-side decision failures
    INVALID_ACTION = "INVALID_ACTION"
    AGENT_EXCEPTION = "AGENT_EXCEPTION"
    FALLBACK_USED = "FALLBACK_USED"
    # Simulator / parser failures
    SIMULATOR_EXCEPTION = "SIMULATOR_EXCEPTION"
    STATE_PARSE_ERROR = "STATE_PARSE_ERROR"
    DATA_PARSE_ERROR = "DATA_PARSE_ERROR"


class BehaviourSource(str, Enum):
    """Labels the origin of a decision as NORMAL or an emergency substitution."""

    NORMAL_ACTION = "NORMAL_ACTION"
    EMERGENCY_FALLBACK = "EMERGENCY_FALLBACK"
    AGENT_CRASH = "AGENT_CRASH"
    INVALID_ACTION = "INVALID_ACTION"


class StrategicFailureType(str, Enum):
    """Phase 5 failure taxonomy (pre-registered; not fabricated post hoc)."""

    TACTICAL = "TACTICAL"
    STRATEGIC = "STRATEGIC"
    INFORMATION = "INFORMATION"
    SEQUENCING = "SEQUENCING"
    RESOURCE = "RESOURCE"
    OPPONENT_INFERENCE = "OPPONENT_INFERENCE"
    REWARD = "REWARD"
    EXPLORATION = "EXPLORATION"
    CALIBRATION = "CALIBRATION"
    SIMULATOR_INTERFACE = "SIMULATOR_INTERFACE"
    DECK_WEAKNESS = "DECK_WEAKNESS"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"


@dataclass
class FailureRecord:
    """One recorded failure event. Never suppressed; always countable."""

    category: FailureCategory
    detail: str
    step: int = -1
    player_index: int = -1
    traceback: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "detail": self.detail,
            "step": self.step,
            "player_index": self.player_index,
            "traceback": self.traceback[:2000],
        }


@dataclass
class DecisionOutcome:
    """Outcome of one agent decision call, including fallback/crash accounting."""

    action: list[int] | None
    behaviour: BehaviourSource | None = None
    failure: FailureRecord | None = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "behaviour": self.behaviour.value if self.behaviour else None,
            "failure": self.failure.to_dict() if self.failure else None,
            "extra": self.extra,
        }