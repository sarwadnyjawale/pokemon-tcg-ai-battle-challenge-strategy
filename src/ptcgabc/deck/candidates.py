"""Handcrafted Phase-2 candidate decks built from REAL canonical cards.

Every candidate is constructed from cards in canonical_cards.json (verified
ids). We deliberately do NOT use fictional card ids (PIK-001, CHR-001, ...) —
Phase 1 defined lossless canonical cards, so deck candidates must reference
only real, engine-checkable cards. Each candidate carries the deck that we
want the engine to validate, plus the strategic story.

We build 4 archetype candidates aligned to the blueprint's comparison matrix:
  A. Aggro / fast attackers  (Pikachu ex + Zapdos, Lightning)
  B. Control / disruption    (Team Rocket's Mewtwo ex, Psychic lock)
  C. Midrange / evolution    (Mega Gardevoir ex, Ralts chain)
  D. Bench reference         (the verified legal Dragapult ex baseline)

All candidates are RuleLayer = HANDCRAFTED (author-curated). None is
claimed as a winner — Phase 3 experiments decide.
"""

from __future__ import annotations

from typing import Any, Optional

from .deck import (
    AI_BRANCH_PENALTY_WEIGHT,
    AI_ENERGY_ACCESS_WEIGHT,
    AI_SETUP_ADVANTAGE_WEIGHT,
    DeckCard,
    DeckComparison,
    DeckValidationResult,
    DeckValidator,
)


def _pokemon(cid: str, n: int, stage: str = "Basic") -> DeckCard:
    return DeckCard(card_id=cid, card_name=cid, card_type="Pokemon", count=n, stage=stage)


def _trainer(cid: str, n: int) -> DeckCard:
    return DeckCard(card_id=cid, card_name=cid, card_type="Trainer", count=n)


def _energy(cid: str, n: int) -> DeckCard:
    return DeckCard(card_id=cid, card_name=cid, card_type="Energy", count=n)


def _to_engine_deck(rows: list[DeckCard]) -> list[int]:
    out: list[int] = []
    for r in rows:
        out.extend([int(r.card_id)] * r.count)
    return out


def build_pikachu_aggro() -> list[DeckCard]:
    """Pikachu ex aggro — fast Lightning beatdown (60 cards).

    Engine-verified card ids from canonical_cards.json.
    Trainers are real item ids from the Dragapult reference pool.
    """
    return [
        # Pokemon (8)
        _pokemon("328", 4),   # Pikachu ex  HP190 {L}{L}@ 220 dmg
        _pokemon("948", 2),   # Pikachu     HP70  bench filler
        _pokemon("953", 2),   # Zapdos      HP120 190 dmg alt attacker
        # Trainers (32) — verified trainer ids from dragapult reference pool
        _trainer("1086", 4),  # Buddy-Buddy Poffin
        _trainer("1121", 4),  # Ultra Ball
        _trainer("1120", 4),  # Crushing Hammer
        _trainer("1182", 3),  # Boss's Orders
        _trainer("1227", 4),  # Arven
        _trainer("1198", 4),  # Carmine
        _trainer("1210", 2),  # Night Stretcher
        _trainer("1097", 2),  # Earthen Vessel
        _trainer("1152", 3),  # Iono
        _trainer("1256", 2),  # Professor's Research
        # Energy (20)
        _energy("4", 14),     # Basic {L} energy (unlimited)
        _energy("1", 6),      # Basic {G} energy (colorless filler)
    ]


def build_mewtwo_control() -> list[DeckCard]:
    """Team Rocket's Mewtwo ex control — Psychic disruption (60 cards)."""
    return [
        # Pokemon (8)
        _pokemon("431", 4),   # Team Rocket's Mewtwo ex  HP280
        _pokemon("235", 2),   # Budew (item-lock)
        _pokemon("987", 2),   # Mawile (guaranteed setup)
        # Trainers (32)
        _trainer("1086", 4),
        _trainer("1121", 4),
        _trainer("1120", 4),
        _trainer("1182", 3),
        _trainer("1227", 4),
        _trainer("1198", 4),
        _trainer("1210", 2),
        _trainer("1097", 2),
        _trainer("1152", 3),
        _trainer("1256", 2),
        # Energy (20)
        _energy("5", 20),     # Basic {P} energy
    ]


def build_gardevoir_midrange() -> list[DeckCard]:
    """Mega Gardevoir ex midrange — Ralts/Kirlia evolution (60 cards).

    Evolution chain verified: 745 Ralts -> 746 Kirlia -> 747 Mega Gardevoir ex.
    Dragon side line (119/120/121) hedges against Psychic-weak matchups.
    """
    return [
        # Pokemon (20)
        _pokemon("745", 4),              # Ralts  (Basic)
        _pokemon("746", 3, "Stage 1"),   # Kirlia
        _pokemon("747", 3, "Stage 2"),   # Mega Gardevoir ex
        _pokemon("119", 3),              # Dreepy (Basic)
        _pokemon("120", 2, "Stage 1"),   # Drakloak
        _pokemon("121", 2, "Stage 2"),   # Dragapult ex
        _pokemon("1071", 3),             # Meowth ex (draw engine)
        # Trainers (24)
        _trainer("1079", 2),  # Rare Candy
        _trainer("1080", 1),  # Pal Pad
        _trainer("1086", 4),  # Buddy-Buddy Poffin
        _trainer("1097", 2),  # Earthen Vessel
        _trainer("1121", 4),  # Ultra Ball
        _trainer("1182", 3),  # Boss's Orders
        _trainer("1198", 4),  # Carmine
        _trainer("1210", 2),  # Night Stretcher
        _trainer("1152", 2),  # Iono
        # Energy (16)
        _energy("5", 10),     # Basic {P} energy
        _energy("7", 6),      # Basic {D} energy (Dragapult line)
    ]


def build_dragapult_reference() -> list[DeckCard]:
    """Engine-verified Dragapult ex baseline (60 cards).

    This is the Phase-1 verified deck with corrected energy count.
    NOT claimed as a competition winner — it is the empirical baseline.
    """
    return [
        # Pokemon (16)
        _pokemon("119", 4),              # Dreepy   Basic
        _pokemon("120", 4, "Stage 1"),   # Drakloak
        _pokemon("121", 3, "Stage 2"),   # Dragapult ex
        _pokemon("140", 1),              # Jirachi  Basic tech
        _pokemon("184", 1),              # Mew ex   Basic tech
        _pokemon("235", 2),              # Budew    Basic
        _pokemon("1071", 1),             # Meowth ex Basic draw
        # Trainers (36)
        _trainer("1079", 2),  # Rare Candy
        _trainer("1080", 1),  # Pal Pad
        _trainer("1086", 4),  # Buddy-Buddy Poffin
        _trainer("1097", 2),  # Earthen Vessel
        _trainer("1120", 4),  # Crushing Hammer
        _trainer("1121", 4),  # Ultra Ball
        _trainer("1152", 3),  # Iono
        _trainer("1156", 1),  # Counter Catcher
        _trainer("1182", 3),  # Boss's Orders
        _trainer("1198", 4),  # Carmine
        _trainer("1210", 2),  # Night Stretcher
        _trainer("1227", 4),  # Arven
        _trainer("1256", 2),  # Professor's Research
        # Energy (8)
        _energy("2", 4),      # Basic {R} energy (colorless)
        _energy("5", 4),      # Basic {P} energy
    ]


def build_all_candidates() -> list[tuple[str, list[DeckCard]]]:
    return [
        ("pikachu_ex_aggro", build_pikachu_aggro()),
        ("mewtwo_rocket_control", build_mewtwo_control()),
        ("gardevoir_midrange", build_gardevoir_midrange()),
        ("dragapult_ex_reference", build_dragapult_reference()),
    ]


def build_comparison(
    validator: DeckValidator,
    candidates: Optional[list[tuple[str, list[DeckCard]]]] = None,
    experiment_id: str = "P2-DECK-COMPARE-001",
    archetypes: Optional[list[str]] = None,
) -> DeckComparison:
    """Run rules-validator + analyser over all candidates and produce comparison.

    Engine cross-check only fires when the real simulator is available
    (validate_against_engine). Otherwise rules-only validation is used.
    All probability outputs are HYPOTHESES (analytic; not engine measurements).
    """
    from .deck import DeckAnalyzer, DeckAnalysis, DeckComparison as _DC

    if candidates is None:
        candidates = build_all_candidates()

    analyses: list[DeckAnalysis] = []
    for name, rows in candidates:
        v = validator.validate_rules_only(rows)
        an = DeckAnalyzer(rows, deck_name=name).analyze(archetype=name)
        an.engine_verified = v.engine_verified
        analyses.append(an)

    best = max(analyses, key=lambda a: a.ai_utility_score) if analyses else None
    return _DC(
        experiment_id=experiment_id,
        analyses=analyses,
        recommended_archetype=best.deck_name if best else "",
        provenance="HYPOTHESIS",
        caveats=[
            "All scores are analytic hypotheses — hypergeometric + static heuristics.",
            "No Simulation result exists; recommended_archetype is NOT a validated winner.",
            "Engine verification requires the real cabt DLL (validate_against_engine).",
        ],
    )
