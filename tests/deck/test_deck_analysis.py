"""Tests for DeckAnalyzer probability and scoring models (Phase 2).

All probability/heuristic outputs are HYPOTHESES (analytic, not measured).
"""

import pytest
from ptcgabc.deck.deck import DeckAnalyzer, DeckAnalysis, DeckCard, POCKET_OPENING_HAND


def _make_deck(pokemon: int, energy: int, trainer: int) -> list[DeckCard]:
    """Build a simple test deck with given card-type counts (total = 60)."""
    assert pokemon + energy + trainer == 60
    cards = []
    if pokemon:
        cards.append(DeckCard(card_id="328", card_name="Pikachu ex",
                              card_type="Pokemon", count=pokemon, stage="Basic"))
    if energy:
        cards.append(DeckCard(card_id="4", card_name="Lightning Energy",
                              card_type="Energy", count=energy))
    if trainer:
        cards.append(DeckCard(card_id="1121", card_name="Ultra Ball",
                              card_type="Trainer", count=trainer))
    return cards


class TestHypergeometric:
    def test_setup_probability_range(self):
        """P(>=1 Basic in opening hand) must be in [0, 1]."""
        for n_pokemon in [4, 8, 12, 20]:
            deck = _make_deck(n_pokemon, 60 - n_pokemon - 4, 4)
            az = DeckAnalyzer(deck)
            p = az.compute_setup_probability()
            assert 0.0 <= p <= 1.0, f"out of range for n_pokemon={n_pokemon}: {p}"

    def test_more_basics_raises_probability(self):
        az4 = DeckAnalyzer(_make_deck(4, 52, 4))
        az12 = DeckAnalyzer(_make_deck(12, 44, 4))
        assert az12.compute_setup_probability() > az4.compute_setup_probability()

    def test_zero_basics_gives_zero(self):
        deck = [
            DeckCard(card_id="4", card_name="Energy", card_type="Energy", count=40),
            DeckCard(card_id="1121", card_name="Ultra Ball", card_type="Trainer", count=20),
        ]
        az = DeckAnalyzer(deck)
        assert az.compute_setup_probability() == 0.0

    def test_hypergeometric_sf_bounds(self):
        az = DeckAnalyzer([])
        assert az.hypergeometric_sf(60, 0, 7, 1) == 0.0
        assert az.hypergeometric_sf(60, 60, 7, 1) == 1.0


class TestAnalyze:
    def test_analyze_returns_deck_analysis(self):
        deck = _make_deck(8, 20, 32)
        az = DeckAnalyzer(deck, deck_name="test")
        result = az.analyze(archetype="aggro")
        assert isinstance(result, DeckAnalysis)

    def test_counts_are_correct(self):
        deck = _make_deck(8, 20, 32)
        az = DeckAnalyzer(deck, deck_name="test")
        result = az.analyze()
        assert result.pokemon_count == 8
        assert result.energy_count == 20
        assert result.trainer_count == 32
        assert result.total_cards == 60

    def test_ai_utility_score_in_range(self):
        deck = _make_deck(8, 20, 32)
        result = DeckAnalyzer(deck).analyze()
        assert -1.0 <= result.ai_utility_score <= 1.0

    def test_to_dict(self):
        result = DeckAnalyzer(_make_deck(8, 20, 32)).analyze()
        d = result.to_dict()
        assert "deck_name" in d
        assert "ai_utility_score" in d
        assert "provenance" in d
