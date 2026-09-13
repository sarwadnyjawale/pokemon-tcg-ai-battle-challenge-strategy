"""Tests for DeckValidator rules layer (Phase 2).

Engine cross-check tests are skipped when the real simulator is unavailable.
"""

import pytest
from ptcgabc.deck.deck import (
    DeckCard,
    DeckValidationResult,
    DeckValidator,
    POCKET_DECK_SIZE,
)


def _energy(cid: str, n: int) -> DeckCard:
    return DeckCard(card_id=cid, card_name=cid, card_type="Energy", count=n)


def _pokemon(cid: str, n: int, stage: str = "Basic") -> DeckCard:
    return DeckCard(card_id=cid, card_name=cid, card_type="Pokemon", count=n, stage=stage)


def _trainer(cid: str, n: int) -> DeckCard:
    return DeckCard(card_id=cid, card_name=cid, card_type="Trainer", count=n)


def _dragapult_deck() -> list[DeckCard]:
    """The engine-verified Dragapult ex reference deck (60 cards, with stages)."""
    return [
        _pokemon("119", 4), _pokemon("120", 4, "Stage 1"), _pokemon("121", 3, "Stage 2"),
        _pokemon("140", 1), _pokemon("184", 1),
        _pokemon("235", 2), _pokemon("1071", 1),
        _trainer("1079", 2), _trainer("1080", 1), _trainer("1086", 4), _trainer("1097", 2),
        _trainer("1120", 4), _trainer("1121", 4), _trainer("1152", 3), _trainer("1156", 1),
        _trainer("1182", 3), _trainer("1198", 4), _trainer("1210", 2), _trainer("1227", 4),
        _trainer("1256", 2),
        _energy("2", 4), _energy("5", 4),
    ]


@pytest.fixture
def validator():
    return DeckValidator()


class TestDeckSizeValidation:
    def test_correct_size_passes(self, validator):
        deck = _dragapult_deck()
        result = validator.validate_rules_only(deck)
        assert result.total_cards == 60
        wrong_size_errors = [e for e in result.rule_errors if e.code == "WRONG_SIZE"]
        assert not wrong_size_errors

    def test_59_cards_fails(self, validator):
        deck = _dragapult_deck()
        deck[0] = _pokemon("119", 3)   # remove one card
        result = validator.validate_rules_only(deck)
        assert result.total_cards == 59
        codes = [e.code for e in result.rule_errors]
        assert "WRONG_SIZE" in codes

    def test_61_cards_fails(self, validator):
        deck = _dragapult_deck()
        deck.append(_energy("1", 1))   # add one card
        result = validator.validate_rules_only(deck)
        assert result.total_cards == 61
        assert any(e.code == "WRONG_SIZE" for e in result.rule_errors)


class TestCopyLimitValidation:
    def test_five_copies_non_energy_rejected(self, validator):
        deck = [_pokemon("328", 5)] + [_energy("4", 55)]
        result = validator.validate_rules_only(deck)
        assert any(e.code == "TOO_MANY_COPIES" for e in result.rule_errors)

    def test_four_copies_accepted(self, validator):
        deck = [_pokemon("328", 4)] + [_energy("4", 56)]
        result = validator.validate_rules_only(deck)
        assert not any(e.code == "TOO_MANY_COPIES" for e in result.rule_errors)

    def test_energy_unlimited_copies(self, validator):
        # 60 basic energies — no copy-limit error (engine verified)
        deck = [_energy("2", 60)]
        result = validator.validate_rules_only(deck)
        assert not any(e.code == "TOO_MANY_COPIES" for e in result.rule_errors)
        assert not any(e.code == "TOO_MANY_ENERGY" for e in result.rule_errors)


class TestResultFields:
    def test_result_has_total_cards(self, validator):
        deck = _dragapult_deck()
        result = validator.validate_rules_only(deck)
        assert isinstance(result.total_cards, int)
        assert result.total_cards == 60

    def test_result_is_valid_on_legal_deck(self, validator):
        result = validator.validate_rules_only(_dragapult_deck())
        assert result.is_valid is True

    def test_result_to_dict(self, validator):
        result = validator.validate_rules_only(_dragapult_deck())
        d = result.to_dict()
        assert "is_valid" in d
        assert "total_cards" in d
        assert d["total_cards"] == 60
