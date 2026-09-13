"""Phase 4/5 — Ablation framework and failure taxonomy.

RULE: Freeze benchmark before running. Never tune after seeing results.
RULE: All results are LOCAL_EXPERIMENT.
RULE: Every ablation has an expected_effect stated BEFORE running.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Ablation conditions
# ---------------------------------------------------------------------------

@dataclass
class AblationCondition:
    """One ablation condition — hypothesis stated before running."""
    name:               str
    description:        str
    components_removed: list[str]
    expected_effect:    str           # stated BEFORE running
    result_win_rate:    Optional[float] = None
    result_ci:          Optional[tuple] = None
    observed_effect:    Optional[str]   = None


ABLATION_CONDITIONS: list[AblationCondition] = [
    AblationCondition(
        name="FULL_SYSTEM",
        description="Complete system with all components",
        components_removed=[],
        expected_effect="BEST_PERFORMANCE",
    ),
    AblationCondition(
        name="NO_STRATEGIC_STATE",
        description="Remove game-phase and prize-delta features",
        components_removed=["game_phase", "prize_delta", "board_position"],
        expected_effect="REDUCED_LATE_GAME_PERFORMANCE",
    ),
    AblationCondition(
        name="NO_CARD_FEATURES",
        description="Remove structured card features — type, damage, energy cost",
        components_removed=["card_type_features", "damage_features", "energy_features"],
        expected_effect="REDUCED_TACTICAL_PERFORMANCE",
    ),
    AblationCondition(
        name="TACTICAL_ONLY",
        description="Only immediate damage and KO features",
        components_removed=["strategic_features", "resource_features", "setup_features"],
        expected_effect="GOOD_MIDGAME_POOR_OPENING_ENDGAME",
    ),
    AblationCondition(
        name="PURE_HEURISTIC",
        description="No learned weights — only hand-crafted B6 heuristic",
        components_removed=["learned_weights"],
        expected_effect="MODERATE_PERFORMANCE_INTERPRETABLE",
    ),
    AblationCondition(
        name="NO_OPPONENT_MODEL",
        description="Remove opponent belief features",
        components_removed=["opponent_belief"],
        expected_effect="MINIMAL_EFFECT_OR_IMPROVEMENT",
    ),
    AblationCondition(
        name="RANDOM_BASELINE",
        description="Pure random — lower bound",
        components_removed=["all"],
        expected_effect="WORST_PERFORMANCE",
    ),
]


# ---------------------------------------------------------------------------
# Frozen benchmark specification
# ---------------------------------------------------------------------------

@dataclass
class FrozenBenchmark:
    """Frozen evaluation specification.

    RULE: Define everything before seeing any results.
    RULE: Never modify after freezing.
    """
    benchmark_id:           str
    benchmark_version:      str
    opponent_pool:          list[str]
    deck_pool:              list[str]
    scenario_pool:          list[str]
    num_games_per_condition: int
    randomization_seed:     int
    metrics:                list[str]
    player_order:           str
    frozen_at:              str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_frozen:              bool = False

    def freeze(self) -> None:
        if self.is_frozen:
            raise RuntimeError("Benchmark already frozen — cannot re-freeze")
        self.is_frozen = True
        print(f"[BENCHMARK] {self.benchmark_id} v{self.benchmark_version} FROZEN")
        print("[BENCHMARK] Do not tune model against these results")

    def validate_frozen(self) -> None:
        if not self.is_frozen:
            raise RuntimeError("Benchmark must be frozen before use")

    def to_dict(self) -> dict:
        return {
            "benchmark_id":            self.benchmark_id,
            "benchmark_version":       self.benchmark_version,
            "opponent_pool":           self.opponent_pool,
            "scenario_pool":           self.scenario_pool,
            "num_games_per_condition": self.num_games_per_condition,
            "randomization_seed":      self.randomization_seed,
            "frozen_at":               self.frozen_at,
            "is_frozen":               self.is_frozen,
        }


# ---------------------------------------------------------------------------
# Ablation result
# ---------------------------------------------------------------------------

@dataclass
class AblationResult:
    condition_name:     str
    components_removed: list[str]
    win_rate:           float
    ci_lower:           float
    ci_upper:           float
    mean_turns:         float
    delta_vs_full:      Optional[float] = None
    ci_excludes_zero:   bool            = False
    observed_effect:    str             = ""
    source:             str             = "LOCAL_EXPERIMENT"


# ---------------------------------------------------------------------------
# Run full ablation study
# ---------------------------------------------------------------------------

def run_ablation_study(
    base_agent_factory,
    simulator_factory,
    benchmark:  FrozenBenchmark,
    output_dir: Path,
    conditions: Optional[list[AblationCondition]] = None,
) -> list[AblationResult]:
    """Run full ablation study against a frozen benchmark.

    base_agent_factory(components_removed: list[str]) -> agent
    """
    benchmark.validate_frozen()

    if conditions is None:
        conditions = ABLATION_CONDITIONS

    from ptcgabc.evaluation.evaluator import wilson_confidence_interval

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[AblationResult] = []
    full_wr: Optional[float] = None

    print(f"\n[ABLATION] {len(conditions)} conditions")
    print(f"[ABLATION] Benchmark: {benchmark.benchmark_id} v{benchmark.benchmark_version}")
    print(f"[ABLATION] {benchmark.num_games_per_condition} games/condition")
    print("[ABLATION] Source: LOCAL_EXPERIMENT")

    for cond in conditions:
        print(f"\n  Condition : {cond.name}")
        print(f"  Removed   : {cond.components_removed}")
        print(f"  Expected  : {cond.expected_effect}")

        rng       = random.Random(benchmark.randomization_seed + hash(cond.name) % 1000)
        wins      = 0
        total     = 0
        turn_list: list[int] = []

        for game_num in range(benchmark.num_games_per_condition):
            sim = simulator_factory(seed=rng.randint(0, 2**31))
            obs = sim.get_observation()

            try:
                agent = base_agent_factory(cond.components_removed)
            except Exception:
                from ptcgabc.agents.baselines.baseline_agents import SimpleHeuristicBaseline
                agent = SimpleHeuristicBaseline()

            if hasattr(agent, "reset"):
                agent.reset()

            turns = 0
            while True:
                la = obs.get("legal_actions", [])
                if not la:
                    break

                # Apply ablation to state
                ablated = dict(obs)
                for comp in cond.components_removed:
                    if comp == "game_phase":
                        ablated["game_phase"] = "midgame"
                    elif comp == "prize_delta":
                        ablated["prize_delta"] = 0
                    elif comp == "board_position":
                        ablated.pop("board_position", None)
                    elif comp == "all":
                        ablated = {"legal_actions": la}

                try:
                    idx, _ = agent.select_action(la, ablated, turns)
                    if idx < 0 or idx >= len(la):
                        idx = 0
                except Exception:
                    idx = 0

                obs, done, info = sim.step(idx, la)
                turns += 1
                if done:
                    wins  += int(info.get("winner", 1) == 0)
                    total += 1
                    turn_list.append(turns)
                    break

        wr          = wins / max(1, total)
        ci_lo, ci_hi = wilson_confidence_interval(wins, total)
        mean_turns  = sum(turn_list) / len(turn_list) if turn_list else 0.0

        ar = AblationResult(
            condition_name     =cond.name,
            components_removed =cond.components_removed,
            win_rate           =round(wr, 4),
            ci_lower           =round(ci_lo, 4),
            ci_upper           =round(ci_hi, 4),
            mean_turns         =round(mean_turns, 2),
        )
        if cond.name == "FULL_SYSTEM":
            full_wr = wr
        results.append(ar)
        print(f"  Result    : WR={wr:.1%}  CI=[{ci_lo:.3f},{ci_hi:.3f}]")

    # Delta vs full system
    for r in results:
        if full_wr is not None:
            r.delta_vs_full   = round(r.win_rate - full_wr, 4)
            r.ci_excludes_zero = (r.ci_upper < full_wr) or (r.ci_lower > full_wr)

    # Print table
    print("\n[ABLATION RESULTS]")
    print(f"{'Condition':<30} {'WR':>8} {'CI-lo':>8} {'CI-hi':>8} {'Delta':>8} {'Sig':>5}")
    print("-" * 70)
    for r in sorted(results, key=lambda x: -x.win_rate):
        sig        = "Y" if r.ci_excludes_zero else "-"
        delta_str  = f"{r.delta_vs_full:+.3f}" if r.delta_vs_full is not None else "  N/A"
        print(f"{r.condition_name:<30} {r.win_rate:>8.1%} {r.ci_lower:>8.3f} "
              f"{r.ci_upper:>8.3f} {delta_str:>8} {sig:>5}")

    # Save
    ablation_data = {
        "benchmark_id": benchmark.benchmark_id,
        "source":       "LOCAL_EXPERIMENT",
        "note":         "NOT official Kaggle performance",
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "results": [
            {
                "condition":        r.condition_name,
                "removed":          r.components_removed,
                "win_rate":         r.win_rate,
                "ci_lower":         r.ci_lower,
                "ci_upper":         r.ci_upper,
                "delta_vs_full":    r.delta_vs_full,
                "significant":      r.ci_excludes_zero,
            }
            for r in results
        ],
    }
    out = output_dir / "ablation_results.json"
    out.write_text(json.dumps(ablation_data, indent=2), encoding="utf-8")
    print(f"\n[ABLATION] Results saved -> {out}")

    return results


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

FAILURE_TAXONOMY = [
    "TACTICAL_ERROR",        # wrong attack target, missed KO
    "STRATEGIC_ERROR",       # wrong long-term plan
    "INFORMATION_ERROR",     # wrong inference about opponent
    "SEQUENCING_ERROR",      # wrong action order
    "RESOURCE_MANAGEMENT",   # energy / hand mismanagement
    "OPPONENT_INFERENCE",    # wrong opponent model
    "REWARD_DESIGN",         # policy optimises wrong proxy
    "EXPLORATION",           # exploration causing loss
    "CALIBRATION",           # overconfident / underconfident
    "SIMULATOR_INTERFACE",   # action parsing error
    "DECK_WEAKNESS",         # structural deck problem
    "UNKNOWN",
]


@dataclass
class FailureEvent:
    """A recorded failure for post-hoc analysis."""
    game_id:      str
    turn:         int
    failure_type: str           # from FAILURE_TAXONOMY
    description:  str
    state_summary: dict
    action_taken:  dict
    better_action: Optional[dict] = None
    lesson:        str = ""


class FailureAnalyzer:
    """Records and categorizes failures for Phase 5 analysis."""

    def __init__(self):
        self.failures: list[FailureEvent] = []

    def record(self, failure: FailureEvent) -> None:
        if failure.failure_type not in FAILURE_TAXONOMY:
            failure.failure_type = "UNKNOWN"
        self.failures.append(failure)

    def get_summary(self) -> dict:
        type_counts = Counter(f.failure_type for f in self.failures)
        return {
            "total_failures": len(self.failures),
            "by_type":        dict(type_counts.most_common()),
            "most_common":    type_counts.most_common(1)[0] if type_counts else None,
        }

    def print_analysis(self) -> None:
        summary = self.get_summary()
        print("\n[FAILURE ANALYSIS]")
        print(f"  Total failures: {summary['total_failures']}")
        for ftype, count in summary["by_type"].items():
            pct = count / max(1, summary["total_failures"])
            print(f"  {ftype:<30}: {count:>4} ({pct:.1%})")

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({
            "summary": self.get_summary(),
            "failures": [
                {
                    "game_id":     f.game_id,
                    "turn":        f.turn,
                    "type":        f.failure_type,
                    "description": f.description,
                    "lesson":      f.lesson,
                }
                for f in self.failures
            ],
        }, indent=2), encoding="utf-8")
