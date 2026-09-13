"""Card-Level Intelligence for CABT card-selection decisions.

Scores individual cards based on their verified properties from the
canonical card database, conditioned on the current game state and
selection context.

RULES:
  - Only uses verified card data from canonical_cards.json
  - Never hallucinate card semantics
  - Card value is context-dependent (setup vs midgame vs endgame)
  - Only visible information used
"""

from __future__ import annotations

from typing import Any

from ..environment.enriched_adapter import (
    _load_card_db,
    _parse_damage,
    _card_category,
    _card_stage,
    _trainer_effect_category,
)


class CardValueScorer:
    """Scores cards for selection contexts based on canonical card DB."""

    def __init__(self, card_db: dict[int, dict] | None = None):
        self._db = card_db or _load_card_db()

    def _lookup(self, action: dict) -> dict:
        cid = action.get("card_id", 0)
        return self._db.get(cid, {})

    def score_for_setup(
        self, action: dict, state: dict, is_active: bool = False
    ) -> float:
        """Score card for setup selection (choose active/bench Pokemon).

        For active: prefer high HP, ready to attack, evolution base.
        For bench: prefer evolution bases, draw engines, backup attackers.
        """
        cdata = self._lookup(action)
        if not cdata:
            return 0.0

        score = 0.0
        hp = 0
        try:
            hp = int(cdata.get("fields", {}).get("HP", "0"))
        except (ValueError, TypeError):
            pass

        name = cdata.get("card_name", "").lower()
        attacks = cdata.get("attacks", [])
        stage = _card_stage(cdata)

        if is_active:
            # For active: tanky basics that can evolve or attack
            score += hp / 10.0  # HP is important for survival
            # Prefer evolution bases for our main line
            if "dreepy" in name:
                score += 15.0  # Dragapult line base
            elif "ralts" in name:
                score += 12.0  # Gardevoir line base
            # Prefer basics that can attack cheaply
            for atk in attacks:
                dmg = _parse_damage(atk.get("damage", ""))
                cost = atk.get("cost", "")
                cost_len = len(cost.replace(" ", "")) if cost else 0
                if cost_len <= 1 and dmg > 0:
                    score += 8.0  # cheap attack available
        else:
            # For bench: evolution bases, draw engines
            if "dreepy" in name:
                score += 20.0  # need bench Dreepy for evolution
            elif "ralts" in name:
                score += 18.0
            elif "meowth" in name:
                score += 12.0  # draw engine
            elif "budew" in name:
                score += 10.0
            elif "jirachi" in name:
                score += 8.0
            score += hp / 20.0

        return score

    def score_for_switch(self, action: dict, state: dict) -> float:
        """Score bench Pokemon as switch-in target.

        Prefer: ready attackers, high HP, not about to be KO'd.
        """
        cdata = self._lookup(action)
        if not cdata:
            return 0.0

        score = 0.0
        hp = 0
        try:
            hp = int(cdata.get("fields", {}).get("HP", "0"))
        except (ValueError, TypeError):
            pass

        attacks = cdata.get("attacks", [])
        name = cdata.get("card_name", "").lower()

        score += hp / 10.0  # prefer tanky switch-in

        # Prefer evolved forms (higher stage = stronger)
        if "ex" in name:
            score += 15.0
        stage = _card_stage(cdata)
        if "Stage 2" in stage:
            score += 10.0
        elif "Stage 1" in stage:
            score += 5.0

        # Prefer Pokemon with attacks
        for atk in attacks:
            dmg = _parse_damage(atk.get("damage", ""))
            score += min(dmg / 20.0, 5.0)

        return score

    def score_for_search(self, action: dict, state: dict) -> float:
        """Score card for search-to-hand selection.

        Context-dependent: what do we NEED right now?
        """
        cdata = self._lookup(action)
        if not cdata:
            return 0.0

        score = 0.0
        cat = _card_category(cdata)
        name = cdata.get("card_name", "").lower()
        phase = state.get("game_phase", "midgame")
        bench = state.get("own_bench_count", state.get("our_bench_count", 0))
        hand = state.get("own_hand_count", state.get("our_hand_count", 3))
        own_prizes = state.get("own_prizes", state.get("our_prizes", 6))

        if cat == "Pokemon":
            hp = 0
            try:
                hp = int(cdata.get("fields", {}).get("HP", "0"))
            except (ValueError, TypeError):
                pass
            stage = _card_stage(cdata)

            if phase in ("opening", "early"):
                # Need basics for bench
                if "Basic" in stage and bench < 3:
                    score += 15.0
                # Need evolution pieces
                if "Stage 1" in stage or "Stage 2" in stage:
                    score += 12.0
            else:
                # Mid/late: prefer strong attackers
                if "ex" in name:
                    score += 12.0
                score += hp / 20.0

        elif cat == "Trainer":
            effect = _trainer_effect_category(cdata)
            if effect == "draw" and hand <= 2:
                score += 18.0  # desperate for cards
            elif effect == "draw":
                score += 10.0
            elif effect == "search":
                score += 12.0  # search chains
            elif effect == "switch":
                score += 6.0
            elif effect == "evolve":
                # Rare Candy
                score += 14.0

        elif cat == "Energy":
            # Energy is important if we need it for attacks
            score += 8.0
            if phase in ("opening", "early"):
                score += 4.0  # energy is critical early

        return score

    def score_for_discard(self, action: dict, state: dict) -> float:
        """Score card for discard selection (lower = discard first).

        Inverse of search score — discard what we need least.
        """
        return -self.score_for_search(action, state)

    def score_for_attach_target(self, action: dict, state: dict) -> float:
        """Score a Pokemon as an energy attachment target.

        Prefer: active attacker needing energy > bench attacker close to ready.
        """
        raw = action.get("raw", {})
        area = raw.get("inPlayArea", 0)

        if area == 4:  # active
            return 20.0  # active always high priority for energy
        elif area == 5:  # bench
            return 8.0  # bench gets energy for future

        return 5.0
