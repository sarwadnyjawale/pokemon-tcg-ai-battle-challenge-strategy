"""Phase 2 — Deck and Strategic Intelligence.

Public API for the deck package.  Import directly from here:

    from ptcgabc.deck import DeckCard, DeckValidator, DeckAnalyzer, DeckComparison
    from ptcgabc.deck.candidates import build_all_candidates, build_comparison
"""

from .deck import (
    AI_BRANCH_PENALTY_WEIGHT,
    AI_ENERGY_ACCESS_WEIGHT,
    AI_SETUP_ADVANTAGE_WEIGHT,
    POCKET_DECK_SIZE,
    POCKET_MAX_COPIES,
    POCKET_OPENING_HAND,
    POCKET_PRIZE_COUNT,
    RULE_LAYER_RULES_ONLY,
    RULE_LAYER_VERIFIED,
    DeckAnalysis,
    DeckAnalyzer,
    DeckCard,
    DeckComparison,
    DeckValidationError,
    DeckValidationResult,
    DeckValidator,
)

__all__ = [
    "POCKET_DECK_SIZE", "POCKET_MAX_COPIES", "POCKET_OPENING_HAND", "POCKET_PRIZE_COUNT",
    "RULE_LAYER_VERIFIED", "RULE_LAYER_RULES_ONLY",
    "AI_SETUP_ADVANTAGE_WEIGHT", "AI_ENERGY_ACCESS_WEIGHT", "AI_BRANCH_PENALTY_WEIGHT",
    "DeckCard", "DeckValidationError", "DeckValidationResult",
    "DeckAnalysis", "DeckComparison", "DeckValidator", "DeckAnalyzer",
]
