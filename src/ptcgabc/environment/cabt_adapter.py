"""CABT Adapter — Main game loop integrating real kaggle-environments cabt env.

This module provides:
  - CabtGame: runs a complete game using the real cabt engine
  - CabtSelfPlayRunner: runs N games between two agents and collects results
  - CabtGameResult: structured result from a real CABT game

RULES:
  - Never substitute MockSimulator here. If cabt is unavailable, fail explicitly.
  - All results labeled REAL_CABT_LOCAL, never OFFICIAL_KAGGLE_RESULT.
  - Only fields from real CABT observations reach the policy.
  - MockSimulator remains untouched in ptcgabc.evaluation.evaluator.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .cabt_observation_parser import (
    parse_observation, build_feature_dict, extract_legal_options, CabtGameState,
)
from .cabt_action_adapter import agent_to_cabt_action, build_deck_action


# ---------------------------------------------------------------------------
# Availability check (fail explicitly, never silently fall back to mock)
# ---------------------------------------------------------------------------

def check_cabt_available() -> bool:
    """Return True if the real cabt environment can be created."""
    try:
        import kaggle_environments as ke
        env = ke.make("cabt")
        return True
    except Exception:
        return False


def require_cabt() -> Any:
    """Return kaggle_environments, raising ImportError if unavailable."""
    try:
        import kaggle_environments as ke
        ke.make("cabt")   # verify cabt specifically
        return ke
    except Exception as e:
        raise ImportError(
            f"Real CABT environment is not available: {e}\n"
            "Do NOT substitute MockSimulator. Report this as a blocker."
        ) from e


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CabtGameResult:
    """Result from one complete real CABT game.

    source is always REAL_CABT_LOCAL — never OFFICIAL_KAGGLE_RESULT.
    """
    game_id:       str
    source:        str = "REAL_CABT_LOCAL"
    agent0_name:   str = ""
    agent1_name:   str = ""
    winner:        int  = -1     # 0 or 1; -1 if timeout/error
    total_steps:   int  = 0
    total_turns:   int  = 0
    reward_p0:     float = 0.0
    reward_p1:     float = 0.0
    end_reason:    str  = ""
    legal_errors:  int  = 0
    step_log:      list[dict] = field(default_factory=list)   # compact replay
    timestamp:     str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "game_id":     self.game_id,
            "source":      self.source,
            "agent0_name": self.agent0_name,
            "agent1_name": self.agent1_name,
            "winner":      self.winner,
            "total_steps": self.total_steps,
            "total_turns": self.total_turns,
            "reward_p0":   self.reward_p0,
            "reward_p1":   self.reward_p1,
            "end_reason":  self.end_reason,
            "legal_errors": self.legal_errors,
            "timestamp":   self.timestamp,
        }


# ---------------------------------------------------------------------------
# Single-game runner using env.train()
# ---------------------------------------------------------------------------

class CabtGame:
    """Runs one CABT game.

    Uses env.train([None, opponent]) so our agent controls player 0
    step-by-step via trainer.step(action).

    The opponent can be any string key in ke.agents (e.g. "random", "first")
    or a callable agent function.
    """

    # Default verified deck (Dragapult ex reference, Phase 1 engine-verified)
    DRAGAPULT_DECK: list[int] = (
        [119]*4 + [120]*4 + [121]*3 + [140]*1 + [184]*1 +
        [235]*2 + [1071]*1 + [1079]*2 + [1080]*1 + [1086]*4 +
        [1097]*2 + [1120]*4 + [1121]*4 + [1152]*3 + [1156]*1 +
        [1182]*3 + [1198]*4 + [1210]*2 + [1227]*4 + [1256]*2 +
        [2]*4 + [5]*4
    )

    def __init__(
        self,
        agent,
        opponent:  str = "random",
        deck:      Optional[list[int]] = None,
        game_id:   str = "cabt-001",
        max_steps: int = 500,
    ):
        self.agent     = agent
        self.opponent  = opponent
        self.deck      = deck or self.DRAGAPULT_DECK
        self.game_id   = game_id
        self.max_steps = max_steps

    def run(self) -> CabtGameResult:
        """Run one complete real CABT game. Returns CabtGameResult.

        CABT game loop (empirically verified):
          Step 0: reset() returns obs with select=None — submit deck list
          Step 1: obs has select.context=41 (deck selection confirm) — submit [0] or [1]
          Step 2+: normal game steps — submit [option_index]
        """
        ke = require_cabt()
        env = ke.make("cabt", debug=False)
        trainer = env.train([None, self.opponent])

        result = CabtGameResult(
            game_id    = self.game_id,
            agent0_name= getattr(self.agent, "name", str(type(self.agent).__name__)),
            agent1_name= self.opponent if isinstance(self.opponent, str) else "callable",
        )

        if hasattr(self.agent, "reset"):
            self.agent.reset()

        obs = trainer.reset()
        step_num = 0
        done = False

        while not done and step_num < self.max_steps:
            # Parse real observation
            gs = parse_observation(obs, player_index=0)

            # Determine action
            try:
                obs_d = dict(obs) if hasattr(obs, "keys") else {}
                sel_raw = obs_d.get("select")

                if sel_raw is None:
                    # Step 0: no select yet — submit the deck
                    action = list(self.deck)
                elif gs.select and gs.select.is_deck_selection:
                    # Context 41: pick first option (confirm deck)
                    action = [0]
                else:
                    action = agent_to_cabt_action(self.agent, gs, deck=self.deck)
            except Exception:
                action = []
                result.legal_errors += 1

            # Record compact step log
            result.step_log.append({
                "step":          step_num,
                "is_active":     gs.is_active,
                "turn":          gs.turn,
                "select_type":   gs.select.select_type if gs.select else None,
                "option_count":  gs.legal_option_count,
                "action_len":    len(action),
                "is_deck_sel":   bool(gs.select and gs.select.is_deck_selection),
            })

            # Step environment
            obs, reward, done, info = trainer.step(action)
            step_num += 1
            result.total_turns = gs.turn

        # Collect terminal info
        result.total_steps = step_num
        for ag_state in env.state:
            if hasattr(ag_state, "get"):
                rew = ag_state.get("reward", 0)
                idx = ag_state.get("observation", {}).get("step", 0)
        # Retrieve rewards from final state
        final = env.state
        if len(final) >= 2:
            result.reward_p0 = float(final[0].get("reward", 0) or 0)
            result.reward_p1 = float(final[1].get("reward", 0) or 0)
            # Determine winner
            if result.reward_p0 > result.reward_p1:
                result.winner = 0
            elif result.reward_p1 > result.reward_p0:
                result.winner = 1
            else:
                result.winner = -1   # draw or unknown

        result.end_reason = "terminal" if done else "max_steps"
        return result


# ---------------------------------------------------------------------------
# Multi-game runner
# ---------------------------------------------------------------------------

@dataclass
class CabtRunSummary:
    """Summary statistics from N real CABT games."""
    source:         str = "REAL_CABT_LOCAL"
    agent0_name:    str = ""
    agent1_name:    str = ""
    total_games:    int = 0
    agent0_wins:    int = 0
    agent1_wins:    int = 0
    draws:          int = 0
    agent0_wr:      float = 0.0
    mean_steps:     float = 0.0
    total_legal_errors: int = 0
    timestamp:      str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    game_results:   list[dict] = field(default_factory=list)

    def compute(self, results: list[CabtGameResult]) -> None:
        self.total_games = len(results)
        if not results:
            return
        self.agent0_wins = sum(1 for r in results if r.winner == 0)
        self.agent1_wins = sum(1 for r in results if r.winner == 1)
        self.draws       = sum(1 for r in results if r.winner == -1)
        self.agent0_wr   = self.agent0_wins / self.total_games
        self.mean_steps  = sum(r.total_steps for r in results) / self.total_games
        self.total_legal_errors = sum(r.legal_errors for r in results)
        self.game_results = [r.to_dict() for r in results]

    def to_dict(self) -> dict:
        return {
            "source":         self.source,
            "agent0_name":    self.agent0_name,
            "agent1_name":    self.agent1_name,
            "total_games":    self.total_games,
            "agent0_wins":    self.agent0_wins,
            "agent1_wins":    self.agent1_wins,
            "draws":          self.draws,
            "agent0_wr":      round(self.agent0_wr, 4),
            "mean_steps":     round(self.mean_steps, 2),
            "total_legal_errors": self.total_legal_errors,
            "timestamp":      self.timestamp,
        }

    def print_summary(self, header: str = "") -> None:
        if header:
            print(f"\n[CABT] {header}")
        print(f"  Source      : {self.source}  <- NOT official Kaggle result")
        print(f"  {self.agent0_name} vs {self.agent1_name}")
        print(f"  Games       : {self.total_games}")
        print(f"  {self.agent0_name} wins: {self.agent0_wins} ({self.agent0_wr:.1%})")
        print(f"  {self.agent1_name} wins: {self.agent1_wins}")
        print(f"  Draws       : {self.draws}")
        print(f"  Mean steps  : {self.mean_steps:.1f}")
        print(f"  Legal errors: {self.total_legal_errors}")


class CabtSelfPlayRunner:
    """Run N real CABT games between two agents."""

    def __init__(
        self,
        agent,
        opponent:   str = "random",
        n_games:    int = 10,
        deck:       Optional[list[int]] = None,
        output_dir: Optional[Path] = None,
    ):
        self.agent      = agent
        self.opponent   = opponent
        self.n_games    = n_games
        self.deck       = deck or CabtGame.DRAGAPULT_DECK
        self.output_dir = output_dir

    def run(self, experiment_id: str = "CABT-RUN-001") -> CabtRunSummary:
        """Run n_games real CABT games. All results labeled REAL_CABT_LOCAL."""
        require_cabt()   # fail early if not available

        agent_name = getattr(self.agent, "name", type(self.agent).__name__)
        summary = CabtRunSummary(
            agent0_name = agent_name,
            agent1_name = self.opponent if isinstance(self.opponent, str) else "callable",
        )

        results: list[CabtGameResult] = []
        t0 = time.time()

        print(f"\n[CABT] {experiment_id}")
        print(f"[CABT] {agent_name} vs {summary.agent1_name}  ({self.n_games} games)")
        print(f"[CABT] Source: REAL_CABT_LOCAL -- not an official Kaggle result")

        for i in range(self.n_games):
            game = CabtGame(
                agent    = self.agent,
                opponent = self.opponent,
                deck     = self.deck,
                game_id  = f"{experiment_id}-G{i:04d}",
            )
            r = game.run()
            results.append(r)
            w = "P0" if r.winner == 0 else ("P1" if r.winner == 1 else "Draw")
            print(f"  Game {i+1:>3}/{self.n_games}  winner={w}  steps={r.total_steps}  "
                  f"errors={r.legal_errors}  turns={r.total_turns}")

        summary.compute(results)
        elapsed = time.time() - t0
        summary.print_summary(f"Complete in {elapsed:.1f}s")

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            out = self.output_dir / f"{experiment_id}_results.json"
            out.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
            print(f"[CABT] Results -> {out}")

        return summary
