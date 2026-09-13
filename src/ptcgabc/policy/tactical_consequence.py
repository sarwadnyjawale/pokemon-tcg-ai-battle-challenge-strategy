"""Symbolic Tactical Consequence Evaluator (Zero-Step Planning).

Approximates 1-step lookahead by symbolically evaluating the strategic
consequence of taking an action before other available actions.
Forces optimal sequencing (e.g., attach energy before playing Research)
by penalizing actions that destroy guaranteed board developments.
"""

from typing import List, Dict

class TacticalConsequenceEvaluator:
    def __init__(self, lambda_weight: float = 1.0, enable_tracer: bool = False):
        self.lambda_weight = lambda_weight
        self.enable_tracer = enable_tracer
        self._traces = []

    def evaluate_consequence(self, action: Dict, state: Dict, legal_actions: List[Dict]) -> float:
        consequence_score = 0.0
        
        action_type = action.get("type", "")
        effect_category = action.get("effect_category", "")
        
        # Determine available parallel board-development actions
        has_attach = any(a.get("type") == "attach_energy" for a in legal_actions)
        has_evolve = any(a.get("type") == "evolve" for a in legal_actions)
        has_play_pokemon = any(a.get("type") == "play_pokemon" for a in legal_actions)
        
        # 1. Sequencing: Hand-altering trainers destroy guaranteed board actions
        #    If we discard or shuffle our hand, we lose the guaranteed ability
        #    to attach the energy or evolve the Pokemon we currently hold.
        if action_type == "play_trainer" and effect_category in ("draw", "search", "discard"):
            if has_attach:
                consequence_score -= 20.0
            if has_evolve:
                consequence_score -= 20.0
            if has_play_pokemon:
                consequence_score -= 10.0
                
        # 2. Sequencing: Turn-ending actions miss board-development opportunities
        if action_type in ("attack", "pass"):
            if has_attach:
                consequence_score -= 15.0
            if has_evolve:
                consequence_score -= 20.0
            if has_play_pokemon and action_type == "pass":
                consequence_score -= 10.0
                
        # 3. Positive Consequence: Establishing the board is intrinsically valuable
        if action_type == "attach_energy":
            consequence_score += 15.0 # Preserves hand, unlocks future attacks
            
        if action_type == "evolve":
            consequence_score += 20.0 # Permanent HP/attack buff
            
        if action_type == "play_pokemon":
            consequence_score += 10.0 # Bench stability
            
        final_consequence = self.lambda_weight * consequence_score
        
        if self.enable_tracer:
            self._traces.append({
                "action": action_type,
                "effect": effect_category,
                "has_attach": has_attach,
                "has_evolve": has_evolve,
                "has_play_pokemon": has_play_pokemon,
                "base_consequence": consequence_score,
                "weighted_consequence": final_consequence
            })
            
        return final_consequence
