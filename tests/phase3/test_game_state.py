"""Phase 3 tests — game state representation."""

import pytest
from ptcgabc.state.game_state import (
    StructuredGameState, PlayerState, PokemonInPlay,
    GamePhase, ResourcePressure, BoardPosition,
)


def _make_pokemon(hp: int = 100, damage: int = 0, is_ex: bool = False) -> PokemonInPlay:
    return PokemonInPlay(
        card_id="328", card_name="Pikachu ex",
        max_hp=hp, current_hp=hp - damage, damage_counters=damage,
        attached_energy={"L": 2}, status_conditions=[],
        is_ex=is_ex, stage="Basic", pokemon_type="Lightning",
        retreat_cost=1, tools_attached=[], attacks_available=[],
    )


class TestPokemonInPlay:
    def test_hp_fraction_full(self):
        p = _make_pokemon(100, 0)
        assert p.hp_fraction == 1.0

    def test_hp_fraction_half(self):
        p = _make_pokemon(100, 50)
        assert abs(p.hp_fraction - 0.5) < 0.01

    def test_is_ko_when_zero(self):
        p = _make_pokemon(100, 100)
        assert p.is_ko

    def test_total_energy(self):
        p = _make_pokemon()
        assert p.total_energy == 2


class TestPlayerState:
    def test_board_presence_with_active(self):
        ps = PlayerState(player_id=0, active=_make_pokemon(), prizes_remaining=6)
        ps.compute_board_presence()
        assert ps.board_presence == 1

    def test_board_presence_active_plus_bench(self):
        ps = PlayerState(player_id=0, prizes_remaining=6)
        ps.active = _make_pokemon()
        ps.bench  = [_make_pokemon(), _make_pokemon()]
        ps.compute_board_presence()
        assert ps.board_presence == 3

    def test_total_energy_in_play(self):
        ps = PlayerState(player_id=0, prizes_remaining=6)
        ps.active = _make_pokemon()  # 2 energy
        ps.bench  = [_make_pokemon()]  # 2 energy
        assert ps.total_energy_in_play == 4


class TestStructuredGameState:
    def test_default_phase_is_opening(self):
        gs = StructuredGameState(turn_number=1)
        gs.compute_derived_features()
        assert gs.game_phase == GamePhase.OPENING

    def test_early_phase(self):
        gs = StructuredGameState(turn_number=4)
        gs.compute_derived_features()
        assert gs.game_phase == GamePhase.EARLY

    def test_midgame_phase(self):
        gs = StructuredGameState(turn_number=7)
        gs.compute_derived_features()
        assert gs.game_phase == GamePhase.MIDGAME

    def test_late_phase(self):
        gs = StructuredGameState(turn_number=12)
        gs.us.prizes_remaining = 3
        gs.opponent.prizes_remaining = 3
        gs.compute_derived_features()
        assert gs.game_phase == GamePhase.LATE

    def test_endgame_phase(self):
        gs = StructuredGameState(turn_number=15)
        gs.us.prizes_remaining = 1
        gs.opponent.prizes_remaining = 1
        gs.compute_derived_features()
        assert gs.game_phase == GamePhase.ENDGAME

    def test_ahead_board_position(self):
        gs = StructuredGameState()
        gs.us.prizes_remaining = 2
        gs.opponent.prizes_remaining = 5
        gs.compute_derived_features()
        assert gs.board_position == BoardPosition.AHEAD

    def test_behind_board_position(self):
        gs = StructuredGameState()
        gs.us.prizes_remaining = 5
        gs.opponent.prizes_remaining = 4
        gs.compute_derived_features()
        assert gs.board_position == BoardPosition.BEHIND

    def test_resource_pressure_rich(self):
        gs = StructuredGameState()
        gs.us.hand_count = 5
        gs.compute_derived_features()
        assert gs.resource_pressure == ResourcePressure.RICH

    def test_resource_pressure_critical(self):
        gs = StructuredGameState()
        gs.us.hand_count = 0
        gs.compute_derived_features()
        assert gs.resource_pressure == ResourcePressure.CRITICAL

    def test_feature_vector_keys(self):
        gs = StructuredGameState(turn_number=3)
        gs.compute_derived_features()
        fv = gs.to_feature_vector()
        for key in ("turn_number", "our_prizes", "opp_prizes", "game_phase",
                    "prize_delta", "board_position", "legal_action_count"):
            assert key in fv

    def test_feature_vector_no_hidden_info(self):
        gs = StructuredGameState()
        fv = gs.to_feature_vector()
        # Must NOT include opponent hand contents, deck order, etc.
        for forbidden in ("opponent_hand_cards", "deck_order", "rng_seed",
                          "prize_cards", "opp_hand_cards"):
            assert forbidden not in fv

    def test_prizes_default_to_6(self):
        """Engine-verified: 6 prizes, not blueprint's 3."""
        ps = PlayerState(player_id=0)
        assert ps.prizes_remaining == 6
