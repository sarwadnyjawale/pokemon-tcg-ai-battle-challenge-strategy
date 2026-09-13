"""Tests for real CABT adapter integration.

These tests use the REAL kaggle-environments cabt engine.
MockSimulator is NOT used here — per the integration requirement.

Tests are marked to skip gracefully if cabt is unavailable in the environment.
"""

import json
import pytest
from pathlib import Path

# Check availability before importing — avoids confusing import errors
try:
    import kaggle_environments as ke
    ke.make("cabt")
    CABT_AVAILABLE = True
except Exception:
    CABT_AVAILABLE = False

skip_no_cabt = pytest.mark.skipif(
    not CABT_AVAILABLE,
    reason="Real CABT environment not available"
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DRAGAPULT_DECK = (
    [119]*4 + [120]*4 + [121]*3 + [140]*1 + [184]*1 +
    [235]*2 + [1071]*1 + [1079]*2 + [1080]*1 + [1086]*4 +
    [1097]*2 + [1120]*4 + [1121]*4 + [1152]*3 + [1156]*1 +
    [1182]*3 + [1198]*4 + [1210]*2 + [1227]*4 + [1256]*2 +
    [2]*4 + [5]*4
)

# ---------------------------------------------------------------------------
# Observation parser tests (with real observations where possible)
# ---------------------------------------------------------------------------

class TestObservationParser:
    """Test parse_observation() against real CABT observation dicts."""

    def _initial_obs(self) -> dict:
        return {
            "remainingOverageTime": 600,
            "step": 0,
            "select": None,
            "logs": [],
            "current": None,
            "search_begin_input": None,
        }

    def _deck_select_obs(self) -> dict:
        return {
            "remainingOverageTime": 599.999,
            "step": 1,
            "select": {
                "type": 9,
                "context": 41,
                "minCount": 1,
                "maxCount": 1,
                "remainDamageCounter": 0,
                "remainEnergyCost": 0,
                "option": [{"type": 1}, {"type": 2}],
                "deck": None,
                "contextCard": None,
                "effect": None,
            },
            "logs": [],
            "current": {
                "turn": 0,
                "turnActionCount": 1,
                "yourIndex": 0,
                "firstPlayer": -1,
                "supporterPlayed": False,
                "stadiumPlayed": False,
                "energyAttached": False,
                "retreated": False,
                "result": -1,
                "stadium": [],
                "looking": None,
                "players": [
                    {
                        "active": [], "bench": [], "benchMax": 5, "deckCount": 60,
                        "discard": [], "prize": [], "handCount": 0, "hand": [],
                        "poisoned": False, "burned": False, "asleep": False,
                        "paralyzed": False, "confused": False,
                    },
                    {
                        "active": [], "bench": [], "benchMax": 5, "deckCount": 60,
                        "discard": [], "prize": [], "handCount": 0, "hand": None,
                        "poisoned": False, "burned": False, "asleep": False,
                        "paralyzed": False, "confused": False,
                    },
                ],
            },
            "search_begin_input": "base64encodedstring==",
        }

    def _board_obs(self) -> dict:
        """Observation with active Pokemon on board."""
        return {
            "remainingOverageTime": 598.0,
            "step": 7,
            "select": {
                "type": 0, "context": 0,
                "minCount": 1, "maxCount": 1,
                "remainDamageCounter": 0, "remainEnergyCost": 0,
                "option": [
                    {"type": 7, "index": 1},
                    {"type": 8, "area": 2, "index": 2, "inPlayArea": 4, "inPlayIndex": 0},
                    {"type": 14},
                ],
                "deck": None, "contextCard": None, "effect": None,
            },
            "logs": [],
            "current": {
                "turn": 2, "turnActionCount": 1,
                "yourIndex": 0, "firstPlayer": 1,
                "supporterPlayed": False, "stadiumPlayed": False,
                "energyAttached": False, "retreated": False, "result": -1,
                "stadium": [], "looking": None,
                "players": [
                    {
                        "active": [{
                            "id": 119, "serial": 7, "playerIndex": 0,
                            "hp": 60, "maxHp": 60, "appearThisTurn": False,
                            "energies": [2], "energyCards": [{"id": 2, "serial": 40, "playerIndex": 0}],
                            "tools": [], "preEvolution": [],
                        }],
                        "bench": [],
                        "benchMax": 5, "deckCount": 46,
                        "discard": [],
                        "prize": [None]*6,
                        "handCount": 7,
                        "hand": [{"id": 120, "serial": 9, "playerIndex": 0}],
                        "poisoned": False, "burned": False, "asleep": False,
                        "paralyzed": False, "confused": False,
                    },
                    {
                        "active": [{
                            "id": 119, "serial": 67, "playerIndex": 1,
                            "hp": 60, "maxHp": 60, "appearThisTurn": False,
                            "energies": [2], "energyCards": [],
                            "tools": [], "preEvolution": [],
                        }],
                        "bench": [],
                        "benchMax": 5, "deckCount": 46,
                        "discard": [], "prize": [None]*6,
                        "handCount": 5, "hand": None,
                        "poisoned": False, "burned": False, "asleep": False,
                        "paralyzed": False, "confused": False,
                    },
                ],
            },
            "search_begin_input": "somebase64==",
        }

    def test_parse_initial_obs(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        gs = parse_observation(self._initial_obs(), player_index=0)
        assert gs.step == 0
        assert gs.select is None
        assert not gs.is_active
        assert gs.remaining_overage_time == 600

    def test_parse_deck_select_obs(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        gs = parse_observation(self._deck_select_obs(), player_index=0)
        assert gs.is_active
        assert gs.select is not None
        assert gs.select.is_deck_selection
        assert gs.select.context == 41
        assert len(gs.select.options) == 2

    def test_parse_board_obs_active_card(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        gs = parse_observation(self._board_obs(), player_index=0)
        assert gs.is_active
        assert gs.turn == 2
        assert gs.your_index == 0
        own = gs.own_player
        assert own is not None
        assert len(own.active) == 1
        assert own.active[0].card_id == 119
        assert own.active[0].hp == 60
        assert own.active[0].max_hp == 60
        assert own.hand is not None   # own hand visible
        assert len(own.hand) == 1

    def test_opponent_hand_hidden(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        gs = parse_observation(self._board_obs(), player_index=0)
        opp = gs.opp_player
        assert opp is not None
        assert opp.hand is None   # HIDDEN — information firewall
        assert opp.hand_count == 5  # count visible

    def test_prize_count_is_6(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        gs = parse_observation(self._board_obs(), player_index=0)
        assert gs.own_player.prize_count == 6

    def test_select_has_pass_option(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        gs = parse_observation(self._board_obs(), player_index=0)
        assert gs.select.has_pass
        assert gs.select.pass_index() is not None

    def test_legal_option_extraction(self):
        from ptcgabc.environment.cabt_observation_parser import (
            parse_observation, extract_legal_options
        )
        gs = parse_observation(self._board_obs(), player_index=0)
        options = extract_legal_options(gs)
        assert len(options) == 3

    def test_feature_dict_no_hidden_info(self):
        from ptcgabc.environment.cabt_observation_parser import (
            parse_observation, build_feature_dict
        )
        gs = parse_observation(self._board_obs(), player_index=0)
        fv = build_feature_dict(gs)
        # Must not include opponent hand contents
        for forbidden in ("opp_hand_cards", "opp_hand", "opp_prize_cards"):
            assert forbidden not in fv

    def test_feature_dict_has_required_keys(self):
        from ptcgabc.environment.cabt_observation_parser import (
            parse_observation, build_feature_dict
        )
        gs = parse_observation(self._board_obs(), player_index=0)
        fv = build_feature_dict(gs)
        for k in ("turn", "your_index", "own_hand_count", "opp_hand_count",
                  "prize_delta", "game_phase", "legal_option_count"):
            assert k in fv

    def test_hp_fraction(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        gs = parse_observation(self._board_obs(), player_index=0)
        assert gs.own_player.active[0].hp_fraction == pytest.approx(1.0)

    def test_malformed_observation_no_crash(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        # Empty dict
        gs = parse_observation({}, player_index=0)
        assert gs.step == 0
        assert not gs.is_active

    def test_missing_select_fields_no_crash(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        obs = {"select": {"type": 0, "context": 0}, "logs": [], "step": 5}
        gs = parse_observation(obs, player_index=0)
        assert gs.select is not None
        assert gs.select.options == []

    def test_terminal_state_detection(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        obs = {
            "step": 100, "select": None, "logs": [],
            "current": {
                "turn": 20, "turnActionCount": 1, "yourIndex": 0,
                "firstPlayer": 0, "supporterPlayed": False, "stadiumPlayed": False,
                "energyAttached": False, "retreated": False, "result": 0,
                "stadium": [], "looking": None, "players": [],
            },
        }
        gs = parse_observation(obs, player_index=0)
        assert gs.is_terminal
        assert gs.result == 0


# ---------------------------------------------------------------------------
# Action adapter tests
# ---------------------------------------------------------------------------

class TestActionAdapter:
    def _board_gs(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        return parse_observation({
            "step": 7, "remainingOverageTime": 598.0,
            "select": {
                "type": 0, "context": 0, "minCount": 1, "maxCount": 1,
                "remainDamageCounter": 0, "remainEnergyCost": 0,
                "option": [{"type": 14}, {"type": 7, "index": 1}],
                "deck": None, "contextCard": None, "effect": None,
            },
            "logs": [], "current": {
                "turn": 2, "turnActionCount": 1, "yourIndex": 0,
                "firstPlayer": 1, "supporterPlayed": False, "stadiumPlayed": False,
                "energyAttached": False, "retreated": False, "result": -1,
                "stadium": [], "looking": None,
                "players": [{
                    "active": [], "bench": [], "benchMax": 5, "deckCount": 40,
                    "discard": [], "prize": [None]*6, "handCount": 5, "hand": [],
                    "poisoned": False, "burned": False, "asleep": False,
                    "paralyzed": False, "confused": False,
                }],
            },
        }, player_index=0)

    def test_deck_action_correct_length(self):
        from ptcgabc.environment.cabt_action_adapter import build_deck_action
        action = build_deck_action(DRAGAPULT_DECK)
        assert len(action) == 60

    def test_deck_action_wrong_length_raises(self):
        from ptcgabc.environment.cabt_action_adapter import build_deck_action
        with pytest.raises(ValueError):
            build_deck_action([119]*59)

    def test_action_index_valid_range(self):
        from ptcgabc.environment.cabt_action_adapter import build_action_from_option_index
        gs = self._board_gs()
        action = build_action_from_option_index(0, gs)
        assert action == [0]

    def test_action_index_out_of_range_raises(self):
        from ptcgabc.environment.cabt_action_adapter import build_action_from_option_index
        gs = self._board_gs()
        with pytest.raises(ValueError):
            build_action_from_option_index(99, gs)

    def test_pass_action_index_minus_one(self):
        from ptcgabc.environment.cabt_action_adapter import build_action_from_option_index
        gs = self._board_gs()
        action = build_action_from_option_index(-1, gs)
        assert action == []

    def test_random_action_valid(self):
        from ptcgabc.environment.cabt_action_adapter import select_random_action
        gs = self._board_gs()
        action = select_random_action(gs)
        assert isinstance(action, list)
        if action:
            assert 0 <= action[0] < gs.select.option_count

    def test_first_action_is_zero(self):
        from ptcgabc.environment.cabt_action_adapter import select_first_action
        gs = self._board_gs()
        action = select_first_action(gs)
        assert action == [0]

    def test_inactive_player_returns_empty(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        from ptcgabc.environment.cabt_action_adapter import build_action_from_option_index
        gs = parse_observation({"step": 5, "select": None, "logs": []}, player_index=1)
        action = build_action_from_option_index(0, gs)
        assert action == []

    def test_deck_selection_action_raises_for_normal_method(self):
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        from ptcgabc.environment.cabt_action_adapter import build_action_from_option_index
        obs = {
            "step": 1, "select": {
                "type": 9, "context": 41, "minCount": 1, "maxCount": 1,
                "remainDamageCounter": 0, "remainEnergyCost": 0,
                "option": [{"type": 1}], "deck": None, "contextCard": None, "effect": None,
            },
            "logs": [], "current": None,
        }
        gs = parse_observation(obs, player_index=0)
        with pytest.raises(ValueError, match="build_deck_action"):
            build_action_from_option_index(0, gs)


# ---------------------------------------------------------------------------
# Real CABT integration tests (require live cabt environment)
# ---------------------------------------------------------------------------

@skip_no_cabt
class TestRealCabtIntegration:
    """These tests run against the actual CABT engine."""

    def test_cabt_make_succeeds(self):
        import kaggle_environments as ke
        env = ke.make("cabt")
        assert env is not None

    def test_real_game_completes(self):
        """Run one real game from start to terminal state."""
        from ptcgabc.environment.cabt_adapter import CabtGame
        from ptcgabc.agents.baselines.baseline_agents import RandomBaseline
        game = CabtGame(
            agent    = RandomBaseline(seed=42),
            opponent = "random",
            game_id  = "test-001",
        )
        result = game.run()
        assert result.total_steps > 0
        assert result.winner in (0, 1, -1)
        assert result.source == "REAL_CABT_LOCAL"
        assert result.legal_errors == 0

    def test_real_obs_has_expected_keys(self):
        """Verify real CABT obs has the schema we documented."""
        import kaggle_environments as ke
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        env = ke.make("cabt", debug=True)
        env.run(["random", "random"])
        # Check step 1 (first active step)
        step1 = env.steps[1]
        obs_raw = dict(step1[0].get("observation", {}))
        gs = parse_observation(obs_raw, player_index=0)
        assert gs.step == 1
        assert "remainingOverageTime" in obs_raw
        assert "select" in obs_raw
        assert "logs" in obs_raw
        assert "current" in obs_raw

    def test_real_deck_selection_step(self):
        """Step 1 should be deck selection (context=41)."""
        import kaggle_environments as ke
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        env = ke.make("cabt", debug=True)
        env.run(["random", "random"])
        step1 = env.steps[1]
        obs_raw = dict(step1[0].get("observation", {}))
        gs = parse_observation(obs_raw, player_index=0)
        # Step 1 active player has deck selection
        if gs.is_active and gs.select:
            assert gs.select.is_deck_selection or gs.select.context == 41

    def test_real_information_firewall(self):
        """In a real game, opponent hand must be null (hidden)."""
        import kaggle_environments as ke
        from ptcgabc.environment.cabt_observation_parser import parse_observation
        env = ke.make("cabt", debug=True)
        env.run(["random", "random"])
        # Find a step where current is populated for player 0
        for step in env.steps[2:]:
            obs_raw = dict(step[0].get("observation", {}))
            gs = parse_observation(obs_raw, player_index=0)
            if gs.players and len(gs.players) >= 2:
                opp = gs.opp_player
                if opp:
                    # Opponent hand must be null (hidden by engine)
                    assert opp.hand is None, \
                        "INFORMATION LEAK: opponent hand is not null"
                    break

    def test_real_action_loop_no_crash(self):
        """Run our agent through a real game with no crashes or illegal actions."""
        from ptcgabc.environment.cabt_adapter import CabtGame
        from ptcgabc.agents.baselines.baseline_agents import StrategicHeuristicBaseline
        game = CabtGame(
            agent    = StrategicHeuristicBaseline(),
            opponent = "random",
            game_id  = "test-heuristic-001",
        )
        result = game.run()
        assert result.total_steps > 0
        assert result.legal_errors == 0
        assert result.source == "REAL_CABT_LOCAL"

    def test_reproducibility_same_deck_different_seeds(self):
        """Two games with same agent should both complete without error."""
        from ptcgabc.environment.cabt_adapter import CabtGame
        from ptcgabc.agents.baselines.baseline_agents import RandomBaseline
        for seed in (0, 1):
            game = CabtGame(
                agent    = RandomBaseline(seed=seed),
                opponent = "random",
                game_id  = f"test-repro-{seed}",
            )
            result = game.run()
            assert result.total_steps > 0

    def test_winner_is_valid(self):
        """Winner must be 0, 1, or -1 (not any other value)."""
        from ptcgabc.environment.cabt_adapter import CabtGame
        from ptcgabc.agents.baselines.baseline_agents import RandomBaseline
        game = CabtGame(agent=RandomBaseline(seed=7), opponent="random")
        result = game.run()
        assert result.winner in (0, 1, -1)

    def test_source_never_official_kaggle(self):
        """Source must be REAL_CABT_LOCAL, never OFFICIAL_KAGGLE_RESULT."""
        from ptcgabc.environment.cabt_adapter import CabtGame
        from ptcgabc.agents.baselines.baseline_agents import RandomBaseline
        game = CabtGame(agent=RandomBaseline(seed=3), opponent="random")
        result = game.run()
        assert result.source == "REAL_CABT_LOCAL"
        assert result.source != "OFFICIAL_KAGGLE_RESULT"

    def test_b0_vs_random(self):
        """B0-SimulatorOrder vs random completes cleanly."""
        from ptcgabc.environment.cabt_adapter import CabtGame
        from ptcgabc.agents.baselines.baseline_agents import SimulatorOrderBaseline
        game = CabtGame(agent=SimulatorOrderBaseline(), opponent="random")
        result = game.run()
        assert result.legal_errors == 0

    def test_b6_vs_random(self):
        """B6-LegalActionScorer vs random completes cleanly."""
        from ptcgabc.environment.cabt_adapter import CabtGame
        from ptcgabc.agents.baselines.legal_action_scorer import LegalActionScorerAgent
        game = CabtGame(agent=LegalActionScorerAgent(), opponent="random")
        result = game.run()
        assert result.legal_errors == 0
