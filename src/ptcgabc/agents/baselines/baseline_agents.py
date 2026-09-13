"""Phase 3 — Baseline Agents (B0 – B4).

RULE: Baselines must exist and be evaluated before advanced learning begins.
RULE: Every agent must always return a valid index into legal_actions.
RULE: Agents operate on VISIBLE_NOW game state dicts only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AgentConfig:
    name:        str
    description: str
    agent_class: str


@dataclass
class ActionRecord:
    turn:          int
    state_summary: dict
    action_chosen: dict
    action_index:  int
    legal_count:   int
    reason:        str = ""


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class BaseAgent:
    """Common interface for all agents."""

    def __init__(self, name: str):
        self.name = name
        self.action_history: list[ActionRecord] = []
        self.game_count = 0

    def select_action(
        self,
        legal_actions: list,
        game_state:    dict,
        turn:          int = 0,
    ) -> tuple[int, str]:
        """Return (action_index, reason). Must always be valid."""
        raise NotImplementedError

    def reset(self) -> None:
        """Called at the start of each game."""
        self.game_count += 1
        self.action_history = []

    def record(self, turn: int, state: dict, action: dict,
               index: int, reason: str) -> None:
        self.action_history.append(ActionRecord(
            turn=turn,
            state_summary=state,
            action_chosen=action,
            action_index=index,
            legal_count=len(self.action_history),
            reason=reason,
        ))


# ---------------------------------------------------------------------------
# B0 — Simulator Order
# ---------------------------------------------------------------------------

class SimulatorOrderBaseline(BaseAgent):
    """Always selects the first legal action as offered by the simulator.

    Tests whether simulator ordering carries useful signal.
    Do NOT assume direction — let experiments determine.
    """

    def __init__(self):
        super().__init__("B0-SimulatorOrder")

    def select_action(self, legal_actions, game_state, turn=0):
        if not legal_actions:
            raise ValueError(f"{self.name}: No legal actions available")
        return 0, "first_offered_by_simulator"


# ---------------------------------------------------------------------------
# B1 — Random
# ---------------------------------------------------------------------------

class RandomBaseline(BaseAgent):
    """Uniform random selection from legal actions.

    Sanity check and environment validation baseline.
    """

    def __init__(self, seed: Optional[int] = None):
        super().__init__("B1-Random")
        self.rng = random.Random(seed)

    def select_action(self, legal_actions, game_state, turn=0):
        if not legal_actions:
            raise ValueError(f"{self.name}: No legal actions available")
        idx = self.rng.randrange(len(legal_actions))
        return idx, f"random_choice_{idx}"


# ---------------------------------------------------------------------------
# B2 — Simple Heuristic
# ---------------------------------------------------------------------------

class SimpleHeuristicBaseline(BaseAgent):
    """Priority: KO → survive → setup → trainer → energy → fallback.

    Simple rule-based, no lookahead, no learned weights.
    """

    def __init__(self):
        super().__init__("B2-SimpleHeuristic")
        self.priority_rules = [
            self._rule_take_ko,
            self._rule_survive,
            self._rule_setup,
            self._rule_play_trainer,
            self._rule_attach_energy,
            self._rule_fallback_first,
        ]

    # -- helpers --

    @staticmethod
    def _action_type(action: dict) -> str:
        if isinstance(action, dict):
            return action.get("type", action.get("action_type", "unknown")).lower()
        return str(action).lower()

    @staticmethod
    def _damage(action: dict) -> int:
        return action.get("damage", 0) if isinstance(action, dict) else 0

    def _would_ko(self, action: dict, gs: dict) -> bool:
        if self._action_type(action) != "attack":
            return False
        opp_max   = gs.get("opp_active_max_hp", 100)
        opp_frac  = gs.get("opp_active_hp_fraction", 1.0)
        opp_dmg   = gs.get("opp_active_damage", 0)
        remaining = max(0, opp_max * opp_frac - opp_dmg)
        return self._damage(action) >= remaining

    def _would_save(self, action: dict, gs: dict) -> bool:
        hp_frac = gs.get("our_active_hp_fraction", 1.0)
        return hp_frac < 0.25 and self._action_type(action) in ("retreat", "switch", "heal")

    def _is_setup(self, action: dict, gs: dict) -> bool:
        return (self._action_type(action) in ("play_pokemon", "evolve") and
                gs.get("game_phase", "") in ("opening", "early"))

    # -- rules --

    def _rule_take_ko(self, actions, gs):
        for i, a in enumerate(actions):
            if self._would_ko(a, gs):
                return i, "rule:take_ko"
        return None

    def _rule_survive(self, actions, gs):
        for i, a in enumerate(actions):
            if self._would_save(a, gs):
                return i, "rule:survive"
        return None

    def _rule_setup(self, actions, gs):
        for i, a in enumerate(actions):
            if self._is_setup(a, gs):
                return i, "rule:setup"
        return None

    def _rule_play_trainer(self, actions, gs):
        for i, a in enumerate(actions):
            if self._action_type(a) in ("play_trainer", "trainer"):
                return i, "rule:play_trainer"
        return None

    def _rule_attach_energy(self, actions, gs):
        for i, a in enumerate(actions):
            if self._action_type(a) in ("attach_energy", "energy"):
                return i, "rule:attach_energy"
        return None

    @staticmethod
    def _rule_fallback_first(actions, gs):
        return (0, "rule:fallback_first") if actions else None

    def select_action(self, legal_actions, game_state, turn=0):
        if not legal_actions:
            raise ValueError(f"{self.name}: No legal actions")
        for rule in self.priority_rules:
            result = rule(legal_actions, game_state)
            if result is not None:
                return result
        return 0, "fallback_first"


# ---------------------------------------------------------------------------
# B3 — Tactical Greedy
# ---------------------------------------------------------------------------

class TacticalGreedyBaseline(BaseAgent):
    """Maximize immediate tactical value (damage > KO > resource)."""

    def __init__(self):
        super().__init__("B3-TacticalGreedy")

    def _score(self, action: dict, gs: dict) -> float:
        if not isinstance(action, dict):
            return 0.0
        atype   = action.get("type", "unknown").lower()
        damage  = action.get("damage", 0)
        score   = 0.0

        if atype == "attack":
            score += damage * 0.1
            opp_hp = gs.get("opp_active_hp_fraction", 1.0) * gs.get("opp_active_max_hp", 100)
            if damage >= opp_hp:
                score += 100.0
                if gs.get("opp_is_ex", 0):
                    score += 50.0
        elif atype in ("attach_energy", "energy"):
            score += 5.0
        elif atype in ("play_trainer", "trainer"):
            eff = action.get("effect_category", "")
            score += {"draw": 8.0, "search": 7.0}.get(eff, 3.0)
        elif atype == "evolve":
            score += 10.0
        elif atype in ("play_pokemon", "pokemon"):
            score += 4.0
        elif atype in ("pass", "end_turn"):
            score -= 1.0

        return score

    def select_action(self, legal_actions, game_state, turn=0):
        if not legal_actions:
            raise ValueError(f"{self.name}: No legal actions")
        best_i = max(range(len(legal_actions)),
                     key=lambda i: self._score(legal_actions[i], game_state))
        return best_i, f"tactical_score={self._score(legal_actions[best_i], game_state):.2f}"


# ---------------------------------------------------------------------------
# B4 — Strategic Heuristic
# ---------------------------------------------------------------------------

class StrategicHeuristicBaseline(BaseAgent):
    """Multi-turn strategic heuristic with phase-weighted scoring."""

    PHASE_WEIGHTS = {
        "opening": {"setup": 0.6, "tempo": 0.2, "disruption": 0.1, "attack": 0.1},
        "early":   {"setup": 0.4, "tempo": 0.3, "disruption": 0.1, "attack": 0.2},
        "midgame": {"setup": 0.2, "tempo": 0.2, "disruption": 0.2, "attack": 0.4},
        "late":    {"setup": 0.1, "tempo": 0.1, "disruption": 0.2, "attack": 0.6},
        "endgame": {"setup": 0.0, "tempo": 0.0, "disruption": 0.2, "attack": 0.8},
    }

    def __init__(self):
        super().__init__("B4-StrategicHeuristic")

    def _score(self, action: dict, gs: dict) -> float:
        if not isinstance(action, dict):
            return 0.0
        phase   = gs.get("game_phase", "midgame")
        w       = self.PHASE_WEIGHTS.get(phase, self.PHASE_WEIGHTS["midgame"])
        atype   = action.get("type", "unknown").lower()
        our_hp  = gs.get("our_active_hp_fraction", 1.0)
        opp_hp  = gs.get("opp_active_hp_fraction", 1.0)
        opp_max = gs.get("opp_active_max_hp", 100)
        our_pri = gs.get("our_prizes", 6)
        opp_pri = gs.get("opp_prizes", 6)
        delta   = our_pri - opp_pri
        is_ex   = bool(gs.get("opp_is_ex", 0))
        bench   = gs.get("our_bench_count", 0)

        setup = tempo = attack = disrupt = 0.0

        if atype in ("play_pokemon", "evolve"):
            setup = 10.0 + (5.0 if bench < 2 and phase in ("opening", "early") else 0.0)

        if atype in ("attach_energy", "energy"):
            tempo = 8.0
        elif atype in ("play_trainer", "trainer"):
            eff = action.get("effect_category", "")
            hand = gs.get("our_hand_count", 4)
            tempo = 10.0 if (eff == "draw" and hand < 3) else ({"draw": 6.0, "search": 9.0}.get(eff, 4.0))
            if "disrupt" in eff or "switch" in eff:
                disrupt = 8.0

        if atype == "attack":
            dmg = action.get("damage", 0)
            attack = dmg * 0.05
            remaining = opp_hp * opp_max
            if dmg >= remaining:
                attack += 50.0 + (25.0 if is_ex else 0.0) + (30.0 if our_pri <= 1 else 0.0)
            if delta > 0:
                attack *= 1.3

        safety = 0.0
        if our_hp < 0.25 and atype not in ("retreat", "switch", "heal"):
            safety = -10.0

        return w["setup"] * setup + w["tempo"] * tempo + w["attack"] * attack + w["disruption"] * disrupt + safety

    def select_action(self, legal_actions, game_state, turn=0):
        if not legal_actions:
            raise ValueError(f"{self.name}: No legal actions")
        best_i = max(range(len(legal_actions)),
                     key=lambda i: self._score(legal_actions[i], game_state))
        phase = game_state.get("game_phase", "?")
        return best_i, f"strategic_score={self._score(legal_actions[best_i], game_state):.3f}_phase={phase}"
