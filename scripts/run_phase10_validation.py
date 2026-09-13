"""Validation Script for EXP-008 vs EXP-005."""

import sys
import json
from pathlib import Path
import random
sys.path.insert(0, "src")

from ptcgabc.policy.context_router import ContextRouter
from ptcgabc.policy.card_value import CardValueScorer
from ptcgabc.policy.tempo import TempoScorer
from ptcgabc.policy.action_safety import ActionSafetyGate
from ptcgabc.policy.tactical_consequence import TacticalConsequenceEvaluator
from ptcgabc.environment.enriched_adapter import run_instrumented_game
from ptcgabc.environment.cabt_adapter import CabtGame

def get_exp005():
    ts = TempoScorer(enable_tracer=False, enable_ability_evaluator=True)
    return ContextRouter(
        card_scorer=CardValueScorer(),
        tempo_scorer=ts,
        safety_gate=ActionSafetyGate(),
    )

def get_exp008():
    ts = TempoScorer(enable_tracer=False, enable_ability_evaluator=True)
    tactical = TacticalConsequenceEvaluator(lambda_weight=1.0)
    return ContextRouter(
        card_scorer=CardValueScorer(),
        tempo_scorer=ts,
        safety_gate=ActionSafetyGate(),
        tactical_scorer=tactical
    )

def main():
    print("Running Paired Validation: EXP-005 vs EXP-008 (n=50)")
    n_games = 50
    deck = "pikachu_aggro"
    seeds = [42 + i for i in range(n_games)]
    
    from ptcgabc.deck.candidates import build_pikachu_aggro
    deck_list = []
    for c in build_pikachu_aggro(): deck_list.extend([int(c.card_id)]*c.count)

    from ptcgabc.environment.enriched_adapter import _load_card_db
    card_db = _load_card_db()

    exp005_episodes = []
    exp008_episodes = []
    
    for i, s in enumerate(seeds):
        import random
        random.seed(s)
        ep5 = run_instrumented_game(get_exp005(), "random", deck_list, f"EXP005-{i}", card_db=card_db)
        exp005_episodes.append(ep5)
        
        random.seed(s)
        ep8 = run_instrumented_game(get_exp008(), "random", deck_list, f"EXP008-{i}", card_db=card_db)
        exp008_episodes.append(ep8)
        
        if (i+1) % 10 == 0:
            print(f"  Processed {i+1}/{n_games} games...")

    # Calculate metrics
    def calc_metrics(eps):
        wins = sum(1 for e in eps if e.winner == 0)
        attacks = sum(sum(1 for d in e.decisions if d.chosen_action_type == "attack") for e in eps) / n_games
        zero_atk = sum(1 for e in eps if sum(1 for d in e.decisions if d.chosen_action_type == "attack") == 0)
        return wins/n_games, attacks, zero_atk

    wr5, atk5, z5 = calc_metrics(exp005_episodes)
    wr8, atk8, z8 = calc_metrics(exp008_episodes)

    print(f"\nEXP-005: WR={wr5:.1%}  MeanAtk={atk5:.1f}  ZeroAtk={z5}/{n_games}")
    print(f"EXP-008: WR={wr8:.1%}  MeanAtk={atk8:.1f}  ZeroAtk={z8}/{n_games}")

    # Action Diff
    disagreements = 0
    disagreements_by_type = {}
    total_comparable_decisions = 0
    
    for ep5, ep8 in zip(exp005_episodes, exp008_episodes):
        # Only compare up to the point they diverge
        min_len = min(len(ep5.decisions), len(ep8.decisions))
        for d_idx in range(min_len):
            d5 = ep5.decisions[d_idx]
            d8 = ep8.decisions[d_idx]
            if d5.select_context != d8.select_context or d5.option_count != d8.option_count:
                break # Diverged in state
                
            total_comparable_decisions += 1
            if d5.chosen_index != d8.chosen_index:
                disagreements += 1
                t5 = d5.chosen_action_type
                t8 = d8.chosen_action_type
                pair = f"{t5} -> {t8}"
                disagreements_by_type[pair] = disagreements_by_type.get(pair, 0) + 1
                break # Stop comparing this game after first divergence

    print(f"\nTotal comparable decision branches before divergence: {total_comparable_decisions}")
    print(f"First-divergence Disagreements: {disagreements}")
    for pair, count in sorted(disagreements_by_type.items(), key=lambda x: -x[1]):
        print(f"  {pair}: {count}")

    # Save validation
    out_dir = Path("results/optimization/tactical_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "paired_validation.json"
    
    json.dump({
        "n_games": n_games,
        "exp005": {"wr": wr5, "mean_atk": atk5, "zero_atk": z5},
        "exp008": {"wr": wr8, "mean_atk": atk8, "zero_atk": z8},
        "disagreements": disagreements,
        "disagreements_by_type": disagreements_by_type
    }, out_file.open("w"), indent=2)

if __name__ == "__main__":
    main()
