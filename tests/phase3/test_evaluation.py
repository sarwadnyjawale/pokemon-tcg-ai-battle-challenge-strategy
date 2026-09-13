"""Phase 3 tests — evaluation harness."""

import pytest
from ptcgabc.evaluation.evaluator import (
    MockSimulator, EvaluationConfig, EvaluationResults,
    GameResult, wilson_confidence_interval, required_sample_size,
    run_evaluation,
)
from ptcgabc.agents.baselines.baseline_agents import RandomBaseline


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestWilsonCI:
    def test_all_wins(self):
        lo, hi = wilson_confidence_interval(100, 100)
        assert lo > 0.9

    def test_no_games(self):
        lo, hi = wilson_confidence_interval(0, 0)
        assert lo == 0.0 and hi == 1.0

    def test_bounds_in_range(self):
        lo, hi = wilson_confidence_interval(50, 100)
        assert 0.0 <= lo <= hi <= 1.0

    def test_symmetric_around_half(self):
        lo, hi = wilson_confidence_interval(50, 100)
        assert abs((lo + hi) / 2 - 0.5) < 0.05


class TestRequiredSampleSize:
    def test_returns_positive_int(self):
        n = required_sample_size()
        assert isinstance(n, int) and n > 0

    def test_larger_effect_needs_fewer_games(self):
        n_small = required_sample_size(0.60, 0.50)
        n_large = required_sample_size(0.70, 0.50)
        assert n_large < n_small


# ---------------------------------------------------------------------------
# MockSimulator
# ---------------------------------------------------------------------------

class TestMockSimulator:
    def test_get_observation_has_required_keys(self):
        sim = MockSimulator(seed=42)
        obs = sim.get_observation()
        for key in ("legal_actions", "turn_number", "our_prizes", "opp_prizes",
                    "game_phase", "prize_delta"):
            assert key in obs

    def test_legal_actions_non_empty(self):
        sim = MockSimulator(seed=42)
        obs = sim.get_observation()
        assert len(obs["legal_actions"]) >= 1

    def test_prizes_start_at_6(self):
        """Engine-verified: 6 prizes (not blueprint's 3)."""
        sim = MockSimulator(seed=42)
        assert sim.our_prizes == 6
        assert sim.opp_prizes == 6

    def test_game_terminates(self):
        sim = MockSimulator(seed=1)
        obs = sim.get_observation()
        done = False
        for _ in range(200):
            la = obs.get("legal_actions", [])
            obs, done, info = sim.step(0, la)
            if done:
                break
        assert done, "MockSimulator did not terminate within 200 steps"

    def test_winner_is_0_or_1(self):
        sim = MockSimulator(seed=99)
        obs = sim.get_observation()
        for _ in range(200):
            la = obs.get("legal_actions", [])
            obs, done, info = sim.step(0, la)
            if done:
                assert info["winner"] in (0, 1)
                break


# ---------------------------------------------------------------------------
# EvaluationResults
# ---------------------------------------------------------------------------

class TestEvaluationResults:
    def _make_results(self, wins: int, total: int) -> EvaluationResults:
        config = EvaluationConfig(
            experiment_id="TEST-001", agent_name="Test", opponent_name="Mock",
            deck_name="D", opponent_deck="R", num_games=total,
            randomization_seed=42, player_order="alternating",
            game_state_conditions=["standard"], metrics=["win_rate"],
        )
        r = EvaluationResults(experiment_id="TEST-001", config=config)
        r.wins = wins
        r.losses = total - wins
        r.total_games = total
        r.game_records = [
            GameResult(f"G{i}", 0 if i < wins else 1, 10, 3, 4, 0, 0)
            for i in range(total)
        ]
        r.compute_summary()
        return r

    def test_win_rate_computed(self):
        r = self._make_results(60, 100)
        assert abs(r.win_rate - 0.60) < 0.001

    def test_ci_contains_win_rate(self):
        r = self._make_results(60, 100)
        assert r.ci_lower <= r.win_rate <= r.ci_upper

    def test_source_is_local_experiment(self):
        r = self._make_results(50, 100)
        assert r.results_source == "LOCAL_EXPERIMENT"

    def test_to_dict_keys(self):
        r = self._make_results(50, 100)
        d = r.to_dict()
        for k in ("experiment_id", "results_source", "win_rate", "ci_lower", "ci_upper",
                  "mean_turns", "legal_error_rate"):
            assert k in d


# ---------------------------------------------------------------------------
# run_evaluation
# ---------------------------------------------------------------------------

class TestRunEvaluation:
    def test_runs_correct_number_of_games(self, tmp_path):
        agent = RandomBaseline(seed=77)
        config = EvaluationConfig(
            experiment_id="P3-TEST-RUN-001", agent_name="B1-Random",
            opponent_name="MockRandom", deck_name="D", opponent_deck="R",
            num_games=20, randomization_seed=0, player_order="alternating",
            game_state_conditions=["standard"], metrics=["win_rate"],
        )
        results = run_evaluation(
            agent=agent, config=config,
            simulator_factory=lambda seed: MockSimulator(seed=seed),
            output_dir=tmp_path,
        )
        assert results.total_games == 20

    def test_output_json_written(self, tmp_path):
        agent = RandomBaseline(seed=1)
        config = EvaluationConfig(
            experiment_id="P3-TEST-FILE-001", agent_name="B1-Random",
            opponent_name="MockRandom", deck_name="D", opponent_deck="R",
            num_games=10, randomization_seed=0, player_order="alternating",
            game_state_conditions=["standard"], metrics=["win_rate"],
        )
        run_evaluation(
            agent=agent, config=config,
            simulator_factory=lambda seed: MockSimulator(seed=seed),
            output_dir=tmp_path,
        )
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1

    def test_zero_catastrophic_errors(self, tmp_path):
        agent = RandomBaseline(seed=2)
        config = EvaluationConfig(
            experiment_id="P3-TEST-ERR-001", agent_name="B1-Random",
            opponent_name="MockRandom", deck_name="D", opponent_deck="R",
            num_games=30, randomization_seed=0, player_order="alternating",
            game_state_conditions=["standard"], metrics=["win_rate"],
        )
        results = run_evaluation(
            agent=agent, config=config,
            simulator_factory=lambda seed: MockSimulator(seed=seed),
            output_dir=tmp_path,
        )
        assert results.catastrophic_error_rate == 0.0
