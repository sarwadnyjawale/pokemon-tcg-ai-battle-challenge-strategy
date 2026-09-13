"""Result provenance. Every experimental claim in this project carries a label."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ResultSource(str, Enum):
    """Allowed provenance labels (blueprint §2, §3)."""

    OFFICIAL_KAGGLE_RESULT = "OFFICIAL_KAGGLE_RESULT"
    LOCAL_EXPERIMENT = "LOCAL_EXPERIMENT"
    PUBLIC_REFERENCE = "PUBLIC_REFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    INFERENCE = "INFERENCE"
    UNKNOWN = "UNKNOWN"


class EnvironmentType(str, Enum):
    """Environment provenance.

    - MOCK: unit/interface tests only. NEVER gameplay evidence.
    - VERIFIED_REAL: the actual cabt engine (bundled libcg / cg.dll).
    - REAL_SIMULATOR_UNAVAILABLE: no real engine could be connected locally.
    """

    MOCK = "MOCK"
    VERIFIED_REAL = "VERIFIED_REAL"
    REAL_SIMULATOR_UNAVAILABLE = "REAL_SIMULATOR_UNAVAILABLE"


# Blueprint §2: we did not enter the Simulation category.
SIMULATION_ENTERED: bool = False


def describe_source() -> dict[str, Any]:
    return {
        "simulation_entered": SIMULATION_ENTERED,
        "official_simulation_rating": None,
        "official_simulation_leaderboard_position": None,
        "official_simulation_matchmaking_result": None,
        "note": (
            "No official Simulation result exists for this team. All local "
            "gameplay results are LOCAL_EXPERIMENT and must never be presented "
            "as official Kaggle results."
        ),
    }


class ProvenanceTags(str, Enum):
    """Tag attributes carried on provenance-stamped results.

    These are the canonical, lossless tags the Phase-2 deck layer reads. They
    are NOT claims about simulation outcome — they only label how evidence got
    produced and how far the rules pipeline can be held accountable for it.
    """

    RULE_LAYER_VERIFIED = "RULE_LAYER_VERIFIED"       # deck passed the real engine
    RULE_LAYER_RULES_ONLY = "RULE_LAYER_RULES_ONLY"   # static rules only; engine pending
    STRATEGIC_HYPOTHESIS = "STRATEGIC_HYPOTHESIS"     # analytic inference, not measured


def provenance_tagged(fn):
    """Decorator that stamps ProvenanceTags onto a function's metadata.

    Because we are in Phase 2 and the REAL simulator is unavailable, we never
    claim rule-layer verification here. The decorator is neutral: it attaches a
    tag, and the CALLER decides whether that tag is evidence or hypothesis.
    """
    fn._ptcgabc_provenance_tags = ProvenanceTags.STRATEGIC_HYPOTHESIS
    return fn


class UnsupportedEvidenceError(ValueError):
    """Raised when evidence that cannot back a claim is used as if it could."""


def require_support(claim: str, source: ResultSource, supports: tuple[ResultSource, ...]) -> None:
    if source not in supports:
        raise UnsupportedEvidenceError(
            f"Claim '{claim}' uses source {source.value!r}, which is not in the "
            f"supported set {[s.value for s in supports]}."
        )


# The final report must reject MOCK results automatically.
GAMEPLAY_EVIDENCE_SOURCES = (ResultSource.LOCAL_EXPERIMENT, ResultSource.OFFICIAL_KAGGLE_RESULT)
GAMEPLAY_ENVIRONMENT_TYPES = (EnvironmentType.VERIFIED_REAL,)


def assert_gameplay_evidence(environment_type: EnvironmentType, source: ResultSource) -> None:
    """Blueprint §1/§3: gameplay conclusions must use a verified real env and a valid source."""
    if environment_type not in GAMEPLAY_ENVIRONMENT_TYPES:
        raise UnsupportedEvidenceError(
            f"environment_type={environment_type.value} is not gameplay evidence "
            f"(allowed: {[e.value for e in GAMEPLAY_ENVIRONMENT_TYPES]})."
        )
    if source not in GAMEPLAY_EVIDENCE_SOURCES:
        raise UnsupportedEvidenceError(
            f"source={source.value} may not back gameplay conclusions "
            f"(allowed: {[s.value for s in GAMEPLAY_EVIDENCE_SOURCES]})."
        )