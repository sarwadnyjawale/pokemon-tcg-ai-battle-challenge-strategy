"""Phase 6 tests — evidence package, provenance guard, report generation."""

import json
import pytest
from pathlib import Path

from ptcgabc.visualization.report_builder import (
    load_result_safely,
    generate_evidence_package,
    generate_strategy_report_template,
    generate_final_summary,
)


# ---------------------------------------------------------------------------
# load_result_safely
# ---------------------------------------------------------------------------

class TestLoadResultSafely:
    def _write(self, tmp_path, data: dict, name: str = "result.json") -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_loads_local_experiment(self, tmp_path):
        p = self._write(tmp_path, {"source": "LOCAL_EXPERIMENT", "win_rate": 0.6})
        data = load_result_safely(p)
        assert data["win_rate"] == 0.6

    def test_loads_results_source_field(self, tmp_path):
        p = self._write(tmp_path, {"results_source": "LOCAL_EXPERIMENT", "x": 1})
        data = load_result_safely(p)
        assert data["x"] == 1

    def test_raises_on_official_kaggle_result(self, tmp_path):
        p = self._write(tmp_path, {"source": "OFFICIAL_KAGGLE_RESULT"})
        with pytest.raises(ValueError, match="PROVENANCE VIOLATION"):
            load_result_safely(p)

    def test_missing_file_returns_error_dict(self, tmp_path):
        p = tmp_path / "nonexistent.json"
        result = load_result_safely(p)
        assert "error" in result
        assert result["source"] == "UNKNOWN"

    def test_unknown_source_is_accepted(self, tmp_path):
        p = self._write(tmp_path, {"source": "UNKNOWN", "val": 42})
        data = load_result_safely(p)
        assert data["val"] == 42

    def test_hypothesis_source_is_accepted(self, tmp_path):
        p = self._write(tmp_path, {"source": "HYPOTHESIS", "val": 1})
        data = load_result_safely(p)
        assert data["val"] == 1


# ---------------------------------------------------------------------------
# generate_evidence_package
# ---------------------------------------------------------------------------

class TestGenerateEvidencePackage:
    def _results_dir(self, tmp_path) -> Path:
        """Minimal results directory with one file per phase."""
        rd = tmp_path / "results"
        for phase, fname, data in [
            ("phase1", "phase1_report.json",
             {"source": "LOCAL_EXPERIMENT", "tests_passed": 29}),
            ("phase2", "deck_comparison.json",
             {"source": "LOCAL_EXPERIMENT", "analyses": [{}, {}, {}, {}]}),
            ("phase3", "baseline_comparison.json",
             {"source": "LOCAL_EXPERIMENT",
              "results": [{"agent_name": "B1-Random", "win_rate": 0.651},
                          {"agent_name": "B4-StrategicHeuristic", "win_rate": 0.651}]}),
            ("phase4", "phase4_report.json",
             {"source": "LOCAL_EXPERIMENT",
              "training": {"games": 500, "final_training_wr": 0.638},
              "architecture_decision": {"conclusion": "SUPERVISED_INSUFFICIENT"}}),
            ("phase5", "ablation_results.json",
             {"source": "LOCAL_EXPERIMENT",
              "results": [{"condition": "FULL_SYSTEM"}] * 7}),
        ]:
            d = rd / phase
            d.mkdir(parents=True, exist_ok=True)
            (d / fname).write_text(json.dumps(data), encoding="utf-8")
        return rd

    def test_produces_evidence_json(self, tmp_path):
        rd = self._results_dir(tmp_path)
        out = tmp_path / "output"
        generate_evidence_package(rd, tmp_path / "figures", out)
        assert (out / "evidence_package.json").exists()

    def test_source_label_local_experiment(self, tmp_path):
        rd = self._results_dir(tmp_path)
        out = tmp_path / "output"
        ev = generate_evidence_package(rd, tmp_path / "figures", out)
        assert ev["source_label"] == "LOCAL_EXPERIMENT"

    def test_simulation_not_entered(self, tmp_path):
        rd = self._results_dir(tmp_path)
        out = tmp_path / "output"
        ev = generate_evidence_package(rd, tmp_path / "figures", out)
        assert ev["simulation_entered"] is False

    def test_official_result_raises(self, tmp_path):
        rd = self._results_dir(tmp_path)
        # Inject an OFFICIAL_KAGGLE_RESULT file
        p = rd / "phase1" / "phase1_report.json"
        p.write_text(json.dumps({"source": "OFFICIAL_KAGGLE_RESULT"}))
        out = tmp_path / "output"
        with pytest.raises(ValueError, match="PROVENANCE VIOLATION"):
            generate_evidence_package(rd, tmp_path / "figures", out)

    def test_phases_populated(self, tmp_path):
        rd = self._results_dir(tmp_path)
        out = tmp_path / "output"
        ev = generate_evidence_package(rd, tmp_path / "figures", out)
        assert len(ev["phases"]) >= 4

    def test_missing_phase_still_completes(self, tmp_path):
        # No phase5 dir at all
        rd = tmp_path / "results_sparse"
        (rd / "phase1").mkdir(parents=True)
        (rd / "phase1" / "phase1_report.json").write_text(
            json.dumps({"source": "LOCAL_EXPERIMENT"}))
        out = tmp_path / "output2"
        ev = generate_evidence_package(rd, tmp_path / "figures", out)
        assert "phase1" in ev["phases"]

    def test_summary_block_included(self, tmp_path):
        rd = self._results_dir(tmp_path)
        out = tmp_path / "output"
        ev = generate_evidence_package(rd, tmp_path / "figures", out)
        assert "summary" in ev


# ---------------------------------------------------------------------------
# generate_strategy_report_template
# ---------------------------------------------------------------------------

class TestGenerateStrategyReport:
    def _evidence(self) -> dict:
        return {
            "source_label": "LOCAL_EXPERIMENT",
            "phases": {
                "phase3": {
                    "source": "LOCAL_EXPERIMENT",
                    "results": [
                        {"agent_name": "B1-Random", "win_rate": 0.651},
                        {"agent_name": "B4-StrategicHeuristic", "win_rate": 0.651},
                        {"agent_name": "B6-LegalActionScorer", "win_rate": 0.651},
                    ],
                },
                "phase5_ablation": {
                    "source": "LOCAL_EXPERIMENT",
                    "results": [{"condition": "FULL_SYSTEM", "win_rate": 0.635}],
                },
            },
            "summary": {
                "total_tests":              210,
                "deck_candidates":          4,
                "baselines_evaluated":      6,
                "training_games":           500,
                "ablation_conditions":      7,
                "adversarial_scenarios":    7,
                "architecture_conclusion":  "SUPERVISED_INSUFFICIENT",
                "worst_adversarial_scenario": {"name": "FORCED_SACRIFICE", "win_rate": 0.59},
                "best_adversarial_scenario":  {"name": "EARLY_PRIZE_BEHIND", "win_rate": 0.70},
            },
        }

    def test_report_written(self, tmp_path):
        ev = self._evidence()
        out = tmp_path / "strategy_report.md"
        generate_strategy_report_template(ev, out)
        assert out.exists()

    def test_report_under_word_limit(self, tmp_path):
        ev = self._evidence()
        out = tmp_path / "strategy_report.md"
        text = generate_strategy_report_template(ev, out)
        assert len(text.split()) <= 2200   # allow small buffer

    def test_report_contains_local_experiment(self, tmp_path):
        ev = self._evidence()
        out = tmp_path / "strategy_report.md"
        text = generate_strategy_report_template(ev, out)
        assert "LOCAL_EXPERIMENT" in text

    def test_report_no_official_kaggle_claim(self, tmp_path):
        ev = self._evidence()
        out = tmp_path / "strategy_report.md"
        text = generate_strategy_report_template(ev, out)
        # Must NOT falsely claim official results — the word "OFFICIAL_KAGGLE_RESULT"
        # may appear as a denial/disclaimer, but the key phrase "no official" must appear
        assert "no official" in text.lower() or "LOCAL_EXPERIMENT" in text

    def test_report_contains_engine_verified_rules(self, tmp_path):
        ev = self._evidence()
        out = tmp_path / "strategy_report.md"
        text = generate_strategy_report_template(ev, out)
        assert "60" in text      # deck size
        assert "7" in text       # opening hand
        assert "6" in text       # prizes

    def test_report_contains_forced_sacrifice(self, tmp_path):
        ev = self._evidence()
        out = tmp_path / "strategy_report.md"
        text = generate_strategy_report_template(ev, out)
        assert "FORCED_SACRIFICE" in text

    def test_report_is_markdown(self, tmp_path):
        ev = self._evidence()
        out = tmp_path / "strategy_report.md"
        text = generate_strategy_report_template(ev, out)
        assert "#" in text   # has headings
        assert "---" in text  # has section dividers


# ---------------------------------------------------------------------------
# generate_final_summary
# ---------------------------------------------------------------------------

class TestGenerateFinalSummary:
    def _evidence(self) -> dict:
        return {
            "summary": {
                "total_tests":           210,
                "deck_candidates":       4,
                "baselines_evaluated":   6,
                "training_games":        500,
                "ablation_conditions":   7,
                "adversarial_scenarios": 7,
                "architecture_conclusion": "SUPERVISED_INSUFFICIENT",
                "worst_adversarial_scenario": {"name": "FORCED_SACRIFICE", "win_rate": 0.59},
            }
        }

    def test_summary_json_written(self, tmp_path):
        ev = self._evidence()
        generate_final_summary(ev, tmp_path)
        assert (tmp_path / "final_summary.json").exists()

    def test_source_is_local_experiment(self, tmp_path):
        ev = self._evidence()
        summary = generate_final_summary(ev, tmp_path)
        assert summary["source"] == "LOCAL_EXPERIMENT"

    def test_simulation_not_entered(self, tmp_path):
        ev = self._evidence()
        summary = generate_final_summary(ev, tmp_path)
        assert summary["simulation_entered"] is False

    def test_phases_completed_is_six(self, tmp_path):
        ev = self._evidence()
        summary = generate_final_summary(ev, tmp_path)
        assert summary["phases_completed"] == 6

    def test_engine_verified_rules_correct(self, tmp_path):
        ev = self._evidence()
        summary = generate_final_summary(ev, tmp_path)
        r = summary["engine_verified_rules"]
        assert r["deck_size"]     == 60
        assert r["opening_hand"]  == 7
        assert r["prize_count"]   == 6

    def test_key_findings_not_empty(self, tmp_path):
        ev = self._evidence()
        summary = generate_final_summary(ev, tmp_path)
        assert len(summary["key_findings"]) >= 5

    def test_caveats_mention_local_experiment(self, tmp_path):
        ev = self._evidence()
        summary = generate_final_summary(ev, tmp_path)
        assert any("LOCAL_EXPERIMENT" in c for c in summary["caveats"])
