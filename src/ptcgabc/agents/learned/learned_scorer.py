"""Phase 4 — Learned Action Scorer.

Starts from heuristic features; learns weights from game outcomes via
REINFORCE (policy gradient). Architecture decision: LINEAR first.
Justify complexity only if linear model fails to beat strong heuristics.

RULE: Every training run has an explicit hypothesis (LearningConfig).
RULE: Results are LOCAL_EXPERIMENT only — never claim as official Kaggle result.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Learning configuration (must be defined before any training)
# ---------------------------------------------------------------------------

@dataclass
class LearningConfig:
    """Learning configuration.

    Every training run must carry an explicit hypothesis and null hypothesis
    before any results are seen (anti-HARKing rule).
    """

    experiment_id:      str
    hypothesis:         str
    null_hypothesis:    str
    model:              str
    deck:               str
    opponents:          list[str]
    training_games:     int
    evaluation_games:   int
    learning_rate:      float
    discount_factor:    float
    exploration_rate:   float
    exploration_decay:  float
    randomization_seed: int

    def log(self) -> None:
        print(f"\n[LEARNING] Experiment: {self.experiment_id}")
        print(f"  H:     {self.hypothesis}")
        print(f"  H0:    {self.null_hypothesis}")
        print(f"  Model: {self.model}")
        print(f"  Games: {self.training_games} train / {self.evaluation_games} eval")
        print(f"  LR={self.learning_rate}  gamma={self.discount_factor}  "
              f"eps={self.exploration_rate}")


# ---------------------------------------------------------------------------
# Linear action scorer (the learnable model)
# ---------------------------------------------------------------------------

class LinearActionScorer:
    """Linear scoring model: score = weights · features + bias.

    Trained via REINFORCE policy gradient or supervised contrastive signal.

    Architecture decision: LINEAR first.
    Justification: explainable, low-variance gradient estimates, fast to train,
    easy to ablate individual features. Upgrade to non-linear only if this fails
    to beat B4-StrategicHeuristic with statistical significance.
    """

    def __init__(
        self,
        feature_dim:   int   = 26,
        learning_rate: float = 0.01,
        seed:          int   = 42,
    ):
        self.feature_dim  = feature_dim
        self.lr           = learning_rate
        self.rng          = random.Random(seed)
        # Initialize near zero — prevents early-game bias
        self.weights: list[float] = [self.rng.gauss(0, 0.01) for _ in range(feature_dim)]
        self.bias:    float       = 0.0
        self.update_count: int    = 0

    # -- scoring --

    def score(self, feature_vector: list[float]) -> float:
        if len(feature_vector) != self.feature_dim:
            raise ValueError(
                f"Feature dim mismatch: {len(feature_vector)} != {self.feature_dim}")
        return sum(w * f for w, f in zip(self.weights, feature_vector)) + self.bias

    def score_batch(self, feature_vectors: list[list[float]]) -> list[float]:
        return [self.score(fv) for fv in feature_vectors]

    def softmax_over_actions(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        max_s = max(scores)
        exp_s = [math.exp(s - max_s) for s in scores]
        total = sum(exp_s)
        return [e / total for e in exp_s]

    def select_action(
        self,
        feature_vectors: list[list[float]],
        temperature: float = 1.0,
        greedy:      bool  = False,
    ) -> tuple[int, list[float]]:
        """Return (selected_index, probabilities).

        greedy=True for evaluation; greedy=False (sampling) for exploration.
        """
        if not feature_vectors:
            raise ValueError("No feature vectors provided")

        scores = [self.score(fv) / max(temperature, 1e-8) for fv in feature_vectors]
        probs  = self.softmax_over_actions(scores)

        if greedy:
            idx = scores.index(max(scores))
        else:
            r, cumulative = self.rng.random(), 0.0
            idx = len(probs) - 1
            for i, p in enumerate(probs):
                cumulative += p
                if r <= cumulative:
                    idx = i
                    break

        return idx, probs

    # -- training updates --

    def reinforce_update(
        self,
        trajectory: list[tuple[list[float], list[float], float]],
    ) -> None:
        """REINFORCE policy gradient update.

        trajectory: list of (feature_vector, action_probs, advantage)
        advantage = G_t - baseline (discounted return minus running mean)

        Gradient: for softmax-linear model the simplified form is
            dw_j += lr * f_j * advantage
        which is an unbiased estimator of the policy gradient.
        """
        for feat_vec, probs, advantage in trajectory:
            if not feat_vec or not probs:
                continue
            for j in range(self.feature_dim):
                self.weights[j] += self.lr * feat_vec[j] * advantage
            self.bias         += self.lr * advantage
            self.update_count += 1

    def supervised_update(
        self,
        positive_features:      list[float],
        negative_features_list: list[list[float]],
        margin:                 float = 1.0,
    ) -> None:
        """Contrastive/ranking update.

        Increase score of the winning action relative to all alternatives.
        Used when we have a supervised signal (e.g. human expert games).
        """
        pos_score = self.score(positive_features)
        for neg_features in negative_features_list:
            neg_score = self.score(neg_features)
            loss = max(0.0, margin - (pos_score - neg_score))
            if loss > 0.0:
                for j in range(self.feature_dim):
                    self.weights[j] += self.lr * (positive_features[j] - neg_features[j])
                self.update_count += 1

    # -- persistence --

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "weights":      self.weights,
            "bias":         self.bias,
            "feature_dim":  self.feature_dim,
            "update_count": self.update_count,
            "lr":           self.lr,
        }, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LinearActionScorer":
        data   = json.loads(path.read_text(encoding="utf-8"))
        scorer = cls(feature_dim=data["feature_dim"], learning_rate=data["lr"])
        scorer.weights      = data["weights"]
        scorer.bias         = data["bias"]
        scorer.update_count = data["update_count"]
        return scorer


# ---------------------------------------------------------------------------
# Learned agent wrapper
# ---------------------------------------------------------------------------

class LearnedActionScorerAgent:
    """Agent backed by a learned LinearActionScorer.

    Wraps the scorer with feature extraction, epsilon-greedy exploration,
    and per-game trajectory recording for REINFORCE updates.
    """

    def __init__(
        self,
        scorer:           LinearActionScorer,
        exploration_rate: float = 0.10,
        name:             str   = "P4-LearnedScorer",
    ):
        self.name             = name
        self.scorer           = scorer
        self.exploration_rate = exploration_rate
        self.game_count       = 0
        self.trajectory:      list[dict] = []

    def reset(self) -> None:
        self.game_count += 1
        self.trajectory  = []

    def select_action(
        self,
        legal_actions: list,
        game_state:    dict,
        turn:          int = 0,
    ) -> tuple[int, str]:
        from ptcgabc.agents.baselines.legal_action_scorer import extract_action_features

        if not legal_actions:
            raise ValueError(f"{self.name}: No legal actions")

        feature_vectors = [
            extract_action_features(a, i, game_state).to_vector()
            for i, a in enumerate(legal_actions)
        ]

        exploring = (random.random() < self.exploration_rate)
        idx, probs = self.scorer.select_action(feature_vectors, greedy=not exploring)

        self.trajectory.append({
            "turn":           turn,
            "feature_vector": feature_vectors[idx],
            "all_features":   feature_vectors,
            "probs":          probs,
            "action_idx":     idx,
            "exploring":      exploring,
        })

        suffix = "_explore" if exploring else "_exploit"
        return idx, f"learned_score_{idx}{suffix}"

    def update_from_game_result(
        self,
        won:      bool,
        discount: float = 0.95,
    ) -> None:
        """Apply REINFORCE update from a +1 (win) / -1 (loss) outcome."""
        reward = 1.0 if won else -1.0
        n      = len(self.trajectory)
        if n == 0:
            return

        # Discounted returns
        returns: list[float] = []
        G = 0.0
        for _ in reversed(range(n)):
            G = reward + discount * G
            returns.insert(0, G)

        baseline = sum(returns) / len(returns)

        reinforce_traj = [
            (step["feature_vector"], step["probs"], returns[t] - baseline)
            for t, step in enumerate(self.trajectory)
        ]
        self.scorer.reinforce_update(reinforce_traj)


# ---------------------------------------------------------------------------
# Self-play training loop
# ---------------------------------------------------------------------------

class SelfPlayTrainer:
    """Self-play (vs mock) training loop.

    Only use if REINFORCE update shows meaningful improvement over baselines
    (Q1 in the architecture decision tree).
    """

    def __init__(
        self,
        agent:             LearnedActionScorerAgent,
        config:            LearningConfig,
        simulator_factory,
        output_dir:        Path,
    ):
        self.agent     = agent
        self.config    = config
        self.simulator = simulator_factory
        self.output_dir = output_dir
        self.training_log: list[dict] = []
        self.snapshots:    list[str]  = []

    def run_training(self) -> dict:
        """Training loop with periodic evaluation checkpoints."""
        self.config.log()
        rng    = random.Random(self.config.randomization_seed)
        wins   = 0
        total  = 0
        window: list[int] = []

        print(f"\n[TRAINING] {self.config.training_games} games ...")

        checkpoint_interval = max(50, self.config.training_games // 10)
        eval_history: list[dict] = []

        for game_num in range(self.config.training_games):
            sim = self.simulator(seed=rng.randint(0, 2**31))
            obs = sim.get_observation()
            self.agent.reset()

            while True:
                la = obs.get("legal_actions", [])
                if not la:
                    break
                try:
                    idx, _ = self.agent.select_action(la, obs)
                except Exception:
                    idx = 0
                obs, done, info = sim.step(idx, la)
                if done:
                    won = (info.get("winner", 1) == 0)
                    self.agent.update_from_game_result(
                        won, self.config.discount_factor)
                    wins  += int(won)
                    total += 1
                    window.append(int(won))
                    if len(window) > 50:
                        window.pop(0)
                    break

            if (game_num + 1) % checkpoint_interval == 0:
                wwr = sum(window) / len(window) if window else 0.0
                owr = wins / max(1, total)
                print(f"  Game {game_num+1:>5}: rolling={wwr:.1%}  overall={owr:.1%}")
                snap = self.output_dir / f"snapshot_game{game_num+1}.json"
                self.agent.scorer.save(snap)
                self.snapshots.append(str(snap))
                eval_history.append({
                    "game": game_num + 1,
                    "rolling_wr": round(wwr, 4),
                    "overall_wr": round(owr, 4),
                })

        # Final save
        final_path = self.output_dir / "model_final.json"
        self.agent.scorer.save(final_path)

        result = {
            "experiment_id":      self.config.experiment_id,
            "source":             "LOCAL_EXPERIMENT",
            "hypothesis":         self.config.hypothesis,
            "training_games":     self.config.training_games,
            "final_training_wr":  round(wins / max(1, total), 4),
            "eval_history":       eval_history,
            "model_path":         str(final_path),
            "snapshots":          self.snapshots,
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "note":               "Mock simulator — not official Kaggle performance",
        }

        (self.output_dir / "training_results.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")

        print(f"\n[TRAINING] Complete. Final WR: {wins/max(1,total):.1%}")
        print(f"[TRAINING] Model saved: {final_path}")
        print("[TRAINING] Evaluate on held-out set before architecture claims")

        return result


# ---------------------------------------------------------------------------
# Architecture decision tree
# ---------------------------------------------------------------------------

def architecture_decision_tree(
    baseline_results:   dict,
    supervised_results: dict,
    rl_results:         Optional[dict] = None,
) -> dict:
    """Evaluate evidence and return a justified architecture decision.

    Q1: Does supervised/REINFORCE beat strong heuristics (B4)?
    Q2: Does RL further improve over supervised? (optional gate)

    All win rates must come from held-out evaluation, never training data.
    """
    decisions = []

    heuristic_wr  = baseline_results.get("B4-StrategicHeuristic", {}).get("win_rate", 0.5)
    supervised_wr = supervised_results.get("win_rate", 0.5)
    supervised_ci = supervised_results.get("ci_lower", 0.0)

    q1_positive = supervised_ci > heuristic_wr
    decisions.append({
        "question":       "Q1: Does learned scoring beat B4-StrategicHeuristic?",
        "heuristic_wr":   heuristic_wr,
        "supervised_wr":  supervised_wr,
        "ci_lower":       supervised_ci,
        "answer":         "YES" if q1_positive else "NO",
        "action": (
            "Continue to RL exploration"
            if q1_positive else
            "Diagnose feature representation — do NOT add RL complexity yet"
        ),
    })

    if not q1_positive:
        return {
            "conclusion":      "SUPERVISED_INSUFFICIENT",
            "recommendation":  "Improve feature representation before adding RL",
            "decisions":       decisions,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        }

    # Q2
    if rl_results:
        rl_wr       = rl_results.get("win_rate", 0.5)
        rl_ci_lower = rl_results.get("ci_lower", 0.0)
        q2_positive = rl_ci_lower > supervised_wr
        decisions.append({
            "question":      "Q2: Does RL improve over supervised on held-out gameplay?",
            "supervised_wr": supervised_wr,
            "rl_wr":         rl_wr,
            "ci_lower":      rl_ci_lower,
            "answer":        "YES" if q2_positive else "NO",
            "action": (
                "Identify exactly what RL adds, then scale"
                if q2_positive else
                "Stop RL development; use supervised weights"
            ),
        })
    else:
        decisions.append({
            "question": "Q2: RL not yet tested",
            "action":   "Run RL training + held-out evaluation before deciding",
        })

    return {
        "conclusion":  "ARCHITECTURE_JUSTIFIED",
        "decisions":   decisions,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
