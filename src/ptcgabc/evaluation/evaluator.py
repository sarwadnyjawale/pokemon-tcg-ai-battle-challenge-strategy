"""Phase 3 — Evaluation harness for all baseline agents.

RULE: Results labeled LOCAL_EXPERIMENT — never claimed as official Kaggle results.
RULE: Confidence intervals always reported.
RULE: Multiple opponent conditions evaluated.
RULE: EvaluationConfig frozen before seeing results.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------

@dataclass
class GameResult:
    game_id:              str
    winner:               int   # 0 = us, 1 = opponent
    turns:                int
    our_prizes:           int
    opp_prizes:           int
    legal_errors:         int
    catastrophic_errors:  int
    action_history:       list  = field(default_factory=list)
    end_reason:           str   = ""


@dataclass
class EvaluationConfig:
    """Frozen evaluation configuration.

    RULE: Define before seeing results. Do NOT tune post-hoc.
    """

    experiment_id:          str
    agent_name:             str
    opponent_name:          str
    deck_name:              str
    opponent_deck:          str
    num_games:              int
    randomization_seed:     int
    player_order:           str       # "first" | "second" | "alternating"
    game_state_conditions:  list[str]
    metrics:                list[str]
    timestamp:              str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    frozen:                 bool = False

    def freeze(self) -> None:
        self.frozen = True
        print(f"[EVAL] Config {self.experiment_id} FROZEN — results binding")

    def to_dict(self) -> dict:
        return {
            "experiment_id":         self.experiment_id,
            "agent_name":            self.agent_name,
            "opponent_name":         self.opponent_name,
            "deck_name":             self.deck_name,
            "num_games":             self.num_games,
            "randomization_seed":    self.randomization_seed,
            "player_order":          self.player_order,
            "conditions":            self.game_state_conditions,
            "frozen":                self.frozen,
        }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def wilson_confidence_interval(
    wins:       int,
    total:      int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Wilson score interval for binomial proportions.

    Preferred over naïve ±SE for small samples.
    """
    if total == 0:
        return 0.0, 1.0
    z     = 1.96 if confidence == 0.95 else 1.645
    p_hat = wins / total
    n     = total
    center = (p_hat + z**2 / (2 * n)) / (1 + z**2 / n)
    margin = (z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))) / (1 + z**2 / n)
    return max(0.0, center - margin), min(1.0, center + margin)


def required_sample_size(
    expected_win_rate: float = 0.55,
    baseline_win_rate: float = 0.50,
    alpha:             float = 0.05,
    power:             float = 0.80,
) -> int:
    """Required games to detect a given effect size at given power."""
    p1 = baseline_win_rate
    p2 = expected_win_rate
    z_alpha = 1.96
    z_beta  = 0.84
    p_bar   = (p1 + p2) / 2
    num     = (z_alpha * math.sqrt(2 * p_bar * (1 - p_bar)) +
               z_beta  * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    denom   = (p2 - p1) ** 2
    return math.ceil(num / denom)


# ---------------------------------------------------------------------------
# Aggregate results
# ---------------------------------------------------------------------------

@dataclass
class EvaluationResults:
    """Complete evaluation results. Always labeled LOCAL_EXPERIMENT."""

    experiment_id:   str
    config:          EvaluationConfig
    results_source:  str = "LOCAL_EXPERIMENT"   # NEVER change to OFFICIAL

    total_games: int   = 0
    wins:        int   = 0
    losses:      int   = 0
    draws:       int   = 0

    win_rate: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0

    mean_turns:              float = 0.0
    legal_error_rate:        float = 0.0
    catastrophic_error_rate: float = 0.0

    first_player_wr:  float = 0.0
    second_player_wr: float = 0.0
    phase_breakdown:  dict  = field(default_factory=dict)

    game_records: list[GameResult] = field(default_factory=list)
    timestamp:    str              = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_summary(self) -> None:
        if self.total_games == 0:
            return
        self.win_rate = self.wins / self.total_games
        self.ci_lower, self.ci_upper = wilson_confidence_interval(
            self.wins, self.total_games)
        if self.game_records:
            self.mean_turns = sum(g.turns for g in self.game_records) / len(self.game_records)
            self.legal_error_rate = (
                sum(g.legal_errors for g in self.game_records) / self.total_games)
            self.catastrophic_error_rate = (
                sum(g.catastrophic_errors for g in self.game_records) / self.total_games)

    def print_summary(self) -> None:
        print(f"\n[RESULT] {self.experiment_id}")
        print(f"  Source      : {self.results_source}  <- NOT an official Kaggle result")
        print(f"  Games       : {self.total_games}")
        print(f"  Wins        : {self.wins} ({self.win_rate:.1%})")
        print(f"  95% CI      : [{self.ci_lower:.3f}, {self.ci_upper:.3f}]")
        print(f"  Mean turns  : {self.mean_turns:.1f}")
        print(f"  Legal errors: {self.legal_error_rate:.3f}/game")
        print(f"  Catastrophic: {self.catastrophic_error_rate:.3f}/game")

    def to_dict(self) -> dict:
        return {
            "experiment_id":           self.experiment_id,
            "results_source":          self.results_source,
            "timestamp":               self.timestamp,
            "total_games":             self.total_games,
            "wins":                    self.wins,
            "losses":                  self.losses,
            "win_rate":                round(self.win_rate, 4),
            "ci_lower":                round(self.ci_lower, 4),
            "ci_upper":                round(self.ci_upper, 4),
            "mean_turns":              round(self.mean_turns, 2),
            "legal_error_rate":        round(self.legal_error_rate, 4),
            "catastrophic_error_rate": round(self.catastrophic_error_rate, 4),
            "first_player_wr":         round(self.first_player_wr, 4),
            "second_player_wr":        round(self.second_player_wr, 4),
        }


# ---------------------------------------------------------------------------
# Mock Simulator
# ---------------------------------------------------------------------------

class MockSimulator:
    """Mock simulator for testing and baseline evaluation.

    Returns plausible but synthetic game states and legal actions.
    REPLACE with the actual competition simulator for real experiments.
    All results from this simulator are LOCAL_EXPERIMENT only.
    """

    MOCK_ACTIONS = [
        {"type": "attack",        "name": "Thunder Shock",         "damage": 30,  "energy_cost": 1},
        {"type": "attack",        "name": "Circle Circuit",        "damage": 60,  "energy_cost": 2},
        {"type": "attach_energy", "name": "Attach Lightning"},
        {"type": "play_trainer",  "name": "Professor's Research",  "effect_category": "draw"},
        {"type": "play_trainer",  "name": "Ultra Ball",            "effect_category": "search"},
        {"type": "play_pokemon",  "name": "Pikachu ex"},
        {"type": "retreat",       "name": "Retreat"},
        {"type": "pass",          "name": "End Turn"},
    ]

    _PHASE_MAP = {0: "opening", 1: "early", 2: "midgame", 3: "late", 4: "endgame"}

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.reset()

    def reset(self) -> None:
        self.turn       = 0
        self.our_prizes = 6   # engine-verified
        self.opp_prizes = 6
        self.game_over  = False

    def get_observation(self) -> dict:
        n_actions    = self.rng.randint(2, 5)
        legal_subset = self.rng.sample(self.MOCK_ACTIONS, min(n_actions, len(self.MOCK_ACTIONS)))
        legal_subset = [dict(a) for a in legal_subset]
        phase        = self._PHASE_MAP[min(self.turn // 3, 4)]

        return {
            "turn_number":              self.turn,
            "game_phase":               phase,
            "our_prizes":               self.our_prizes,
            "opp_prizes":               self.opp_prizes,
            "our_active_hp_fraction":   self.rng.uniform(0.4, 1.0),
            "opp_active_hp_fraction":   self.rng.uniform(0.3, 1.0),
            "opp_active_max_hp":        120,
            "our_active_max_hp":        100,
            "opp_is_ex":                int(self.rng.random() < 0.3),
            "our_hand_count":           self.rng.randint(1, 6),
            "our_bench_count":          self.rng.randint(0, 3),
            "prize_delta":              self.our_prizes - self.opp_prizes,
            "our_energy_in_play":       self.rng.randint(0, 4),
            "our_active_damage":        self.rng.randint(0, 60),
            "opp_active_damage":        self.rng.randint(0, 60),
            "legal_actions":            legal_subset,
        }

    def step(
        self,
        action_index: int,
        legal_actions: list,
    ) -> tuple[dict, bool, dict]:
        self.turn += 1

        if self.rng.random() < 0.15:
            self.opp_prizes -= 1
        if self.rng.random() < 0.12:
            self.our_prizes -= 1

        if self.opp_prizes <= 0:
            self.game_over = True
            return {}, True, {"winner": 0, "reason": "prizes_exhausted"}
        if self.our_prizes <= 0:
            self.game_over = True
            return {}, True, {"winner": 1, "reason": "prizes_exhausted"}
        if self.turn >= 40:
            self.game_over = True
            winner = 0 if self.our_prizes <= self.opp_prizes else 1
            return {}, True, {"winner": winner, "reason": "max_turns"}

        return self.get_observation(), False, {"winner": None}


# ---------------------------------------------------------------------------
# Core evaluation loop
# ---------------------------------------------------------------------------

def run_evaluation(
    agent,
    config:            EvaluationConfig,
    simulator_factory,
    output_dir:        Path,
) -> EvaluationResults:
    """Run a complete evaluation of an agent."""
    config.freeze()
    results = EvaluationResults(experiment_id=config.experiment_id, config=config)

    rng = random.Random(config.randomization_seed)
    first_wins:  list[int] = []
    second_wins: list[int] = []

    print(f"\n[EVAL] {config.num_games} games: {config.agent_name} vs {config.opponent_name}")
    print(f"[EVAL] {results.results_source} — not an official Kaggle result")

    t0 = time.time()

    for game_num in range(config.num_games):
        sim = simulator_factory(seed=rng.randint(0, 2**31))
        obs = sim.get_observation()
        agent.reset()

        turns               = 0
        legal_errors        = 0
        catastrophic_errors = 0
        is_first = (game_num % 2 == 0) if config.player_order == "alternating" \
                   else (config.player_order == "first")

        while True:
            legal_actions = obs.get("legal_actions", [])
            if not legal_actions:
                legal_errors += 1
                break

            try:
                action_idx, reason = agent.select_action(legal_actions, obs, turns)
            except Exception as e:
                legal_errors += 1
                action_idx = 0

            if action_idx < 0 or action_idx >= len(legal_actions):
                legal_errors += 1
                catastrophic_errors += 1
                action_idx = 0

            obs, done, info = sim.step(action_idx, legal_actions)
            turns += 1

            if done:
                winner = info.get("winner", 1)
                won    = (winner == 0)
                results.total_games += 1
                if won:
                    results.wins += 1
                    (first_wins if is_first else second_wins).append(1)
                else:
                    results.losses += 1
                    (first_wins if is_first else second_wins).append(0)

                results.game_records.append(GameResult(
                    game_id             =f"{config.experiment_id}-G{game_num:04d}",
                    winner              =winner,
                    turns               =turns,
                    our_prizes          =sim.our_prizes,
                    opp_prizes          =sim.opp_prizes,
                    legal_errors        =legal_errors,
                    catastrophic_errors =catastrophic_errors,
                    end_reason          =info.get("reason", "unknown"),
                ))
                break

        step = max(1, config.num_games // 10)
        if (game_num + 1) % step == 0:
            wr = results.wins / max(1, results.total_games)
            print(f"  [{(game_num+1)/config.num_games:.0%}] Games={game_num+1} WR={wr:.1%} "
                  f"t={time.time()-t0:.1f}s")

    results.compute_summary()
    if first_wins:
        results.first_player_wr  = sum(first_wins)  / len(first_wins)
    if second_wins:
        results.second_player_wr = sum(second_wins) / len(second_wins)

    results.print_summary()

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{config.experiment_id}_results.json"
    out.write_text(json.dumps(results.to_dict(), indent=2), encoding="utf-8")
    print(f"[EVAL] -> {out}  (elapsed {time.time()-t0:.1f}s)")

    return results


# ---------------------------------------------------------------------------
# Run all baselines
# ---------------------------------------------------------------------------

def run_all_baselines(
    output_dir: Path,
    num_games:  Optional[int] = None,
) -> list[EvaluationResults]:
    """Run all Phase-3 baseline agents and write comparison JSON."""
    from ptcgabc.agents.baselines.baseline_agents import (
        SimulatorOrderBaseline, RandomBaseline,
        SimpleHeuristicBaseline, TacticalGreedyBaseline,
        StrategicHeuristicBaseline,
    )
    from ptcgabc.agents.baselines.legal_action_scorer import LegalActionScorerAgent

    if num_games is None:
        num_games = max(100, required_sample_size(0.55, 0.50))
        print(f"\n[EVAL] Statistical sample size: {num_games} games "
              f"(55% vs 50% at 80% power, 95% CI)")

    agents = [
        (SimulatorOrderBaseline(), "B0-SimulatorOrder"),
        (RandomBaseline(seed=42),  "B1-Random"),
        (SimpleHeuristicBaseline(), "B2-SimpleHeuristic"),
        (TacticalGreedyBaseline(),  "B3-TacticalGreedy"),
        (StrategicHeuristicBaseline(), "B4-StrategicHeuristic"),
        (LegalActionScorerAgent(),  "B6-LegalActionScorer"),
    ]

    all_results: list[EvaluationResults] = []

    for agent, agent_name in agents:
        config = EvaluationConfig(
            experiment_id         =f"P3-{agent_name.upper().replace('-','_')}-001",
            agent_name            =agent_name,
            opponent_name         ="MockRandom",
            deck_name             ="PikachuExAggro-CANDIDATE",
            opponent_deck         ="Random",
            num_games             =num_games,
            randomization_seed    =12345,
            player_order          ="alternating",
            game_state_conditions =["standard_mock"],
            metrics               =["win_rate", "ci", "legal_errors", "catastrophic_errors"],
        )
        res = run_evaluation(
            agent             =agent,
            config            =config,
            simulator_factory =lambda seed: MockSimulator(seed=seed),
            output_dir        =output_dir,
        )
        all_results.append(res)

    # Comparison table
    print("\n[BASELINE COMPARISON]")
    print(f"{'Agent':<32} {'WR':>8} {'CI-lo':>8} {'CI-hi':>8} {'LErr':>8}")
    print("-" * 72)
    for r in all_results:
        print(f"{r.config.agent_name:<32} {r.win_rate:>8.1%} "
              f"{r.ci_lower:>8.3f} {r.ci_upper:>8.3f} {r.legal_error_rate:>8.3f}")

    comparison = {
        "experiment":      "P3-BASELINE-COMPARISON-001",
        "source":          "LOCAL_EXPERIMENT",
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "games_per_agent": num_games,
        "note":            "Mock simulator — not official Kaggle performance",
        "results":         [r.to_dict() for r in all_results],
    }
    cmp_path = output_dir / "baseline_comparison.json"
    cmp_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(f"\n[EVAL] Comparison written -> {cmp_path}")

    return all_results
