"""Phase 5 — Adversarial evaluation suite.

Tests the policy against conditions designed to expose weaknesses.
Every scenario carries:
  - a pre-stated failure_hypothesis (before running)
  - an expected_difficulty rating
  - initial state modifications applied to the mock simulator

RULE: All results are LOCAL_EXPERIMENT — not official Kaggle performance.
RULE: Scenarios defined before seeing any results.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Adversarial scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class AdversarialScenario:
    """One adversarial test condition.

    setup: dict of observation-key overrides applied to the initial state.
    failure_hypothesis: stated BEFORE running — what we expect to see.
    """
    name:                str
    description:         str
    setup:               dict        # initial obs overrides
    expected_difficulty: str         # easy / medium / hard / critical
    failure_hypothesis:  str


ADVERSARIAL_SCENARIOS: list[AdversarialScenario] = [
    AdversarialScenario(
        name="BAD_OPENING",
        description="No energy in opening hand, minimal Pokemon",
        setup={
            "our_hand_count":     2,
            "our_energy_in_play": 0,
            "our_bench_count":    0,
        },
        expected_difficulty="hard",
        failure_hypothesis="Agent cannot set up — may make irreversible early decisions",
    ),
    AdversarialScenario(
        name="SCARCE_RESOURCES",
        description="Empty hand, no energy, one active Pokemon",
        setup={
            "our_hand_count":     0,
            "our_energy_in_play": 1,
            "our_bench_count":    0,
        },
        expected_difficulty="critical",
        failure_hypothesis="Agent forced into suboptimal attacks with no alternatives",
    ),
    AdversarialScenario(
        name="KEY_CARD_LOSS",
        description="Primary attacker KO'd on turn 2",
        setup={
            "our_active_hp_fraction": 0.0,
            "our_bench_count":        1,
        },
        expected_difficulty="hard",
        failure_hypothesis="Agent cannot recover without backup plan",
    ),
    AdversarialScenario(
        name="EARLY_PRIZE_BEHIND",
        description="Down 0-2 prizes by turn 3",
        setup={
            "our_prizes":  6,
            "opp_prizes":  4,
            "prize_delta": 2,
            "turn_number": 3,
        },
        expected_difficulty="hard",
        failure_hypothesis="Agent becomes too aggressive, makes tactical mistakes",
    ),
    AdversarialScenario(
        name="ONE_PRIZE_ENDGAME",
        description="Both players at 1 prize — next KO wins",
        setup={
            "our_prizes":  1,
            "opp_prizes":  1,
            "prize_delta": 0,
            "game_phase":  "endgame",
        },
        expected_difficulty="medium",
        failure_hypothesis="Agent may not prioritize KO correctly under pressure",
    ),
    AdversarialScenario(
        name="UNFAVORABLE_MATCHUP",
        description="Opponent has type advantage — very tanky active",
        setup={
            "opp_active_hp_fraction": 1.0,
            "opp_active_max_hp":      200,
            "our_active_hp_fraction": 0.5,
        },
        expected_difficulty="hard",
        failure_hypothesis="Agent cannot KO opponent efficiently, mismanages tempo",
    ),
    AdversarialScenario(
        name="FORCED_SACRIFICE",
        description="Active Pokemon near KO — only bench target is ex",
        setup={
            "our_active_hp_fraction": 0.1,
            "our_bench_count":        1,
            "opp_is_ex":              1,
        },
        expected_difficulty="medium",
        failure_hypothesis="Agent may not protect prize-sensitive ex on bench",
    ),
]


# ---------------------------------------------------------------------------
# Adversarial evaluation runner
# ---------------------------------------------------------------------------

def run_adversarial_evaluation(
    agent,
    simulator_factory,
    scenarios:          list[AdversarialScenario],
    games_per_scenario: int,
    benchmark_seed:     int,
    output_dir:         Path,
    experiment_id:      str = "P5-ADVERSARIAL-001",
) -> dict:
    """Run adversarial evaluation across all scenarios.

    Returns a dict of scenario_name -> result dict.
    All results labeled LOCAL_EXPERIMENT.
    """
    from ptcgabc.evaluation.evaluator import wilson_confidence_interval

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    print(f"\n[ADVERSARIAL] {experiment_id}")
    print(f"[ADVERSARIAL] Source: LOCAL_EXPERIMENT -- not official Kaggle result")
    print(f"[ADVERSARIAL] {len(scenarios)} scenarios x {games_per_scenario} games each")

    for scenario in scenarios:
        rng  = random.Random(benchmark_seed + hash(scenario.name) % 1000)
        wins = 0
        total = 0

        print(f"\n  Scenario  : {scenario.name}")
        print(f"  Difficulty: {scenario.expected_difficulty}")
        print(f"  Hypothesis: {scenario.failure_hypothesis}")

        for _ in range(games_per_scenario):
            sim = simulator_factory(seed=rng.randint(0, 2**31))
            obs = sim.get_observation()

            # Apply scenario-specific state modifications
            for key, value in scenario.setup.items():
                if key in obs:
                    obs[key] = value

            if hasattr(agent, "reset"):
                agent.reset()

            while True:
                la = obs.get("legal_actions", [])
                if not la:
                    break
                try:
                    idx, _ = agent.select_action(la, obs)
                    if idx < 0 or idx >= len(la):
                        idx = 0
                except Exception:
                    idx = 0

                obs, done, info = sim.step(idx, la)
                if done:
                    wins  += int(info.get("winner", 1) == 0)
                    total += 1
                    break

        wr         = wins / max(1, total)
        ci_lo, ci_hi = wilson_confidence_interval(wins, total)

        results[scenario.name] = {
            "description":        scenario.description,
            "win_rate":           round(wr, 4),
            "ci_lower":           round(ci_lo, 4),
            "ci_upper":           round(ci_hi, 4),
            "games":              total,
            "expected_difficulty": scenario.expected_difficulty,
            "failure_hypothesis": scenario.failure_hypothesis,
        }
        print(f"  Result    : WR={wr:.1%}  CI=[{ci_lo:.3f}, {ci_hi:.3f}]")

    # Summary table
    print(f"\n{'Scenario':<25} {'WR':>8} {'CI':>22} {'Difficulty':>12}")
    print("-" * 72)
    for name, r in sorted(results.items(), key=lambda x: x[1]["win_rate"]):
        ci_str = f"[{r['ci_lower']:.3f}, {r['ci_upper']:.3f}]"
        print(f"{name:<25} {r['win_rate']:>8.1%} {ci_str:>22} {r['expected_difficulty']:>12}")

    # Save
    output = {
        "experiment_id":      experiment_id,
        "source":             "LOCAL_EXPERIMENT",
        "note":               "NOT official Kaggle performance",
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "games_per_scenario": games_per_scenario,
        "results":            results,
    }
    out_path = output_dir / "adversarial_results.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\n[ADVERSARIAL] Results -> {out_path}")

    return results


# ---------------------------------------------------------------------------
# Robustness summary
# ---------------------------------------------------------------------------

def compute_robustness_summary(
    adversarial_results: dict,
    baseline_wr:         float,
) -> dict:
    """Compute robustness metrics from adversarial results.

    robustness_score = mean(scenario WR) / baseline_wr
    A score > 0.9 means the agent loses < 10% relative performance under stress.
    """
    if not adversarial_results:
        return {"robustness_score": 0.0, "worst_scenario": None, "mean_wr": 0.0}

    wrs  = [v["win_rate"] for v in adversarial_results.values()]
    mean = sum(wrs) / len(wrs)
    worst_name = min(adversarial_results, key=lambda k: adversarial_results[k]["win_rate"])

    robustness = mean / max(baseline_wr, 1e-6)

    return {
        "mean_adversarial_wr": round(mean, 4),
        "baseline_wr":         round(baseline_wr, 4),
        "robustness_score":    round(robustness, 4),
        "worst_scenario":      worst_name,
        "worst_wr":            adversarial_results[worst_name]["win_rate"],
        "interpretation": (
            "ROBUST" if robustness >= 0.9 else
            "DEGRADED" if robustness >= 0.7 else
            "FRAGILE"
        ),
    }
