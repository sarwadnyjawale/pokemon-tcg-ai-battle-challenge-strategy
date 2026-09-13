"""Tempo / Strategic Timing Policy for CABT MAIN-context decisions.

Evaluates the strategic value of each MAIN-context option by considering:
  - Attack readiness and value
  - Setup urgency vs attack opportunity
  - Board development needs
  - Prize race pressure
  - Energy management
  - Survival considerations

The key principle: the right objective is not "attack as often as possible"
but "maximize expected game value while understanding when attacking is
strategically correct."

RULES:
  - Only visible information used
  - No hard-coded "always attack" rule
  - Transparent scoring with named components
"""

from __future__ import annotations

from typing import Any

from ..environment.enriched_adapter import (
    OPT_ATTACK, OPT_EVOLVE, OPT_ATTACH, OPT_PLAY, OPT_ABILITY,
    OPT_RETREAT, OPT_END, OPT_CARD,
    _load_card_db,
    _parse_damage,
    _card_category,
    _trainer_effect_category,
)


class TempoScorer:
    """Scores MAIN-context actions based on strategic timing.

    Each action gets a composite score from multiple named components.
    The scoring is transparent and can be inspected per-decision.
    """

    def __init__(self, card_db: dict[int, dict] | None = None, enable_ability_evaluator: bool = False, enable_tracer: bool = False):
        self._db = card_db or _load_card_db()
        from .attack_value import AttackEvaluator, AttackContext
        from .ability_value import AbilityEvaluator
        self.attack_evaluator = AttackEvaluator()
        self.ability_evaluator = AbilityEvaluator()
        self.enable_ability_evaluator = enable_ability_evaluator
        self.enable_tracer = enable_tracer
        self._traces = []

    def score(self, action: dict, state: dict, turn: int) -> float:
        """Score a MAIN-context action.

        Returns a float where higher = more desirable.
        """
        opt_type = action.get("cabt_option_type", -1)

        if opt_type == OPT_ATTACK:
            return self._score_attack(action, state, turn)
        elif opt_type == OPT_EVOLVE:
            return self._score_evolve(action, state, turn)
        elif opt_type == OPT_ATTACH:
            return self._score_attach(action, state, turn)
        elif opt_type == OPT_PLAY:
            return self._score_play(action, state, turn)
        elif opt_type == OPT_ABILITY:
            return self._score_ability(action, state, turn)
        elif opt_type == OPT_RETREAT:
            return self._score_retreat(action, state, turn)
        elif opt_type == OPT_END:
            return self._score_end(action, state, turn)
        else:
            return 0.0

    # ------------------------------------------------------------------
    # Component scorers
    # ------------------------------------------------------------------

    def _score_attack(self, action: dict, state: dict, turn: int) -> float:
        """Score an attack option using semantic AttackEvaluator."""
        from .attack_value import AttackContext
        
        cid = action.get("card_id", 0)
        cdata = self._db.get(cid, {})
        attacks = cdata.get("attacks", [])
        
        action_attack_name = action.get("card_name", "")
        target_attack = None
        for a in attacks:
            if a.get("name") == action_attack_name:
                target_attack = a
                break
        
        if not target_attack and attacks:
            target_attack = attacks[0]
        elif not target_attack:
            target_attack = {"damage": str(action.get("damage", 0)), "name": action_attack_name}
            
        context = AttackContext(state)
        eval_res = self.attack_evaluator.evaluate(target_attack, context)

        score = 30.0  # base value: attacks advance the game

        # Damage & KO Component
        if eval_res.ko_status == "GUARANTEED_KO":
            score += 60.0
            if context.opp_is_ex:
                score += 25.0
            if context.own_prizes <= 2:
                score += 20.0
        elif eval_res.ko_status == "PROBABLE_KO":
            score += 50.0
            if context.opp_is_ex:
                score += 20.0
        elif eval_res.ko_status == "CONDITIONAL_KO":
            score += 40.0
        elif eval_res.expected_damage > 0:
            damage_fraction = eval_res.expected_damage / max(context.opp_max_hp, 1)
            score += damage_fraction * 30.0
        else:
            score += 5.0
            
        # Semantic Effects
        if "status" in eval_res.effects:
            score += 15.0
        if "bench_damage" in eval_res.effects:
            score += 10.0
        if "search" in eval_res.effects or "draw" in eval_res.effects:
            score += 15.0

        # Prize race urgency
        if context.own_prizes <= context.opp_prizes:
            score += 5.0
        if context.own_prizes <= 1:
            score += 15.0

        phase = state.get("game_phase", "midgame")
        if phase == "endgame":
            score += 10.0
        elif phase in ("opening", "early"):
            if eval_res.expected_damage < 30 and not eval_res.effects:
                score -= 5.0

        # Tracer
        if self.enable_tracer:
            self._traces.append({
                "turn": turn,
                "card_name": cdata.get("card_name", ""),
                "attack_id": action.get("raw", {}).get("attackId", -1),
                "raw_option": action.get("raw", {}),
                "parsed_attack": target_attack,
                "damage_model": {
                    "base": eval_res.base_damage,
                    "expected": eval_res.expected_damage,
                    "min": eval_res.min_damage,
                    "max": eval_res.max_damage,
                    "ko_status": eval_res.ko_status,
                    "effects": eval_res.effects
                },
                "context": {
                    "opp_max_hp": context.opp_max_hp,
                    "opp_damage": context.opp_damage,
                    "remaining_hp": context.remaining_hp,
                    "own_bench": context.own_bench_count,
                    "own_prizes": context.own_prizes
                },
                "score": score
            })

        return score

    def _score_evolve(self, action: dict, state: dict, turn: int) -> float:
        """Score an evolution option.

        Evolution is typically very valuable because:
          - Evolved Pokemon have more HP, stronger attacks
          - Sets up future turns
          - May be strictly necessary before attacking effectively
        """
        phase = state.get("game_phase", "midgame")
        card_name = action.get("card_name", "").lower()
        cid = action.get("card_id", 0)
        cdata = self._db.get(cid, {})

        score = 35.0  # base: evolution is almost always good

        # Check if this evolution leads to a strong attacker
        attacks = cdata.get("attacks", [])
        max_damage = 0
        for atk in attacks:
            dmg = _parse_damage(atk.get("damage", ""))
            max_damage = max(max_damage, dmg)

        if max_damage >= 100:
            score += 15.0  # evolving into a heavy hitter
        elif max_damage >= 50:
            score += 8.0

        # Early evolution is crucial for setup
        if phase in ("opening", "early"):
            score += 10.0

        # Named card bonuses (Dragapult line is our main attacker)
        if "dragapult" in card_name:
            score += 15.0  # main attacker
        elif "drakloak" in card_name:
            score += 10.0  # intermediate evolution

        # ex forms are high-value evolutions
        if "ex" in card_name:
            score += 10.0

        return score

    def _score_attach(self, action: dict, state: dict, turn: int) -> float:
        """Score energy attachment.

        Energy is critical for enabling attacks.
        """
        phase = state.get("game_phase", "midgame")
        energy_attached = state.get("energy_attached", False)
        own_energy = state.get("own_energy_in_play", 0)

        score = 25.0  # base: energy is almost always useful

        if not energy_attached:
            score += 5.0  # first energy attachment this turn

        # Energy is more critical when we have little
        if own_energy <= 1:
            score += 8.0
        elif own_energy <= 3:
            score += 4.0

        # Energy in opening is critical for attack enablement
        if phase in ("opening", "early"):
            score += 5.0

        return score

    def _score_play(self, action: dict, state: dict, turn: int) -> float:
        """Score playing a card from hand."""
        card_cat = action.get("card_category", "")
        effect = action.get("effect_category", "")
        is_supporter = action.get("is_supporter", False)
        supporter_played = state.get("supporter_played", False)
        phase = state.get("game_phase", "midgame")
        hand = state.get("own_hand_count", state.get("our_hand_count", 3))
        bench = state.get("own_bench_count", state.get("our_bench_count", 0))

        if card_cat == "Pokemon":
            score = 18.0
            if bench < 2 and phase in ("opening", "early"):
                score += 12.0  # bench development critical early
            elif bench < 3:
                score += 5.0
            return score

        elif card_cat == "Trainer":
            # Supporters can only be played once per turn
            if is_supporter and supporter_played:
                return -10.0  # can't play another supporter

            score = 15.0
            if effect == "draw":
                if hand <= 1:
                    score += 15.0  # desperate draw
                elif hand <= 3:
                    score += 8.0
                else:
                    score += 3.0  # already have cards
            elif effect == "search":
                score += 10.0  # search is versatile
                if phase in ("opening", "early"):
                    score += 5.0  # setup search is key
            elif effect == "switch":
                own_hp_frac = state.get("own_active_hp_fraction", 1.0)
                if own_hp_frac < 0.3:
                    score += 12.0  # need to switch out dying Pokemon
                else:
                    score += 2.0
            elif effect == "gust":
                # Boss's Orders / Counter Catcher. Is there a good target?
                try:
                    from .target_context import TargetSelectionScorer
                    target_scorer = TargetSelectionScorer(self._db)
                    best_target_score = 0.0
                    opp_idx = 1 - state.get("your_index", 0)
                    for p in state.get("players", []):
                        if p.get("player_index") == opp_idx:
                            # Evaluate each benched pokemon
                            for i, bench_mon in enumerate(p.get("bench", [])):
                                # Create a dummy action to score
                                dummy_action = {"raw": {"area": 5, "index": i, "playerIndex": opp_idx}}
                                ts = target_scorer.score_target(dummy_action, state)
                                if ts > best_target_score:
                                    best_target_score = ts
                    if best_target_score >= 50.0: # e.g. GUARANTEED_KO
                        score += 30.0
                    elif best_target_score >= 30.0:
                        score += 15.0
                    else:
                        score -= 5.0 # Save it
                except Exception:
                    score += 5.0 # Fallback
            elif effect == "discard":
                score += 4.0  # disruption
            elif effect == "heal":
                own_hp_frac = state.get("own_active_hp_fraction", 1.0)
                if own_hp_frac < 0.5:
                    score += 8.0
            elif effect == "evolve":
                score += 12.0  # Rare Candy
            else:
                score += 3.0  # generic utility
            return score

        elif card_cat == "Energy":
            return 22.0  # energy from hand

        return 10.0  # unknown card type

    def _score_ability(self, action: dict, state: dict, turn: int) -> float:
        """Score using a Pokemon ability."""
        cid = action.get("card_id", 0)
        cdata = self._db.get(cid, {})
        if cdata:
            eval_res = self.ability_evaluator.evaluate(cdata, state)
            return eval_res.context_score
        return 22.0  # abilities are generally free actions — use them

    def _score_retreat(self, action: dict, state: dict, turn: int) -> float:
        """Score retreat action.

        Only high value when active is threatened or a better attacker is on bench.
        """
        own_hp_frac = state.get("own_active_hp_fraction", 1.0)
        retreated = state.get("retreated", False)

        if retreated:
            return -10.0  # already retreated this turn

        if own_hp_frac < 0.2:
            return 28.0  # active about to die — retreat is urgent
        elif own_hp_frac < 0.4:
            return 15.0
        else:
            return 3.0  # low priority when healthy

    def _score_end(self, action: dict, state: dict, turn: int) -> float:
        """Score ending turn / passing.

        Should almost always be the lowest-scored option.
        """
        return -5.0  # strong disincentive to pass
