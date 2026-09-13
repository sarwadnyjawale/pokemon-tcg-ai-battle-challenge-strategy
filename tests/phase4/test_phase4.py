"""Phase 4 tests — learned scorer, training loop, ablation, architecture decision tree."""

import math
import json
import pytest
from pathlib import Path

from ptcgabc.agents.learned.learned_scorer import (
    LearningConfig,
    LinearActionScorer,
    LearnedActionScorerAgent,
    SelfPlayTrainer,
    architecture_decision_tree,
)
from ptcgabc.evaluation.ablation import (
    AblationCondition, FrozenBenchmark, AblationResult,
    ABLATION_CONDITIONS, FAILURE_TAXONOMY,
    FailureEvent, FailureAnalyzer,
    run_ablation_study,
)
from ptcgabc.evaluation.evaluator import MockSimulator

# ---------------------------------------------------------------------------
# LinearActionScorer
# ---------------------------------------------------------------------------

class TestLinearActionScorer:
    def _scorer(self, dim: int = 4) -> LinearActionScorer:
        s = LinearActionScorer(feature_dim=dim, learning_rate=0.1, seed=0)
        s.weights = [1.0, 0.0, 0.0, 0.0]
        return s

    def test_score_dot_product(self):
        s = self._scorer()
        assert abs(s.score([2.0, 0.0, 0.0, 0.0]) - 2.0) < 1e-9

    def test_score_wrong_dim_raises(self):
        s = self._scorer()
        with pytest.raises(ValueError):
            s.score([1.0, 2.0])   # wrong dim

    def test_softmax_sums_to_one(self):
        s = LinearActionScorer(feature_dim=4, seed=0)
        probs = s.softmax_over_actions([1.0, 2.0, 3.0])
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_softmax_empty(self):
        s = LinearActionScorer(feature_dim=4, seed=0)
        assert s.softmax_over_actions([]) == []

    def test_greedy_picks_highest(self):
        s = self._scorer(4)
        fvs = [[2.0, 0, 0, 0], [1.0, 0, 0, 0], [3.0, 0, 0, 0]]
        idx, _ = s.select_action(fvs, greedy=True)
        assert idx == 2   # highest dot product

    def test_select_action_empty_raises(self):
        s = LinearActionScorer(feature_dim=4, seed=0)
        with pytest.raises(ValueError):
            s.select_action([])

    def test_reinforce_update_changes_weights(self):
        s = LinearActionScorer(feature_dim=4, learning_rate=0.1, seed=0)
        w_before = list(s.weights)
        traj = [([1.0, 0.0, 0.0, 0.0], [1.0], 1.0)]
        s.reinforce_update(traj)
        assert s.weights != w_before

    def test_reinforce_update_increments_counter(self):
        s = LinearActionScorer(feature_dim=4, seed=0)
        s.reinforce_update([([1.0, 0, 0, 0], [1.0], 0.5)])
        assert s.update_count == 1

    def test_supervised_update_increases_pos_score(self):
        s = LinearActionScorer(feature_dim=4, learning_rate=0.5, seed=0)
        pos = [1.0, 0.0, 0.0, 0.0]
        neg = [0.0, 0.0, 0.0, 0.0]
        score_before = s.score(pos)
        s.supervised_update(pos, [neg])
        assert s.score(pos) > score_before

    def test_save_load_roundtrip(self, tmp_path):
        s = LinearActionScorer(feature_dim=4, learning_rate=0.05, seed=7)
        s.weights = [1.0, 2.0, 3.0, 4.0]
        s.bias    = 0.5
        path = tmp_path / "model.json"
        s.save(path)
        s2 = LinearActionScorer.load(path)
        assert s2.weights == s.weights
        assert s2.bias    == s.bias
        assert s2.feature_dim == 4

    def test_score_batch(self):
        s = LinearActionScorer(feature_dim=2, seed=0)
        s.weights = [1.0, 0.0]
        fvs = [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]
        scores = s.score_batch(fvs)
        assert scores[2] > scores[1] > scores[0]


# ---------------------------------------------------------------------------
# LearnedActionScorerAgent
# ---------------------------------------------------------------------------

MOCK_GS = {
    "game_phase": "midgame", "our_prizes": 4, "opp_prizes": 3,
    "our_active_hp_fraction": 0.8, "opp_active_hp_fraction": 0.5,
    "opp_active_max_hp": 120, "our_active_max_hp": 100,
    "opp_is_ex": 0, "our_hand_count": 3, "our_bench_count": 2,
    "prize_delta": 1, "our_energy_in_play": 2,
    "our_active_damage": 0, "opp_active_damage": 0,
}
MOCK_ACTIONS = [
    {"type": "attack",       "name": "Thunder", "damage": 60, "energy_cost": 2},
    {"type": "attach_energy","name": "Attach"},
    {"type": "pass",         "name": "End Turn"},
]


class TestLearnedActionScorerAgent:
    def _agent(self, eps: float = 0.0) -> LearnedActionScorerAgent:
        scorer = LinearActionScorer(feature_dim=26, seed=0)
        return LearnedActionScorerAgent(scorer, exploration_rate=eps, name="test")

    def test_returns_valid_index(self):
        agent = self._agent()
        idx, reason = agent.select_action(MOCK_ACTIONS, MOCK_GS)
        assert 0 <= idx < len(MOCK_ACTIONS)

    def test_returns_reason_string(self):
        agent = self._agent()
        _, reason = agent.select_action(MOCK_ACTIONS, MOCK_GS)
        assert isinstance(reason, str) and len(reason) > 0

    def test_empty_actions_raises(self):
        agent = self._agent()
        with pytest.raises(ValueError):
            agent.select_action([], MOCK_GS)

    def test_reset_increments_game_count(self):
        agent = self._agent()
        agent.reset()
        assert agent.game_count == 1

    def test_reset_clears_trajectory(self):
        agent = self._agent()
        agent.select_action(MOCK_ACTIONS, MOCK_GS)
        agent.reset()
        assert agent.trajectory == []

    def test_trajectory_recorded_after_action(self):
        agent = self._agent()
        agent.select_action(MOCK_ACTIONS, MOCK_GS)
        assert len(agent.trajectory) == 1

    def test_update_from_game_result_win(self):
        agent = self._agent()
        # Take multiple actions so discounted returns differ (advantage != 0)
        for _ in range(3):
            agent.select_action(MOCK_ACTIONS, MOCK_GS)
        w_before = list(agent.scorer.weights)
        agent.update_from_game_result(won=True)
        # With multiple steps, at least the bias should change (advantage non-zero on outer turns)
        changed = (agent.scorer.weights != w_before or agent.scorer.bias != 0.0)
        assert changed

    def test_update_from_game_result_empty_trajectory(self):
        agent = self._agent()
        # No crash on empty trajectory
        agent.update_from_game_result(won=True)

    def test_exploit_reason_contains_exploit(self):
        agent = self._agent(eps=0.0)  # always exploit
        _, reason = agent.select_action(MOCK_ACTIONS, MOCK_GS)
        assert "exploit" in reason


# ---------------------------------------------------------------------------
# SelfPlayTrainer
# ---------------------------------------------------------------------------

class TestSelfPlayTrainer:
    def _config(self, n: int = 20) -> LearningConfig:
        return LearningConfig(
            experiment_id="TEST-P4-001",
            hypothesis="Learned weights beat heuristic",
            null_hypothesis="No difference",
            model="LinearActionScorer",
            deck="pikachu_ex_aggro",
            opponents=["MockRandom"],
            training_games=n,
            evaluation_games=20,
            learning_rate=0.01,
            discount_factor=0.95,
            exploration_rate=0.2,
            exploration_decay=0.995,
            randomization_seed=42,
        )

    def test_training_completes(self, tmp_path):
        scorer = LinearActionScorer(feature_dim=26, seed=0)
        agent  = LearnedActionScorerAgent(scorer, exploration_rate=0.2)
        config = self._config(20)
        trainer = SelfPlayTrainer(
            agent=agent, config=config,
            simulator_factory=lambda seed: MockSimulator(seed=seed),
            output_dir=tmp_path,
        )
        result = trainer.run_training()
        assert "final_training_wr" in result
        assert 0.0 <= result["final_training_wr"] <= 1.0

    def test_model_final_json_written(self, tmp_path):
        scorer = LinearActionScorer(feature_dim=26, seed=0)
        agent  = LearnedActionScorerAgent(scorer)
        config = self._config(10)
        trainer = SelfPlayTrainer(
            agent=agent, config=config,
            simulator_factory=lambda seed: MockSimulator(seed=seed),
            output_dir=tmp_path,
        )
        trainer.run_training()
        assert (tmp_path / "model_final.json").exists()

    def test_training_results_json_written(self, tmp_path):
        scorer = LinearActionScorer(feature_dim=26, seed=1)
        agent  = LearnedActionScorerAgent(scorer)
        config = self._config(10)
        trainer = SelfPlayTrainer(
            agent=agent, config=config,
            simulator_factory=lambda seed: MockSimulator(seed=seed),
            output_dir=tmp_path,
        )
        trainer.run_training()
        assert (tmp_path / "training_results.json").exists()

    def test_source_is_local_experiment(self, tmp_path):
        scorer = LinearActionScorer(feature_dim=26, seed=2)
        agent  = LearnedActionScorerAgent(scorer)
        config = self._config(5)
        trainer = SelfPlayTrainer(
            agent=agent, config=config,
            simulator_factory=lambda seed: MockSimulator(seed=seed),
            output_dir=tmp_path,
        )
        result = trainer.run_training()
        assert result["source"] == "LOCAL_EXPERIMENT"


# ---------------------------------------------------------------------------
# Architecture decision tree
# ---------------------------------------------------------------------------

class TestArchitectureDecisionTree:
    def _baseline(self, wr: float) -> dict:
        return {"B4-StrategicHeuristic": {"win_rate": wr}}

    def test_q1_positive_when_supervised_beats_heuristic(self):
        result = architecture_decision_tree(
            baseline_results   =self._baseline(0.50),
            supervised_results ={"win_rate": 0.60, "ci_lower": 0.55},
        )
        assert result["conclusion"] == "ARCHITECTURE_JUSTIFIED"

    def test_q1_negative_when_supervised_below_heuristic(self):
        result = architecture_decision_tree(
            baseline_results   =self._baseline(0.60),
            supervised_results ={"win_rate": 0.55, "ci_lower": 0.48},
        )
        assert result["conclusion"] == "SUPERVISED_INSUFFICIENT"

    def test_decisions_list_not_empty(self):
        result = architecture_decision_tree(
            baseline_results   =self._baseline(0.50),
            supervised_results ={"win_rate": 0.60, "ci_lower": 0.55},
        )
        assert len(result["decisions"]) >= 1

    def test_q2_branch_taken_when_rl_provided(self):
        result = architecture_decision_tree(
            baseline_results   =self._baseline(0.50),
            supervised_results ={"win_rate": 0.60, "ci_lower": 0.55},
            rl_results         ={"win_rate": 0.65, "ci_lower": 0.62},
        )
        q2 = [d for d in result["decisions"] if "Q2" in d["question"]]
        assert len(q2) == 1


# ---------------------------------------------------------------------------
# FrozenBenchmark
# ---------------------------------------------------------------------------

class TestFrozenBenchmark:
    def _bm(self) -> FrozenBenchmark:
        return FrozenBenchmark(
            benchmark_id="BM-TEST-001", benchmark_version="1.0",
            opponent_pool=["MockRandom"], deck_pool=["pikachu_ex_aggro"],
            scenario_pool=["standard"], num_games_per_condition=20,
            randomization_seed=42, metrics=["win_rate"], player_order="alternating",
        )

    def test_freeze_sets_flag(self):
        bm = self._bm()
        bm.freeze()
        assert bm.is_frozen

    def test_double_freeze_raises(self):
        bm = self._bm()
        bm.freeze()
        with pytest.raises(RuntimeError):
            bm.freeze()

    def test_validate_frozen_before_freeze_raises(self):
        bm = self._bm()
        with pytest.raises(RuntimeError):
            bm.validate_frozen()

    def test_to_dict_has_required_keys(self):
        bm = self._bm()
        d  = bm.to_dict()
        for k in ("benchmark_id", "benchmark_version", "is_frozen",
                  "num_games_per_condition", "randomization_seed"):
            assert k in d


# ---------------------------------------------------------------------------
# Ablation study
# ---------------------------------------------------------------------------

class TestAblationStudy:
    def _factory(self):
        def factory(removed):
            from ptcgabc.agents.baselines.baseline_agents import RandomBaseline
            return RandomBaseline(seed=0)
        return factory

    def _bm(self, n: int = 20) -> FrozenBenchmark:
        bm = FrozenBenchmark(
            benchmark_id="BM-ABL-TEST", benchmark_version="1.0",
            opponent_pool=["Mock"], deck_pool=["any"], scenario_pool=["standard"],
            num_games_per_condition=n, randomization_seed=0,
            metrics=["win_rate"], player_order="alternating",
        )
        bm.freeze()
        return bm

    def test_returns_results_list(self, tmp_path):
        results = run_ablation_study(
            base_agent_factory=self._factory(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            benchmark         =self._bm(10),
            output_dir        =tmp_path,
            conditions        =ABLATION_CONDITIONS[:2],
        )
        assert len(results) == 2

    def test_json_written(self, tmp_path):
        run_ablation_study(
            base_agent_factory=self._factory(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            benchmark         =self._bm(10),
            output_dir        =tmp_path,
            conditions        =ABLATION_CONDITIONS[:2],
        )
        assert (tmp_path / "ablation_results.json").exists()

    def test_unfrozen_benchmark_raises(self, tmp_path):
        bm = FrozenBenchmark(
            benchmark_id="BM-UNFRZ", benchmark_version="1.0",
            opponent_pool=[], deck_pool=[], scenario_pool=[],
            num_games_per_condition=5, randomization_seed=0,
            metrics=[], player_order="alternating",
        )
        with pytest.raises(RuntimeError):
            run_ablation_study(self._factory(), lambda seed: MockSimulator(seed=seed),
                               bm, tmp_path)


# ---------------------------------------------------------------------------
# FailureAnalyzer
# ---------------------------------------------------------------------------

class TestFailureAnalyzer:
    def _event(self, ftype: str) -> FailureEvent:
        return FailureEvent(
            game_id="G001", turn=3, failure_type=ftype,
            description="test", state_summary={}, action_taken={},
        )

    def test_record_valid_type(self):
        fa = FailureAnalyzer()
        fa.record(self._event("TACTICAL_ERROR"))
        assert fa.get_summary()["total_failures"] == 1

    def test_unknown_type_becomes_unknown(self):
        fa = FailureAnalyzer()
        fa.record(self._event("MADE_UP_TYPE"))
        ev = fa.failures[0]
        assert ev.failure_type == "UNKNOWN"

    def test_summary_counts_correct(self):
        fa = FailureAnalyzer()
        fa.record(self._event("TACTICAL_ERROR"))
        fa.record(self._event("TACTICAL_ERROR"))
        fa.record(self._event("STRATEGIC_ERROR"))
        s = fa.get_summary()
        assert s["by_type"]["TACTICAL_ERROR"] == 2

    def test_save_writes_json(self, tmp_path):
        fa = FailureAnalyzer()
        fa.record(self._event("DECK_WEAKNESS"))
        path = tmp_path / "failures.json"
        fa.save(path)
        data = json.loads(path.read_text())
        assert data["summary"]["total_failures"] == 1
