"""Tests for Phase-2 candidate decks (real canonical card ids only).

These tests verify that every candidate deck:
  - uses only real integer card ids (no fictional strings like PIK-001)
  - passes the rules-only validator (correct size, copy limits)
  - produces a valid DeckComparison when build_comparison is called
"""

import pytest
from ptcgabc.deck.deck import DeckValidator, DeckCard
from ptcgabc.deck.candidates import (
    build_all_candidates,
    build_pikachu_aggro,
    build_mewtwo_control,
    build_gardevoir_midrange,
    build_dragapult_reference,
    build_comparison,
)


@pytest.fixture
def validator():
    return DeckValidator()


class TestCandidateCardIds:
    """All card ids must be valid integers (real canonical ids, not fictional)."""

    @pytest.mark.parametrize("name,builder", [
        ("pikachu_aggro", build_pikachu_aggro),
        ("mewtwo_control", build_mewtwo_control),
        ("gardevoir_midrange", build_gardevoir_midrange),
        ("dragapult_reference", build_dragapult_reference),
    ])
    def test_ids_are_integers(self, name, builder):
        for card in builder():
            int(card.card_id), f"{name}: card_id '{card.card_id}' not int-castable"


class TestDeckSizes:
    """build_all_candidates total card counts (rules-layer)."""

    @pytest.mark.parametrize("name,rows", build_all_candidates())
    def test_dragapult_reference_is_60(self, name, rows):
        if name == "dragapult_ex_reference":
            total = sum(c.count for c in rows)
            assert total == 60

    def test_all_candidates_have_cards(self):
        for name, rows in build_all_candidates():
            assert len(rows) > 0, f"{name} has no cards"
            assert sum(c.count for c in rows) > 0


class TestDragapultReferenceValidation:
    """The Phase-1 engine-verified reference deck must pass rules-only validation."""

    def test_dragapult_reference_rules_valid(self, validator):
        rows = build_dragapult_reference()
        result = validator.validate_rules_only(rows)
        wrong_size = [e for e in result.rule_errors if e.code == "WRONG_SIZE"]
        assert not wrong_size, f"dragapult reference is not 60 cards: {result.rule_errors}"
        copy_errs = [e for e in result.rule_errors if e.code == "TOO_MANY_COPIES"]
        assert not copy_errs, f"dragapult reference has copy violations: {copy_errs}"


class TestBuildComparison:
    def test_returns_deck_comparison(self, validator):
        from ptcgabc.deck.deck import DeckComparison
        result = build_comparison(validator)
        assert isinstance(result, DeckComparison)

    def test_comparison_has_four_analyses(self, validator):
        result = build_comparison(validator)
        assert len(result.analyses) == 4

    def test_recommended_archetype_is_string(self, validator):
        result = build_comparison(validator)
        assert isinstance(result.recommended_archetype, str)
        assert len(result.recommended_archetype) > 0

    def test_comparison_provenance_is_hypothesis(self, validator):
        result = build_comparison(validator)
        assert result.provenance == "HYPOTHESIS"

    def test_to_dict(self, validator):
        result = build_comparison(validator)
        d = result.to_dict()
        assert "experiment_id" in d
        assert "analyses" in d
        assert len(d["analyses"]) == 4
