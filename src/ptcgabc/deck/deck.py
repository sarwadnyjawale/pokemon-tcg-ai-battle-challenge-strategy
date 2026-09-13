"""
Deck representation, validation, and analysis for PTCGABC.
Phase 2 (Deck and Strategic Intelligence).

Constants here are ENGINE-VERIFIED against the real cabt DLL, NOT copied from
Pocket assumptions. Every constant carries a provenance tag. See
docs/simulator/verified_contract.md for the live evidence table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import comb
from typing import Any, Optional

from ..provenance import EnvironmentType, ProvenanceTags, ResultSource, provenance_tagged


# ---------------------------------------------------------------------------
# VERIFIED game-format constants (evidence: live engine probes, 2026-09-13)
# ---------------------------------------------------------------------------

POCKET_DECK_SIZE = 60          # blueprint's 20 was a Pocket assumption — REJECTED (verified 60)
POCKET_MAX_COPIES = 4          # non-energy copies (verified: 5x non-energy -> errorType=2)
POCKET_MAX_BASIC_ENERGY = None  # None = unlimited (verified: 5x basic {R} energy accepted)
POCKET_PRIZE_COUNT = 6         # verified live (prize_len=6)
POCKET_OPENING_HAND = 7        # verified live (handCount=7 after mulligans)
POCKET_ENERGY_COPIES_UNLIMITED = True

# Strategic labels we apply only as INFERENCE/HYPOTHESIS — never as fact.
AI_SETUP_ADVANTAGE_WEIGHT = 0.45
AI_ENERGY_ACCESS_WEIGHT = 0.30
AI_BRANCH_PENALTY_WEIGHT = 0.25

# What our rules pipeline can PROVE from the CSV + verified engine.
RULE_LAYER_VERIFIED = "RULE+ENGINE_VERIFIED"   # deck accepted by real engine
RULE_LAYER_RULES_ONLY = "RULES_ONLY"           # passes static rules; engine test pending


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DeckCard:
    card_id: str
    card_name: str
    card_type: str            # Pokemon / Trainer / Energy
    count: int
    evolution_chain: list[str] = field(default_factory=list)   # [basic, stage1, stage2] ids
    stage: Optional[str] = None
    hp: Optional[int] = None
    copies_limit: Optional[int] = None   # None -> energy (no limit)
    strategic_role: str = ""


@dataclass
class DeckValidationError:
    code: str
    message: str


@dataclass
class DeckValidationResult:
    is_valid: bool
    total_cards: int
    rule_errors: list[DeckValidationError] = field(default_factory=list)
    rule_warnings: list[str] = field(default_factory=list)
    engine_state: str = ""      # RULE_LAYER_*
    engine_error_player: int = -2
    engine_error_type: int = -2
    engine_verified: bool = False

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "total_cards": self.total_cards,
            "rule_errors": [e.__dict__ for e in self.rule_errors],
            "rule_warnings": self.rule_warnings,
            "engine_state": self.engine_state,
            "engine_error_player": self.engine_error_player,
            "engine_error_type": self.engine_error_type,
            "engine_verified": self.engine_verified,
        }


@dataclass
class DeckAnalysis:
    """Strategic analysis of a deck (from canonical cards + static reasoning).

    All probability fields are HYPOTHESES / analytic estimates unless the deck
    is also engine-verified; they never imply a Simulation result.
    """
    deck_name: str
    archetype: str
    total_cards: int = 0
    pokemon_count: int = 0
    trainer_count: int = 0
    energy_count: int = 0
    basic_pokemon_count: int = 0
    evolution_chains_verified: int = 0
    evolution_chains_ambiguous: int = 0

    # Consistency (hypergeometric, opening hand = 7)
    setup_probability: float = 0.0           # P(>=1 basic in opening hand)
    core_resource_probability: float = 0.0   # P(key card in first turns)
    energy_access_probability: float = 0.0   # P(energy by turn 2, hand + attach)

    # Complexity
    mean_legal_actions_estimate: float = 0.0
    decision_depth: int = 0
    branching_factor: float = 0.0

    # Strategy
    primary_win_condition: str = ""
    secondary_win_condition: str = ""
    recovery_capability: str = ""
    matchup_dependence: str = ""

    # AI alignment (heuristics)
    ai_complexity_score: float = 0.0
    ai_utility_score: float = 0.0
    fragility_score: float = 0.0

    # Provenance
    provenance: str = ResultSource.HYPOTHESIS.value
    engine_verified: bool = False
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: (v if not isinstance(v, (list,)) else list(v))
                for k, v in self.__dict__.items()}


class DeckValidator:
    """Validates deck composition; optionally cross-checks against the real
    simulator engine (verified layer)."""

    def __init__(
        self,
        deck_size: int = POCKET_DECK_SIZE,
        max_copies: int = POCKET_MAX_COPIES,
        max_basic_energy: Optional[int] = POCKET_MAX_BASIC_ENERGY,
        require_basic: bool = True,
    ):
        self.deck_size = deck_size
        self.max_copies = max_copies
        self.max_basic_energy = max_basic_energy
        self.require_basic = require_basic

    def validate_rules_only(self, deck: list[DeckCard]) -> DeckValidationResult:
        errs: list[DeckValidationError] = []
        warns: list[str] = []

        total = sum(c.count for c in deck)
        if total != self.deck_size:
            errs.append(DeckValidationError(
                "WRONG_SIZE", f"{total} cards (expected {self.deck_size})"))

        # Copy limits (energy exempt; verified in engine)
        from collections import Counter
        counts: Counter[str] = Counter()
        for c in deck:
            counts[c.card_name] += c.count

        for name, cnt in counts.items():
            card = next((c for c in deck if c.card_name == name), None)
            if card and card.card_type == "Energy":
                if self.max_basic_energy is not None and cnt > self.max_basic_energy:
                    errs.append(DeckValidationError(
                        "TOO_MANY_ENERGY", f"{name} x{cnt} (limit {self.max_basic_energy})"))
                continue
            if cnt > self.max_copies:
                errs.append(DeckValidationError(
                    "TOO_MANY_COPIES", f"{name} x{cnt} (max {self.max_copies})"))

        # At least one Basic Pokemon
        basics = [c for c in deck if c.card_type == "Pokemon" and c.stage == "Basic"]
        if self.require_basic and not basics:
            errs.append(DeckValidationError("NO_BASIC", "deck has no Basic Pokemon"))

        # Warn: evolution without its base / inconsistent chain
        for c in deck:
            if c.evolution_chain:
                for link in c.evolution_chain:
                    if not any(dc.card_id == link for dc in deck):
                        warns.append(
                            f"EVOLUTION_MISSING: {c.card_name} depends on card {link} not in deck")

        return DeckValidationResult(
            is_valid=not errs,
            total_cards=total,
            rule_errors=errs,
            rule_warnings=warns,
            engine_state=RULE_LAYER_RULES_ONLY,
        )

    def validate_against_engine(self, deck: list[DeckCard]) -> DeckValidationResult:
        """Cross-check legality with the real simulator (when available)."""
        result = self.validate_rules_only(deck)
        ids: list[int] = []
        try:
            ids = [int(c.card_id) for c in deck for _ in range(c.count)]
        except ValueError:
            result.rule_errors.append(DeckValidationError("BAD_ID", "non-integer card_id"))
            result.engine_state = "UNCHECKED"
            return result

        from ..simulator import verified_adapter as va

        if va._BATTLE_AVAILABLE is not True:
            result.engine_state = "ENGINE_UNAVAILABLE"
            result.rule_warnings.append("engine not importable; rules-only validation")
            return result

        battle = va.RealCabtBattle()
        try:
            start = battle.start(ids, ids)
            result.engine_error_player = int(start.errorPlayer)
            result.engine_error_type = int(start.errorType)
            result.engine_verified = start.errorPlayer == -1 and start.errorType == 0
            result.engine_state = RULE_LAYER_VERIFIED if result.engine_verified else "ENGINE_REJECTED"
            if not result.engine_verified:
                result.rule_errors.append(DeckValidationError(
                    "ENGINE_REJECT",
                    f"start rejected: player={start.errorPlayer} type={start.errorType}"))
        except Exception as e:  # engine crash on malformed deck is a failure, not silent
            result.engine_state = "ENGINE_CRASH"
            result.engine_verified = False
            result.rule_errors.append(DeckValidationError("ENGINE_CRASH", f"{type(e).__name__}: {e}"))
        finally:
            battle.finish()

        return result


class DeckAnalyzer:
    """Computes strategic metrics for a deck.

    Decision-critical models are intentionally SIMPLE + explicit and tagged as
    analytic hypotheses; they WILL be refined by Phase 2 simulator measurements.
    """

    def __init__(self, deck: list[DeckCard], deck_name: str = "Unknown"):
        self.deck = deck
        self.deck_name = deck_name

    # -- probability helpers -------------------------------------------------

    def hypergeometric_sf(self, pop: int, hits: int, draws: int, need: int) -> float:
        """P(X >= need) for X ~ Hypergeometric(pop, hits, draws)."""
        if hits <= 0 or draws <= 0 or need <= 0:
            return 0.0
        if need > hits:
            return 0.0
        lo = need
        hi = min(hits, draws)
        return sum(
            comb(hits, k) * comb(pop - hits, draws - k) / comb(pop, draws)
            for k in range(lo, hi + 1)
        )

    def compute_setup_probability(self, opening_hand_size: int = POCKET_OPENING_HAND) -> float:
        """P(at least one Basic Pokemon in the opening hand)."""
        basics = sum(c.count for c in self.deck if c.card_type == "Pokemon" and c.stage == "Basic")
        pop = sum(c.count for c in self.deck)
        return round(self.hypergeometric_sf(pop, basics, opening_hand_size, 1), 4)

    def compute_basic_energy_probability(self, opening_hand_size: int = POCKET_OPENING_HAND) -> float:
        """P(at least one basic energy in opening hand)."""
        energies = sum(c.count for c in self.deck if c.card_type == "Energy")
        pop = sum(c.count for c in self.deck)
        return round(self.hypergeometric_sf(pop, energies, opening_hand_size, 1), 4)

    def compute_energy_access_probability(self, opening_hand_size: int = POCKET_OPENING_HAND) -> float:
        """Energy by turn-2: opening energy OR (items/supporters that search)."""
        energies = sum(c.count for c in self.deck if c.card_type == "Energy")
        searchers = sum(
            c.count for c in self.deck
            if "Ball" in c.card_name or "Search" in c.card_name or "Buddy" in c.card_name
        )
        pop = sum(c.count for c in self.deck)
        p_hand = self.hypergeometric_sf(pop, energies, opening_hand_size, 1)
        p_attach = 1.0 - (1.0 if pop - energies == 0 else 1.0)
        # simple model: energy attach guaranteed (basic per turn) + search access
        return round(min(1.0, p_hand + 0.30 * (1 if searchers else 0) + 0.25), 4)

    def estimate_branching_factor(self, max_value: float = 20.0) -> float:
        """Rough estimate of mean legal actions per turn (analytic, not measured)."""
        attackers = sum(c.count for c in self.deck if c.card_type == "Pokemon")
        return round(min(max_value, 4.0 + 0.5 * attackers + 2.0), 2)

    def estimate_decision_depth(self) -> int:
        evo = sum(1 for c in self.deck if c.stage in ("Stage 1", "Stage 2"))
        return 4 if evo >= 8 else (3 if evo >= 4 else 2)

    # -- aggregation ---------------------------------------------------------

    def analyze(self, archetype: str = "") -> DeckAnalysis:
        total = sum(c.count for c in self.deck)
        analysis = DeckAnalysis(
            deck_name=self.deck_name,
            archetype=archetype,
            total_cards=total,
            pokemon_count=sum(c.count for c in self.deck if c.card_type == "Pokemon"),
            trainer_count=sum(c.count for c in self.deck if c.card_type == "Trainer"),
            energy_count=sum(c.count for c in self.deck if c.card_type == "Energy"),
            basic_pokemon_count=sum(c.count for c in self.deck if c.card_type == "Pokemon" and c.stage == "Basic"),
            evolution_chains_verified=sum(1 for c in self.deck if c.evolution_chain and c.stage in ("Stage 1", "Stage 2")),
        )
        analysis.setup_probability = self.compute_setup_probability()
        analysis.core_resource_probability = self.hypergeometric_sf(
            total, analysis.basic_pokemon_count, 7, 1)
        analysis.energy_access_probability = self.compute_energy_access_probability()
        analysis.branching_factor = self.estimate_branching_factor()
        analysis.decision_depth = self.estimate_decision_depth()
        analysis.ai_complexity_score = round(
            AI_SETUP_ADVANTAGE_WEIGHT * (1.0 - analysis.setup_probability)
            + AI_BRANCH_PENALTY_WEIGHT * (analysis.branching_factor / 20.0), 3)
        analysis.ai_utility_score = round(
            AI_SETUP_ADVANTAGE_WEIGHT * analysis.setup_probability
            + AI_ENERGY_ACCESS_WEIGHT * analysis.energy_access_probability
            - AI_BRANCH_PENALTY_WEIGHT * (analysis.branching_factor / 20.0), 4)
        analysis.fragility_score = round(
            (1.0 - analysis.setup_probability) + 0.5 * (1.0 - analysis.energy_access_probability), 3)
        analysis.caveats = [
            "All consistency/branching/probability fields are analytic hypotheses "
            "(hypergeometric + static reasoning), not engine measurements.",
            "AI_* scores are local heuristics for deck selection — they are NOT a "
            "validated predictor of Simulation outcome.",
        ]
        return analysis


@dataclass
class DeckComparison:
    """Side-by-side comparison of N candidate decks.

    All strategic scores are HYPOTHESES (analytic, not simulator-measured).
    Engine-verified flags are only True when validate_against_engine was called
    and the real cabt engine accepted the deck.
    """

    experiment_id: str
    analyses: list[DeckAnalysis] = field(default_factory=list)
    recommended_archetype: str = ""          # best by ai_utility_score (HYPOTHESIS)
    provenance: str = ResultSource.HYPOTHESIS.value
    caveats: list[str] = field(default_factory=list)

    def best(self) -> Optional[DeckAnalysis]:
        if not self.analyses:
            return None
        return max(self.analyses, key=lambda a: a.ai_utility_score)

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "analyses": [a.to_dict() for a in self.analyses],
            "recommended_archetype": self.recommended_archetype,
            "provenance": self.provenance,
            "caveats": self.caveats,
        }


__all__ = [
    "POCKET_DECK_SIZE", "POCKET_MAX_COPIES", "POCKET_MAX_BASIC_ENERGY",
    "POCKET_PRIZE_COUNT", "POCKET_OPENING_HAND", "POCKET_ENERGY_COPIES_UNLIMITED",
    "RULE_LAYER_VERIFIED", "RULE_LAYER_RULES_ONLY",
    "DeckCard", "DeckValidationError", "DeckValidationResult", "DeckAnalysis",
    "DeckComparison", "DeckValidator", "DeckAnalyzer",
    "AI_SETUP_ADVANTAGE_WEIGHT", "AI_ENERGY_ACCESS_WEIGHT", "AI_BRANCH_PENALTY_WEIGHT",
]
