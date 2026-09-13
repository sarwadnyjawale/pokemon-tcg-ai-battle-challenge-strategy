"""Phase 3-6: Fixed Attack Evaluator with Dynamic Board Semantics."""

import re
from dataclasses import dataclass
from typing import Any

from ..environment.enriched_adapter import _parse_damage

@dataclass
class DamageModel:
    base_damage: int
    expected_damage: float
    min_damage: int
    max_damage: int
    ko_status: str  # GUARANTEED_KO, PROBABLE_KO, CONDITIONAL_KO, NO_KO, UNKNOWN
    effects: list[str]
    raw_damage_str: str

class AttackContext:
    def __init__(self, state: dict):
        self.own_bench_count = state.get("our_bench_count", state.get("own_bench_count", 0))
        self.opp_max_hp = state.get("opp_active_maxhp", state.get("opp_active_max_hp", 100))
        self.opp_damage = state.get("opp_active_damage", 0)
        self.remaining_hp = max(0, self.opp_max_hp - self.opp_damage)
        self.own_prizes = state.get("our_prizes", state.get("own_prizes", 6))
        self.opp_prizes = state.get("opp_prizes", 6)
        self.opp_is_ex = state.get("opp_is_ex", 0)
        self.turn = state.get("turn_number", state.get("turn", 0))

class AttackEvaluator:
    """Parses and evaluates attacks strictly using visible board context."""
    
    def evaluate(self, attack: dict, context: AttackContext) -> DamageModel:
        dmg_str = attack.get("damage", "")
        effect_text = attack.get("effect", "").lower()
        name = attack.get("name", "").lower()
        
        base_dmg = _parse_damage(dmg_str)
        exp_dmg = float(base_dmg)
        min_dmg = base_dmg
        max_dmg = base_dmg
        
        effects = []
        
        # Parse Variable Damage based on visible state
        if "circle circuit" in name:
            multiplier = 50
            total_dmg = multiplier * context.own_bench_count
            exp_dmg = total_dmg
            min_dmg = total_dmg
            max_dmg = total_dmg
        elif "x" in dmg_str.lower() or "×" in dmg_str:
            coins_match = re.search(r"flip (\d+) coin", effect_text)
            if coins_match:
                n_coins = int(coins_match.group(1))
                exp_dmg = base_dmg * (n_coins / 2.0)
                min_dmg = 0
                max_dmg = base_dmg * n_coins
            else:
                # E.g. 50x for each energy - dynamic calculation needed
                # For safety, treat as base damage if we can't parse exactly
                exp_dmg = base_dmg
                min_dmg = base_dmg
                max_dmg = base_dmg * 3 # Optimistic max
                
        elif "+" in dmg_str:
            extra_match = re.search(r"does (\d+) more", effect_text)
            if extra_match:
                extra = int(extra_match.group(1))
                exp_dmg = base_dmg + (extra * 0.5)
                min_dmg = base_dmg
                max_dmg = base_dmg + extra
            else:
                exp_dmg = base_dmg + 20
                min_dmg = base_dmg
                max_dmg = base_dmg + 50
                
        # Parse Semantic Effects
        if "heal" in effect_text or "recover" in effect_text:
            effects.append("heal")
        if "discard" in effect_text:
            effects.append("discard")
        if "switch" in effect_text or ("bench" in effect_text and "switch" in effect_text):
            effects.append("switch")
        if "to your opponent's benched" in effect_text or "on your opponent's benched" in effect_text or "damage to 1 of your opponent's benched" in effect_text:
            effects.append("bench_damage")
        if "search" in effect_text:
            effects.append("search")
        if "paralyzed" in effect_text or "poisoned" in effect_text or "asleep" in effect_text or "burned" in effect_text or "confused" in effect_text:
            effects.append("status")
            
        # Fix KO Evaluation
        if context.remaining_hp == 0:
            # Active already KO'd (rare edge case in CABT transition states)
            ko_status = "UNKNOWN"
        elif min_dmg >= context.remaining_hp:
            ko_status = "GUARANTEED_KO"
        elif exp_dmg >= context.remaining_hp:
            ko_status = "PROBABLE_KO"
        elif max_dmg >= context.remaining_hp:
            ko_status = "CONDITIONAL_KO"
        else:
            ko_status = "NO_KO"
            
        return DamageModel(
            base_damage=base_dmg,
            expected_damage=exp_dmg,
            min_damage=min_dmg,
            max_damage=max_dmg,
            ko_status=ko_status,
            effects=effects,
            raw_damage_str=dmg_str
        )
