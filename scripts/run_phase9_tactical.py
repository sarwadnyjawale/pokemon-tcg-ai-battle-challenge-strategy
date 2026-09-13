"""Phase 9: Tactical Consequence Evaluator Benchmark.

Evaluates the symbolic sequencing consequence logic against the frozen baseline.
"""

import sys
import json
from pathlib import Path
sys.path.insert(0, "src")

from ptcgabc.policy.context_router import ContextRouter
from ptcgabc.policy.card_value import CardValueScorer
from ptcgabc.policy.tempo import TempoScorer
from ptcgabc.policy.action_safety import ActionSafetyGate
from ptcgabc.policy.tactical_consequence import TacticalConsequenceEvaluator
from phase5_utils import run_extended_benchmark

def get_baseline_agent():
    ts = TempoScorer(enable_tracer=False, enable_ability_evaluator=True)
    return ContextRouter(
        card_scorer=CardValueScorer(),
        tempo_scorer=ts,
        safety_gate=ActionSafetyGate(),
    )

def get_tactical_agent_l05():
    ts = TempoScorer(enable_tracer=False, enable_ability_evaluator=True)
    tactical = TacticalConsequenceEvaluator(lambda_weight=0.5)
    return ContextRouter(
        card_scorer=CardValueScorer(),
        tempo_scorer=ts,
        safety_gate=ActionSafetyGate(),
        tactical_scorer=tactical
    )

def get_tactical_agent_l10():
    ts = TempoScorer(enable_tracer=False, enable_ability_evaluator=True)
    tactical = TacticalConsequenceEvaluator(lambda_weight=1.0)
    return ContextRouter(
        card_scorer=CardValueScorer(),
        tempo_scorer=ts,
        safety_gate=ActionSafetyGate(),
        tactical_scorer=tactical
    )

def main():
    print("PHASE 9: Tactical Consequence Pilot (n=20)")
    deck = "pikachu_aggro"
    
    # Smoke test n=20
    res_l10_20 = run_extended_benchmark(get_tactical_agent_l10, "EXP008-L1.0", "random", deck, 20, "EXP008_L10_pilot")
    print(f"Pilot L1.0 -> WR: {res_l10_20.win_rate:.1%} Err: {res_l10_20.legal_errors}")
    
    if res_l10_20.legal_errors > 0:
        print("Legal errors detected! Halting.")
        return

    print("\nPHASE 9: Full Tactical Consequence Benchmark (n=120)")
    out_dir = Path("results/optimization/phase9/tactical")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    n_games = 120
    results = []
    
    # 1. Baseline
    print("Running Baseline vs random...")
    res_base = run_extended_benchmark(get_baseline_agent, "BASELINE", "random", deck, n_games, "Baseline_vs_random")
    results.append(res_base.to_dict())
    print(f"  -> WR: {res_base.win_rate:.1%} CI: [{res_base.ci_lower:.3f}, {res_base.ci_upper:.3f}] Zero-Atk: {res_base.zero_attack_games}/{n_games} Mean Atk: {res_base.mean_attacks:.1f}")

    # 2. Tactical L0.5
    print("\nRunning Tactical L0.5 vs random...")
    res_l05 = run_extended_benchmark(get_tactical_agent_l05, "EXP008-L0.5", "random", deck, n_games, "EXP008_L05_vs_random")
    results.append(res_l05.to_dict())
    print(f"  -> WR: {res_l05.win_rate:.1%} CI: [{res_l05.ci_lower:.3f}, {res_l05.ci_upper:.3f}] Zero-Atk: {res_l05.zero_attack_games}/{n_games} Mean Atk: {res_l05.mean_attacks:.1f}")

    # 3. Tactical L1.0
    print("\nRunning Tactical L1.0 vs random...")
    res_l10 = run_extended_benchmark(get_tactical_agent_l10, "EXP008-L1.0", "random", deck, n_games, "EXP008_L10_vs_random")
    results.append(res_l10.to_dict())
    print(f"  -> WR: {res_l10.win_rate:.1%} CI: [{res_l10.ci_lower:.3f}, {res_l10.ci_upper:.3f}] Zero-Atk: {res_l10.zero_attack_games}/{n_games} Mean Atk: {res_l10.mean_attacks:.1f}")

    # 4. Tactical L1.0 vs first
    print("\nRunning Tactical L1.0 vs first...")
    res_l10_f = run_extended_benchmark(get_tactical_agent_l10, "EXP008-L1.0", "first", deck, n_games, "EXP008_L10_vs_first")
    results.append(res_l10_f.to_dict())
    print(f"  -> WR: {res_l10_f.win_rate:.1%} CI: [{res_l10_f.ci_lower:.3f}, {res_l10_f.ci_upper:.3f}] Zero-Atk: {res_l10_f.zero_attack_games}/{n_games} Mean Atk: {res_l10_f.mean_attacks:.1f}")

    (out_dir / "tactical_benchmark_120.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    
if __name__ == "__main__":
    main()
