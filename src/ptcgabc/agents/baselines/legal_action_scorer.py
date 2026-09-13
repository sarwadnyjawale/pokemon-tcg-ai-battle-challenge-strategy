"""Phase 3 — Legal Action Scorer (Baseline 6).

Scores each legal action using hand-crafted feature weights.
Weights are intentionally simple starting points; Phase 4 will learn them.

RULE: Only VISIBLE_NOW / INFERRED features.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Feature vector for one action
# ---------------------------------------------------------------------------

@dataclass
class ActionFeatures:
    """Features for one legal action in one game state.
    All fields must be VISIBLE_NOW or INFERRED.
    """

    action_index: int

    # Action type
    is_attack:       bool = False
    is_trainer:      bool = False
    is_energy_attach: bool = False
    is_evolve:       bool = False
    is_play_pokemon: bool = False
    is_retreat:      bool = False
    is_pass:         bool = False

    # Tactical
    immediate_damage: int  = 0
    would_ko:         bool = False
    targets_ex:       bool = False
    prize_gain:       int  = 0

    # Resource
    energy_cost:  int = 0
    energy_gained: int = 0
    hand_change:  int = 0
    bench_change: int = 0

    # Strategic context
    game_phase:      str   = "midgame"
    prize_delta:     int   = 0
    our_hp_fraction: float = 1.0
    opp_hp_fraction: float = 1.0

    # Effect categories
    effect_is_draw:    bool = False
    effect_is_search:  bool = False
    effect_is_heal:    bool = False
    effect_is_switch:  bool = False
    effect_is_disrupt: bool = False

    # Risk
    leaves_active_vulnerable: bool = False
    uses_last_energy:          bool = False
    forces_discard:            bool = False

    def to_vector(self) -> list[float]:
        """Flat numerical vector for ML models."""
        phase_enc = {"opening": 0, "early": 1, "midgame": 2, "late": 3, "endgame": 4}
        return [
            float(self.is_attack),
            float(self.is_trainer),
            float(self.is_energy_attach),
            float(self.is_evolve),
            float(self.is_play_pokemon),
            float(self.is_retreat),
            float(self.is_pass),
            self.immediate_damage / 200.0,
            float(self.would_ko),
            float(self.targets_ex),
            float(self.prize_gain),
            self.energy_cost / 5.0,
            self.our_hp_fraction,
            self.opp_hp_fraction,
            phase_enc.get(self.game_phase, 2) / 4.0,
            (self.prize_delta + 3) / 6.0,  # normalise [-3, 3] → [0, 1]
            float(self.effect_is_draw),
            float(self.effect_is_search),
            float(self.effect_is_heal),
            float(self.effect_is_switch),
            float(self.effect_is_disrupt),
            float(self.leaves_active_vulnerable),
            float(self.uses_last_energy),
            float(self.forces_discard),
            self.hand_change / 5.0,
            self.bench_change / 4.0,
        ]

    @classmethod
    def dimension(cls) -> int:
        return 26


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_action_features(
    action:       dict,
    action_index: int,
    game_state:   dict,
    card_db:      Optional[dict] = None,
) -> ActionFeatures:
    """Extract features for one legal action.

    RULE: Only use information visible at decision time.
    """
    f = ActionFeatures(action_index=action_index)

    if not isinstance(action, dict):
        return f

    atype = action.get("type", action.get("action_type", "unknown")).lower()
    f.game_phase      = game_state.get("game_phase", "midgame")
    f.prize_delta     = game_state.get("prize_delta", 0)
    f.our_hp_fraction = game_state.get("our_active_hp_fraction", 1.0)
    f.opp_hp_fraction = game_state.get("opp_active_hp_fraction", 1.0)

    # Action type flags
    f.is_attack        = "attack" in atype
    f.is_trainer       = "trainer" in atype
    f.is_energy_attach = "energy" in atype or "attach" in atype
    f.is_evolve        = "evolve" in atype
    f.is_play_pokemon  = "pokemon" in atype and "play" in atype
    f.is_retreat       = "retreat" in atype or "switch" in atype
    f.is_pass          = atype in ("pass", "end_turn", "end")

    # Attack features
    if f.is_attack:
        f.immediate_damage = action.get("damage", 0)
        opp_max     = game_state.get("opp_active_max_hp", 100)
        opp_extra   = game_state.get("opp_active_damage", 0)
        opp_rem     = max(0, opp_max * f.opp_hp_fraction - opp_extra)
        f.would_ko  = f.immediate_damage >= opp_rem
        f.targets_ex = bool(game_state.get("opp_is_ex", 0))
        if f.would_ko:
            f.prize_gain = 2 if f.targets_ex else 1
        f.energy_cost = action.get("energy_cost", 0)
        our_energy    = game_state.get("our_energy_in_play", 0)
        f.uses_last_energy = our_energy <= f.energy_cost
        our_hp_abs  = f.our_hp_fraction * game_state.get("our_active_max_hp", 100)
        f.leaves_active_vulnerable = our_hp_abs < 50

    # Trainer features
    if f.is_trainer:
        eff = action.get("effect_category", action.get("effect", "")).lower()
        f.effect_is_draw    = "draw"    in eff
        f.effect_is_search  = "search"  in eff
        f.effect_is_heal    = "heal"    in eff
        f.effect_is_switch  = "switch"  in eff
        f.effect_is_disrupt = "disrupt" in eff or "discard" in eff
        f.hand_change       = action.get("hand_change", 0)
        f.forces_discard    = "discard" in eff

    if f.is_play_pokemon:
        f.bench_change = 1

    if f.is_energy_attach:
        f.energy_gained = 1

    return f


# ---------------------------------------------------------------------------
# B6 — Legal Action Scorer Agent
# ---------------------------------------------------------------------------

class LegalActionScorerAgent:
    """Scores each legal action and selects the highest-scoring one.

    Hand-crafted starting weights; Phase 4 will learn improved weights
    from game outcomes.
    """

    def __init__(self, name: str = "B6-LegalActionScorer"):
        self.name = name
        self.game_count = 0
        # Initial weights — to be tuned/learned in Phase 4
        self.weights: dict[str, float] = {
            "immediate_ko":          100.0,
            "ex_ko_bonus":            50.0,
            "damage_per_hp":          15.0,
            "setup_early":             8.0,
            "energy_attach":           6.0,
            "draw_effect":             7.0,
            "search_effect":           8.0,
            "heal_when_low":          12.0,
            "evolve":                  9.0,
            "pass_penalty":           -2.0,
            "vulnerability_penalty": -10.0,
            "endgame_aggression":     20.0,
            "behind_aggression":       5.0,
        }

    def reset(self) -> None:
        self.game_count += 1

    def score_features(self, f: ActionFeatures) -> float:
        """Apply weight vector to feature structure."""
        w = self.weights
        score = 0.0

        if f.would_ko:
            score += w["immediate_ko"]
            if f.targets_ex:
                score += w["ex_ko_bonus"]

        if f.is_attack and not f.would_ko:
            score += f.immediate_damage * 0.1 * w["damage_per_hp"]

        if (f.is_play_pokemon or f.is_evolve) and f.game_phase in ("opening", "early"):
            score += w["setup_early"]
        if f.is_evolve:
            score += w["evolve"]

        if f.is_energy_attach:
            score += w["energy_attach"]
        if f.effect_is_draw:
            score += w["draw_effect"]
        if f.effect_is_search:
            score += w["search_effect"]

        if f.effect_is_heal and f.our_hp_fraction < 0.4:
            score += w["heal_when_low"] * (1.0 - f.our_hp_fraction)

        if f.is_pass:
            score += w["pass_penalty"]
        if f.leaves_active_vulnerable:
            score += w["vulnerability_penalty"]

        if f.game_phase == "endgame" and f.is_attack:
            score += w["endgame_aggression"]
        if f.prize_delta > 0 and f.is_attack:
            score += w["behind_aggression"] * f.prize_delta

        return score

    def select_action(
        self,
        legal_actions: list,
        game_state:    dict,
        turn:          int = 0,
    ) -> tuple[int, str]:
        if not legal_actions:
            raise ValueError(f"{self.name}: No legal actions")

        scored = []
        for i, action in enumerate(legal_actions):
            feats = extract_action_features(action, i, game_state)
            score = self.score_features(feats)
            scored.append((i, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        best_idx, best_score = scored[0]
        return best_idx, f"action_score={best_score:.2f}"
