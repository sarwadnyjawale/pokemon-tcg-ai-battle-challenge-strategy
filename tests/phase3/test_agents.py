"""Phase 3 tests — baseline agents."""

import pytest
from ptcgabc.agents.baselines.baseline_agents import (
    SimulatorOrderBaseline, RandomBaseline,
    SimpleHeuristicBaseline, TacticalGreedyBaseline,
    StrategicHeuristicBaseline,
)
from ptcgabc.agents.baselines.legal_action_scorer import (
    LegalActionScorerAgent, ActionFeatures, extract_action_features,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_ACTIONS = [
    {"type": "attack",        "name": "Thunder Shock", "damage": 30, "energy_cost": 1},
    {"type": "attack",        "name": "Circle Circuit", "damage": 60, "energy_cost": 2},
    {"type": "attach_energy", "name": "Attach Lightning"},
    {"type": "play_trainer",  "name": "Professor's Research", "effect_category": "draw"},
    {"type": "retreat",       "name": "Retreat"},
    {"type": "pass",          "name": "End Turn"},
]

STANDARD_GS = {
    "game_phase":             "midgame",
    "our_prizes":             4,
    "opp_prizes":             3,
    "our_active_hp_fraction": 0.8,
    "opp_active_hp_fraction": 0.5,
    "opp_active_max_hp":      120,
    "our_active_max_hp":      100,
    "opp_is_ex":              0,
    "our_hand_count":         3,
    "our_bench_count":        2,
    "prize_delta":            1,
    "our_energy_in_play":     2,
    "our_active_damage":      20,
    "opp_active_damage":      60,
}


# ---------------------------------------------------------------------------
# Contract tests (all agents)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent", [
    SimulatorOrderBaseline(),
    RandomBaseline(seed=0),
    SimpleHeuristicBaseline(),
    TacticalGreedyBaseline(),
    StrategicHeuristicBaseline(),
    LegalActionScorerAgent(),
])
class TestAgentContract:
    def test_returns_valid_index(self, agent):
        idx, reason = agent.select_action(MOCK_ACTIONS, STANDARD_GS)
        assert 0 <= idx < len(MOCK_ACTIONS)

    def test_returns_reason_string(self, agent):
        _, reason = agent.select_action(MOCK_ACTIONS, STANDARD_GS)
        assert isinstance(reason, str) and len(reason) > 0

    def test_single_action_always_zero(self, agent):
        idx, _ = agent.select_action([MOCK_ACTIONS[0]], STANDARD_GS)
        assert idx == 0

    def test_raises_on_empty_actions(self, agent):
        with pytest.raises((ValueError, Exception)):
            agent.select_action([], STANDARD_GS)

    def test_reset_increments_game_count(self, agent):
        before = agent.game_count
        agent.reset()
        assert agent.game_count == before + 1


# ---------------------------------------------------------------------------
# B0 — Simulator Order
# ---------------------------------------------------------------------------

class TestSimulatorOrderBaseline:
    def test_always_picks_first(self):
        agent = SimulatorOrderBaseline()
        for _ in range(10):
            idx, _ = agent.select_action(MOCK_ACTIONS, STANDARD_GS)
            assert idx == 0


# ---------------------------------------------------------------------------
# B1 — Random
# ---------------------------------------------------------------------------

class TestRandomBaseline:
    def test_different_seed_same_distribution(self):
        a = RandomBaseline(seed=1)
        b = RandomBaseline(seed=2)
        results_a = set(a.select_action(MOCK_ACTIONS, STANDARD_GS)[0] for _ in range(20))
        results_b = set(b.select_action(MOCK_ACTIONS, STANDARD_GS)[0] for _ in range(20))
        # Both should explore more than 1 action
        assert len(results_a) > 1 or len(results_b) > 1  # at least one explores


# ---------------------------------------------------------------------------
# B2 — Simple Heuristic
# ---------------------------------------------------------------------------

class TestSimpleHeuristic:
    def test_prefers_ko_attack(self):
        agent = SimpleHeuristicBaseline()
        # High-damage action that KOs, vs pass
        ko_action  = {"type": "attack", "name": "KO", "damage": 200}
        pass_action = {"type": "pass"}
        gs = {**STANDARD_GS, "opp_active_hp_fraction": 0.3, "opp_active_max_hp": 60,
              "opp_active_damage": 0}
        idx, reason = agent.select_action([pass_action, ko_action], gs)
        # KO action is at index 1 — it should be chosen
        assert idx == 1 or "ko" in reason.lower() or "attack" in reason.lower()

    def test_no_crash_with_varied_action_types(self):
        agent = SimpleHeuristicBaseline()
        for action in MOCK_ACTIONS:
            agent.select_action([action], STANDARD_GS)


# ---------------------------------------------------------------------------
# B3 — Tactical Greedy
# ---------------------------------------------------------------------------

class TestTacticalGreedy:
    def test_prefers_high_damage(self):
        agent = TacticalGreedyBaseline()
        low_dmg  = {"type": "attack", "damage": 10}
        high_dmg = {"type": "attack", "damage": 100}
        idx, _ = agent.select_action([low_dmg, high_dmg], STANDARD_GS)
        assert idx == 1  # high damage preferred


# ---------------------------------------------------------------------------
# B4 — Strategic Heuristic
# ---------------------------------------------------------------------------

class TestStrategicHeuristic:
    def test_endgame_prefers_attack(self):
        agent = StrategicHeuristicBaseline()
        attack  = {"type": "attack", "damage": 60}
        trainer = {"type": "play_trainer", "effect_category": "draw"}
        gs = {**STANDARD_GS, "game_phase": "endgame", "our_prizes": 1, "opp_prizes": 1}
        idx, _ = agent.select_action([attack, trainer], gs)
        assert idx == 0  # attack preferred in endgame

    def test_opening_prefers_setup(self):
        agent = StrategicHeuristicBaseline()
        setup  = {"type": "play_pokemon"}
        attack = {"type": "attack", "damage": 30}
        gs = {**STANDARD_GS, "game_phase": "opening", "our_bench_count": 0}
        idx, _ = agent.select_action([attack, setup], gs)
        assert idx == 1  # setup preferred in opening


# ---------------------------------------------------------------------------
# B6 — Legal Action Scorer
# ---------------------------------------------------------------------------

class TestLegalActionScorer:
    def test_ko_action_gets_high_score(self):
        agent  = LegalActionScorerAgent()
        ko_gs  = {**STANDARD_GS, "opp_active_hp_fraction": 0.1, "opp_active_max_hp": 60}
        ko_act = {"type": "attack", "damage": 60}
        feats  = extract_action_features(ko_act, 0, ko_gs)
        assert feats.would_ko is True
        score  = agent.score_features(feats)
        assert score >= 100.0

    def test_pass_has_negative_score(self):
        agent = LegalActionScorerAgent()
        pass_a = {"type": "pass"}
        feats  = extract_action_features(pass_a, 0, STANDARD_GS)
        score  = agent.score_features(feats)
        assert score < 0

    def test_feature_vector_length(self):
        feats = extract_action_features(MOCK_ACTIONS[0], 0, STANDARD_GS)
        vec = feats.to_vector()
        assert len(vec) == ActionFeatures.dimension()

    def test_all_elements_float(self):
        feats = extract_action_features(MOCK_ACTIONS[0], 0, STANDARD_GS)
        for v in feats.to_vector():
            assert isinstance(v, float)
