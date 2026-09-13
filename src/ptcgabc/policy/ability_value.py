"""Phase D: Semantic Ability Intelligence.

Parses and categorizes Pokemon abilities to value them correctly in context.
"""

from dataclasses import dataclass
from typing import Any

@dataclass
class AbilityEvaluation:
    name: str
    categories: list[str]  # 'draw', 'search', 'energy_accel', 'heal', etc.
    context_score: float

class AbilityEvaluator:
    """Evaluates Pokemon abilities."""
    
    def evaluate(self, card_data: dict, state: dict) -> AbilityEvaluation:
        # Check if card has an ability in its attacks array (often represented there)
        # or in effect explanation.
        name = card_data.get("card_name", "")
        attacks = card_data.get("attacks", [])
        
        effect_text = ""
        ab_name = "Ability"
        for a in attacks:
            if a.get("damage", "") == "" and a.get("cost", "") == "":
                # Might be an ability
                effect_text += " " + a.get("effect", "").lower()
                ab_name = a.get("name", "")
                
        # Some abilities might just be in the fields if not in attacks
        if not effect_text:
            effect_text = card_data.get("fields", {}).get("Effect Explanation", "").lower()
            
        categories = []
        if "draw" in effect_text or "look at the top" in effect_text:
            categories.append("draw")
        if "search" in effect_text:
            categories.append("search")
        if "attach" in effect_text and "energy" in effect_text:
            categories.append("energy_accel")
        if "heal" in effect_text or "remove" in effect_text and "damage" in effect_text:
            categories.append("heal")
        if "switch" in effect_text:
            categories.append("switch")
        if "discard" in effect_text:
            categories.append("discard")
            
        score = 15.0 # Base score for ability
        
        hand = state.get("own_hand_count", 3)
        if "draw" in categories and hand <= 3:
            score += 15.0
        if "search" in categories:
            score += 10.0
        if "energy_accel" in categories:
            score += 12.0
            
        # Specific known abilities from candidates
        n = name.lower()
        if "drakloak" in n:
            categories.append("draw")
            score += 10.0 if hand <= 4 else 5.0
        if "meowth" in n:
            categories.append("draw")
            score += 12.0
        if "pidgeot" in n:
            categories.append("search")
            score += 15.0
            
        return AbilityEvaluation(
            name=ab_name,
            categories=categories,
            context_score=score
        )
