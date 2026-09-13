"""Phase 5 tests — adversarial evaluation, robustness, failure analysis."""

import json
import pytest
from pathlib import Path

from ptcgabc.evaluation.adversarial import (
    AdversarialScenario,
    ADVERSARIAL_SCENARIOS,
    run_adversarial_evaluation,
    compute_robustness_summary,
)
from ptcgabc.evaluation.ablation import (
    FrozenBenchmark, ABLATION_CONDITIONS, run_ablation_study,
    FailureAnalyzer, FailureEvent, FAILURE_TAXONOMY,
)
from ptcgabc.evaluation.evaluator import MockSimulator
from ptcgabc.agents.baselines.baseline_agents import (
    RandomBaseline, StrategicHeuristicBaseline,
)


# ---------------------------------------------------------------------------
# ADVERSARIAL_SCENARIOS catalogue
# ---------------------------------------------------------------------------

class TestAdversarialScenarioCatalogue:
    def test_seven_scenarios_defined(self):
        assert len(ADVERSARIAL_SCENARIOS) == 7

    def test_all_have_name(self):
        for s in ADVERSARIAL_SCENARIOS:
            assert isinstance(s.name, str) and len(s.name) > 0

    def test_all_have_failure_hypothesis(self):
        for s in ADVERSARIAL_SCENARIOS:
            assert isinstance(s.failure_hypothesis, str) and len(s.failure_hypothesis) > 0

    def test_all_have_valid_difficulty(self):
        valid = {"easy", "medium", "hard", "critical"}
        for s in ADVERSARIAL_SCENARIOS:
            assert s.expected_difficulty in valid

    def test_one_prize_endgame_is_endgame_phase(self):
        sc = next(s for s in ADVERSARIAL_SCENARIOS if s.name == "ONE_PRIZE_ENDGAME")
        assert sc.setup.get("game_phase") == "endgame"

    def test_early_prize_behind_setup(self):
        sc = next(s for s in ADVERSARIAL_SCENARIOS if s.name == "EARLY_PRIZE_BEHIND")
        # prize_delta > 0 means we're behind
        assert sc.setup.get("prize_delta", 0) >= 0

    def test_names_are_unique(self):
        names = [s.name for s in ADVERSARIAL_SCENARIOS]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# run_adversarial_evaluation
# ---------------------------------------------------------------------------

class TestRunAdversarialEvaluation:
    def _agent(self):
        return StrategicHeuristicBaseline()

    def test_runs_all_scenarios(self, tmp_path):
        results = run_adversarial_evaluation(
            agent             =self._agent(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS,
            games_per_scenario=10,
            benchmark_seed    =42,
            output_dir        =tmp_path,
        )
        assert len(results) == len(ADVERSARIAL_SCENARIOS)

    def test_result_has_required_keys(self, tmp_path):
        results = run_adversarial_evaluation(
            agent             =self._agent(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS[:2],
            games_per_scenario=10,
            benchmark_seed    =42,
            output_dir        =tmp_path,
        )
        for name, r in results.items():
            for key in ("win_rate", "ci_lower", "ci_upper", "games",
                        "expected_difficulty", "failure_hypothesis"):
                assert key in r, f"Missing key '{key}' in scenario '{name}'"

    def test_win_rates_in_range(self, tmp_path):
        results = run_adversarial_evaluation(
            agent             =self._agent(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS,
            games_per_scenario=10,
            benchmark_seed    =0,
            output_dir        =tmp_path,
        )
        for r in results.values():
            assert 0.0 <= r["win_rate"] <= 1.0

    def test_ci_contains_win_rate(self, tmp_path):
        results = run_adversarial_evaluation(
            agent             =self._agent(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS[:3],
            games_per_scenario=20,
            benchmark_seed    =1,
            output_dir        =tmp_path,
        )
        for r in results.values():
            assert r["ci_lower"] <= r["win_rate"] <= r["ci_upper"]

    def test_adversarial_json_written(self, tmp_path):
        run_adversarial_evaluation(
            agent             =self._agent(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS[:1],
            games_per_scenario=5,
            benchmark_seed    =0,
            output_dir        =tmp_path,
        )
        assert (tmp_path / "adversarial_results.json").exists()

    def test_source_label_correct(self, tmp_path):
        run_adversarial_evaluation(
            agent             =self._agent(),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS[:1],
            games_per_scenario=5,
            benchmark_seed    =0,
            output_dir        =tmp_path,
        )
        data = json.loads((tmp_path / "adversarial_results.json").read_text())
        assert data["source"] == "LOCAL_EXPERIMENT"

    def test_games_count_matches(self, tmp_path):
        n = 15
        results = run_adversarial_evaluation(
            agent             =RandomBaseline(seed=7),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS[:2],
            games_per_scenario=n,
            benchmark_seed    =0,
            output_dir        =tmp_path,
        )
        for r in results.values():
            assert r["games"] == n

    def test_random_agent_completes_no_crash(self, tmp_path):
        run_adversarial_evaluation(
            agent             =RandomBaseline(seed=99),
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            scenarios         =ADVERSARIAL_SCENARIOS,
            games_per_scenario=5,
            benchmark_seed    =0,
            output_dir        =tmp_path,
        )


# ---------------------------------------------------------------------------
# compute_robustness_summary
# ---------------------------------------------------------------------------

class TestComputeRobustnessSummary:
    def _make_results(self, wrs: list[float]) -> dict:
        names = [f"S{i}" for i in range(len(wrs))]
        return {
            n: {"win_rate": w, "ci_lower": 0.4, "ci_upper": 0.8,
                "games": 100, "expected_difficulty": "medium",
                "failure_hypothesis": "test"}
            for n, w in zip(names, wrs)
        }

    def test_perfect_robustness(self):
        results = self._make_results([0.65, 0.65, 0.65])
        summary = compute_robustness_summary(results, baseline_wr=0.65)
        assert summary["robustness_score"] == pytest.approx(1.0)
        assert summary["interpretation"] == "ROBUST"

    def test_fragile_agent(self):
        results = self._make_results([0.30, 0.25, 0.20])
        summary = compute_robustness_summary(results, baseline_wr=0.65)
        assert summary["interpretation"] == "FRAGILE"

    def test_worst_scenario_identified(self):
        results = self._make_results([0.70, 0.40, 0.60])
        summary = compute_robustness_summary(results, baseline_wr=0.65)
        assert summary["worst_scenario"] == "S1"  # WR=0.40

    def test_empty_results(self):
        summary = compute_robustness_summary({}, 0.65)
        assert summary["robustness_score"] == 0.0

    def test_mean_wr_correct(self):
        results = self._make_results([0.60, 0.70])
        summary = compute_robustness_summary(results, baseline_wr=0.65)
        assert abs(summary["mean_adversarial_wr"] - 0.65) < 0.01


# ---------------------------------------------------------------------------
# Phase 5 ablation (re-using Phase 4 framework, Phase 5 context)
# ---------------------------------------------------------------------------

class TestPhase5Ablation:
    def _bm(self) -> FrozenBenchmark:
        bm = FrozenBenchmark(
            benchmark_id="BM-P5-001", benchmark_version="1.0",
            opponent_pool=["MockRandom"], deck_pool=["dragapult_ex_reference"],
            scenario_pool=["BAD_OPENING", "SCARCE_RESOURCES"],
            num_games_per_condition=15,
            randomization_seed=77,
            metrics=["win_rate", "ci", "delta_vs_full"],
            player_order="alternating",
        )
        bm.freeze()
        return bm

    def test_ablation_with_strategic_agent(self, tmp_path):
        def factory(removed):
            if "all" in removed:
                return RandomBaseline(seed=0)
            return StrategicHeuristicBaseline()

        results = run_ablation_study(
            base_agent_factory=factory,
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            benchmark         =self._bm(),
            output_dir        =tmp_path,
            conditions        =ABLATION_CONDITIONS[:3],
        )
        assert len(results) == 3

    def test_all_conditions_have_delta(self, tmp_path):
        def factory(removed):
            return StrategicHeuristicBaseline()

        results = run_ablation_study(
            base_agent_factory=factory,
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            benchmark         =self._bm(),
            output_dir        =tmp_path,
            conditions        =ABLATION_CONDITIONS[:2],
        )
        for r in results:
            assert r.delta_vs_full is not None

    def test_full_system_delta_is_zero(self, tmp_path):
        def factory(removed):
            return StrategicHeuristicBaseline()

        results = run_ablation_study(
            base_agent_factory=factory,
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            benchmark         =self._bm(),
            output_dir        =tmp_path,
            conditions        =ABLATION_CONDITIONS[:1],  # FULL_SYSTEM only
        )
        full = next(r for r in results if r.condition_name == "FULL_SYSTEM")
        assert full.delta_vs_full == 0.0


# ---------------------------------------------------------------------------
# FailureAnalyzer (extended Phase 5 tests)
# ---------------------------------------------------------------------------

class TestFailureAnalyzerPhase5:
    def test_all_taxonomy_entries_valid(self):
        fa = FailureAnalyzer()
        for ft in FAILURE_TAXONOMY:
            fa.record(FailureEvent(
                game_id="G001", turn=1, failure_type=ft,
                description="test", state_summary={}, action_taken={},
            ))
        assert fa.get_summary()["total_failures"] == len(FAILURE_TAXONOMY)

    def test_most_common_returned(self):
        fa = FailureAnalyzer()
        for _ in range(5):
            fa.record(FailureEvent("G1", 1, "TACTICAL_ERROR", "test", {}, {}))
        fa.record(FailureEvent("G2", 2, "STRATEGIC_ERROR", "test", {}, {}))
        summary = fa.get_summary()
        assert summary["most_common"][0] == "TACTICAL_ERROR"

    def test_save_load_roundtrip(self, tmp_path):
        fa = FailureAnalyzer()
        fa.record(FailureEvent("G99", 5, "DECK_WEAKNESS", "bad deck", {}, {},
                               lesson="Add more basics"))
        path = tmp_path / "failures.json"
        fa.save(path)
        data = json.loads(path.read_text())
        assert data["failures"][0]["lesson"] == "Add more basics"
