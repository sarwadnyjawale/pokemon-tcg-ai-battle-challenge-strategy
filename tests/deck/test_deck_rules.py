"""Tests for engine-verified game format constants (Phase 2).

All constants were empirically confirmed against the real cabt DLL in Phase 1.
"""

import pytest
from ptcgabc.deck.deck import (
    POCKET_DECK_SIZE,
    POCKET_MAX_COPIES,
    POCKET_MAX_BASIC_ENERGY,
    POCKET_OPENING_HAND,
    POCKET_PRIZE_COUNT,
    POCKET_ENERGY_COPIES_UNLIMITED,
)


def test_deck_size_is_60():
    assert POCKET_DECK_SIZE == 60, "Engine verified: 60-card deck"


def test_max_copies_non_energy_is_4():
    assert POCKET_MAX_COPIES == 4, "Engine verified: errorType=2 on 5x non-energy"


def test_basic_energy_limit_is_none():
    assert POCKET_MAX_BASIC_ENERGY is None, "Engine verified: unlimited basic energy"


def test_energy_copies_unlimited_flag():
    assert POCKET_ENERGY_COPIES_UNLIMITED is True


def test_opening_hand_is_7():
    assert POCKET_OPENING_HAND == 7, "Engine verified: handCount=7"


def test_prize_count_is_6():
    assert POCKET_PRIZE_COUNT == 6, "Engine verified: prize_len=6"
