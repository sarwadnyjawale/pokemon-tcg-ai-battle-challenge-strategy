"""Target Selection Intelligence for real-CABT.

Evaluates strategic targets on the opponent's board using tactical feasibility.

RULES:
  - Only visible information used.
  - Tightly coupled to AttackEvaluator to ensure targets can actually be exploited.
"""

from __future__ import annotations
from typing import Any

class REJECTED_EXP006_TargetSelectionScorer:
    """Old static target scorer that caused a -11.6pp regression."""

    def __init__(self, card_db: dict[int, dict] | None = None):
        from ..environment.enriched_adapter import _load_card_db
        self._db = card_db or _load_card_db()

    def score_target(self, action: dict, state: dict) -> float:
        score = 10.0
        raw = action.get("raw", {})
        target_area = raw.get("area", -1)
        target_idx = raw.get("index", -1)
        player_idx = raw.get("playerIndex", -1)

        if player_idx == state.get("your_index", 0):
            return 0.0

        target_pokemon = None
        for p in state.get("players", []):
            if p.get("player_index") == player_idx:
                if target_area == 4:
                    if p.get("active"): target_pokemon = p["active"][0]
                elif target_area == 5:
                    if target_idx < len(p["bench"]): target_pokemon = p["bench"][target_idx]

        if not target_pokemon:
            cid = action.get("card_id", 0)
            cdata = self._db.get(cid, {})
            name = cdata.get("card_name", "").lower()
            if "ex" in name: score += 15.0
            if "kirlia" in name or "pidgeot" in name: score += 12.0
            return score

        cid = target_pokemon.card_id if hasattr(target_pokemon, "card_id") else target_pokemon.get("id", 0)
        cdata = self._db.get(cid, {})
        name = cdata.get("card_name", "").lower()
        
        is_ex = "ex" in name
        if is_ex: score += 25.0

        hp = target_pokemon.hp if hasattr(target_pokemon, "hp") else target_pokemon.get("hp", 100)
        if hp <= 60: score += 20.0
        elif hp <= 90: score += 10.0

        energies = target_pokemon.energies if hasattr(target_pokemon, "energies") else target_pokemon.get("energies", [])
        score += len(energies) * 15.0

        if "meowth" in name or "kirlia" in name or "pidgeot" in name or "drakloak" in name:
            score += 15.0

        return score
