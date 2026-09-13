"""Tactical Target Context and Target Selection Scorer.

Couples target selection tightly to the AttackEvaluator to evaluate targets
based on tactical feasibility (e.g. can we actually KO it?) rather than
just static threat values.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

from ptcgabc.policy.attack_value import AttackEvaluator, AttackContext, DamageModel

@dataclass
class TargetContext:
    """Tactical context for an opponent target."""
    card_id: int
    card_name: str
    card_category: str
    is_active: bool
    max_hp: int
    current_damage: int
    remaining_hp: int
    attached_energy: int
    retreat_cost: int
    prize_value: int
    is_ex: bool
    
    # Tactical Evaluation
    best_incoming_damage: float = 0.0
    ko_status: str = "UNKNOWN"
    can_exploit: bool = False

class TargetSelectionScorer:
    """Scores opponent targets based on tactical feasibility and strategic value."""
    
    def __init__(self, card_db: dict[int, dict] | None = None, enable_tracer: bool = False):
        from ptcgabc.environment.enriched_adapter import _load_card_db
        self._db = card_db or _load_card_db()
        self.attack_eval = AttackEvaluator()
        self.enable_tracer = enable_tracer
        self._traces = []
        
    def _build_target_context(self, action: dict, state: dict) -> TargetContext | None:
        raw = action.get("raw", {})
        target_area = raw.get("area", -1)
        target_idx = raw.get("index", -1)
        player_idx = raw.get("playerIndex", -1)
        
        target_pokemon = None
        for p in state.get("players", []):
            if p.get("player_index") == player_idx:
                if target_area == 4 and p.get("active"):
                    target_pokemon = p["active"][0]
                elif target_area == 5 and target_idx < len(p["bench"]):
                    target_pokemon = p["bench"][target_idx]
                    
        if not target_pokemon:
            return None
            
        cid = target_pokemon.card_id if hasattr(target_pokemon, "card_id") else target_pokemon.get("id", 0)
        cdata = self._db.get(cid, {})
        name = cdata.get("card_name", "").lower()
        is_ex = "ex" in name
        prize_value = 2 if is_ex else 1
        
        hp = target_pokemon.hp if hasattr(target_pokemon, "hp") else target_pokemon.get("hp", 100)
        max_hp = target_pokemon.max_hp if hasattr(target_pokemon, "max_hp") else target_pokemon.get("maxHp", 100)
        damage = max_hp - hp
        
        energies = target_pokemon.energies if hasattr(target_pokemon, "energies") else target_pokemon.get("energies", [])
        
        # Retreat cost
        rc_str = cdata.get("fields", {}).get("Retreat", "0")
        rc = int(rc_str) if rc_str.isdigit() else 0
        
        return TargetContext(
            card_id=cid,
            card_name=name,
            card_category=_card_category(cdata),
            is_active=(target_area == 4),
            max_hp=max_hp,
            current_damage=damage,
            remaining_hp=hp,
            attached_energy=len(energies),
            retreat_cost=rc,
            prize_value=prize_value,
            is_ex=is_ex
        )
        
    def _evaluate_tactical_feasibility(self, tctx: TargetContext, state: dict):
        """Pretend the target is active and evaluate our best attack against it."""
        # Setup mock state with target as active
        mock_state = dict(state)
        mock_state["opp_active_maxhp"] = tctx.max_hp
        mock_state["opp_active_damage"] = tctx.current_damage
        mock_state["opp_is_ex"] = int(tctx.is_ex)
        
        attack_ctx = AttackContext(mock_state)
        
        # Get our active's attacks
        best_dmg = 0.0
        best_ko = "NO_KO"
        
        our_idx = state.get("your_index", 0)
        our_active = None
        for p in state.get("players", []):
            if p.get("player_index") == our_idx and p.get("active"):
                our_active = p["active"][0]
                break
                
        if our_active:
            cid = our_active.card_id if hasattr(our_active, "card_id") else our_active.get("id", 0)
            our_cdata = self._db.get(cid, {})
            attacks = our_cdata.get("attacks", [])
            for atk in attacks:
                res = self.attack_eval.evaluate(atk, attack_ctx)
                if res.expected_damage > best_dmg:
                    best_dmg = res.expected_damage
                if res.ko_status in ("GUARANTEED_KO", "PROBABLE_KO", "CONDITIONAL_KO"):
                    best_ko = res.ko_status
                    if res.ko_status == "GUARANTEED_KO":
                        break
                        
        tctx.best_incoming_damage = best_dmg
        tctx.ko_status = best_ko
        tctx.can_exploit = (best_ko != "NO_KO" and best_ko != "UNKNOWN")

    def score_target(self, action: dict, state: dict) -> float:
        score = 10.0
        
        tctx = self._build_target_context(action, state)
        if not tctx:
            return score
            
        self._evaluate_tactical_feasibility(tctx, state)
        
        # TARGET VALUE MODEL
        # immediate_prize_value, ko_value, threat_value, support_value
        # minus: cannot_exploit_penalty
        
        if tctx.ko_status == "GUARANTEED_KO":
            score += 50.0
            if tctx.is_ex:
                score += 30.0 # 2 prizes!
        elif tctx.ko_status == "PROBABLE_KO":
            score += 30.0
            if tctx.is_ex:
                score += 20.0
        elif tctx.ko_status == "CONDITIONAL_KO":
            score += 15.0
            
        # Support/Threat Value
        if tctx.attached_energy > 0:
            score += tctx.attached_energy * 10.0
            
        if "meowth" in tctx.card_name or "kirlia" in tctx.card_name or "pidgeot" in tctx.card_name or "drakloak" in tctx.card_name:
            score += 15.0
            
        # CANNOT EXPLOIT PENALTY (CRITICAL FIX)
        if tctx.ko_status == "NO_KO":
            # If we pull a high HP threat that we can't KO, we wall ourselves!
            if tctx.remaining_hp > 100:
                score -= 30.0 # High HP penalty
            elif tctx.best_incoming_damage == 0:
                score -= 20.0 # We have no attacks
                
            # If it's a threat and we can't kill it, pulling it up means it will hit us!
            if tctx.attached_energy >= 2:
                score -= 20.0 # Retaliation risk
                
        if self.enable_tracer:
            self._traces.append({
                "target_name": tctx.card_name,
                "target_hp": tctx.remaining_hp,
                "is_ex": tctx.is_ex,
                "attached_energy": tctx.attached_energy,
                "ko_status": tctx.ko_status,
                "best_incoming_damage": tctx.best_incoming_damage,
                "final_score": score
            })
            
        return score

def _card_category(card_data: dict) -> str:
    fields = card_data.get("fields", {})
    stage = fields.get("Stage (Pokémon)/Type (Energy and Trainer)", "")
    stage_lower = stage.lower()
    if "basic" in stage_lower or "stage" in stage_lower:
        return "Pokemon"
    elif "item" in stage_lower or "supporter" in stage_lower or "stadium" in stage_lower or "tool" in stage_lower:
        return "Trainer"
    elif "energy" in stage_lower:
        return "Energy"
    if card_data.get("attacks"):
        return "Pokemon"
    return "Unknown"
