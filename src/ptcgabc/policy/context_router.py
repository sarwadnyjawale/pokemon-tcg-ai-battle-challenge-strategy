"""Context-Aware Decision Router for real CABT.

Routes decisions based on the actual CABT select type and context.
Each context gets a specialized handler that understands the option semantics.

CABT select contexts (empirically verified):
  0:  MAIN — play/attach/attack/evolve/retreat/end
  1:  SETUP_ACTIVE_POKEMON — choose active from hand
  2:  SETUP_BENCH_POKEMON — choose bench from hand
  3:  SWITCH — choose bench Pokemon to swap in
  4:  TO_ACTIVE — move card to active
  5:  TO_BENCH — move card to bench
  7:  TO_HAND — pick card to add to hand (search result)
  8:  DISCARD — choose card to discard
  21: ATTACH_FROM — source for energy attach
  22: ATTACH_TO — target for energy attach
  30: DISCARD_ENERGY — choose energy to discard
  38: DRAW_COUNT — choose how many to draw
  41: IS_FIRST — choose first/second player (deck confirm)

RULES:
  - Only visible information used.
  - Every handler returns a valid option index.
  - Unknown contexts fall back to first option (never crash).
"""

from __future__ import annotations

from typing import Any, Optional

from ..environment.cabt_observation_parser import CabtGameState, CabtOption
from ..environment.enriched_adapter import (
    EnrichedAction,
    enrich_options,
    build_enriched_feature_dict,
    OPT_ATTACK, OPT_EVOLVE, OPT_ATTACH, OPT_PLAY, OPT_ABILITY,
    OPT_RETREAT, OPT_END, OPT_CARD, OPT_NUMBER, OPT_YES, OPT_NO,
    _load_card_db,
)


class ContextRouter:
    """Routes CABT decisions to context-specific handlers.

    select_context determines which handler fires.
    Each handler receives the enriched options and board state.
    """

    def __init__(
        self,
        main_policy=None,
        card_scorer=None,
        tempo_scorer=None,
        safety_gate=None,
        target_scorer=None,
        tactical_scorer=None,
    ):
        self.main_policy = main_policy
        self.card_scorer = card_scorer
        self.tempo_scorer = tempo_scorer
        self.safety_gate = safety_gate
        self.tactical_scorer = tactical_scorer
        
        # Load the new Tactical Target Context Scorer
        if target_scorer is None:
            try:
                from .target_context import TargetSelectionScorer
                self.target_scorer = TargetSelectionScorer()
            except ImportError:
                self.target_scorer = None
        else:
            self.target_scorer = target_scorer

        self.name = "ContextRouter"
        self.game_count = 0
        self._card_db = None

    def reset(self):
        self.game_count += 1

    def _get_card_db(self):
        if self._card_db is None:
            self._card_db = _load_card_db()
        return self._card_db

    def select_action(
        self,
        legal_actions: list[dict],
        game_state: dict,
        turn: int = 0,
    ) -> tuple[int, str]:
        """Standard agent interface — used by the enriched game runner."""
        if not legal_actions:
            raise ValueError("ContextRouter: No legal actions")

        # Determine context from the first action's raw data
        ctx = self._infer_context(legal_actions, game_state)

        if ctx == 0:
            return self._handle_main(legal_actions, game_state, turn)
        elif ctx in (1, 2):
            return self._handle_setup_pokemon(legal_actions, game_state, ctx)
        elif ctx == 3:
            return self._handle_switch(legal_actions, game_state)
        elif ctx in (5, 4):
            return self._handle_to_area(legal_actions, game_state, ctx)
        elif ctx == 7:
            return self._handle_search_result(legal_actions, game_state)
        elif ctx in (8, 30):
            return self._handle_discard(legal_actions, game_state, ctx)
        elif ctx == 38:
            return self._handle_draw_count(legal_actions, game_state)
        elif ctx in (21, 22):
            return self._handle_attach_target(legal_actions, game_state, ctx)
        elif ctx == 41:
            return 0, "deck_confirm_first"
        else:
            return self._handle_generic(legal_actions, game_state, ctx)

    def _infer_context(self, legal_actions: list[dict], game_state: dict) -> int:
        """Infer the select context from the action dicts or game state."""
        # Check if game_state carries context info from enriched adapter
        if "select_context" in game_state:
            return game_state["select_context"]
        # Infer from action types
        types = set(a.get("cabt_option_type", -1) for a in legal_actions)
        # MAIN context has action types like PLAY(7), ATTACH(8), ATTACK(13), END(14)
        if OPT_END in types or OPT_ATTACK in types:
            return 0
        if all(a.get("cabt_option_type") == OPT_CARD for a in legal_actions):
            # Card selection — context depends on card areas
            areas = set(a.get("raw", {}).get("area", -1) for a in legal_actions)
            if 2 in areas:  # HAND
                return 7  # likely search or discard
            return 7
        if all(a.get("cabt_option_type") == OPT_NUMBER for a in legal_actions):
            return 38
        if types == {OPT_YES, OPT_NO} or types == {OPT_YES} or types == {OPT_NO}:
            return 41
        return 0

    # ------------------------------------------------------------------
    # MAIN context (ctx=0): the core strategic decision
    # ------------------------------------------------------------------

    def _handle_main(
        self,
        actions: list[dict],
        state: dict,
        turn: int,
    ) -> tuple[int, str]:
        """MAIN context: strategic decision among play/attach/evolve/attack/end.

        This is where the tempo policy and safety gate fire.
        The key insight: we should NOT blindly always attack.
        We evaluate each option's strategic value in the current state.
        """
        scores = []
        for i, a in enumerate(actions):
            score = self._score_main_action(a, state, turn)
            
            # Symbolic Consequence Evaluator (0-step planning approximation)
            if self.tactical_scorer:
                consequence_delta = self.tactical_scorer.evaluate_consequence(a, state, actions)
                score += consequence_delta

            scores.append((i, score))

        # Apply safety gate: penalize END if productive actions exist
        if self.safety_gate:
            scores = self.safety_gate.adjust_scores(scores, actions, state)

        scores.sort(key=lambda x: x[1], reverse=True)
        best_idx, best_score = scores[0]
        reason = f"main_ctx_score={best_score:.2f}_type={actions[best_idx].get('type','?')}"
        return best_idx, reason

    def _score_main_action(self, action: dict, state: dict, turn: int) -> float:
        """Score a single MAIN-context action.

        Integrates tempo scoring if available, otherwise uses built-in logic.
        """
        if self.tempo_scorer:
            return self.tempo_scorer.score(action, state, turn)

        # Built-in fallback scoring
        opt_type = action.get("cabt_option_type", -1)
        atype = action.get("type", "")
        damage = action.get("damage", 0)
        phase = state.get("game_phase", "midgame")
        own_prizes = state.get("own_prizes", state.get("our_prizes", 6))
        opp_prizes = state.get("opp_prizes", state.get("opp_prizes", 6))

        score = 0.0

        if opt_type == OPT_ATTACK:
            # Attack value depends on damage and board state
            score = 40.0  # base: attacks advance the game
            if damage > 0:
                opp_hp = state.get("opp_active_hp", 100)
                if opp_hp and damage >= opp_hp:
                    score += 60.0  # KO is highly valuable
                else:
                    score += min(damage / 10.0, 20.0)  # damage scaling
            if own_prizes <= 2:
                score += 15.0  # endgame urgency

        elif opt_type == OPT_EVOLVE:
            score = 35.0  # evolution is typically very valuable
            if phase in ("opening", "early"):
                score += 10.0  # early evolution is crucial for setup

        elif opt_type == OPT_ATTACH:
            score = 25.0  # energy enables attacks
            if not state.get("energy_attached", False):
                score += 5.0  # first energy this turn

        elif opt_type == OPT_PLAY:
            card_cat = action.get("card_category", "")
            effect = action.get("effect_category", "")
            if card_cat == "Pokemon":
                score = 20.0
                bench = state.get("own_bench_count", state.get("our_bench_count", 0))
                if bench < 2 and phase in ("opening", "early"):
                    score += 10.0  # bench development
            elif card_cat == "Trainer":
                score = 18.0
                if effect == "draw" and state.get("own_hand_count", state.get("our_hand_count", 3)) <= 2:
                    score += 10.0
                elif effect == "search":
                    score += 8.0
                elif effect == "switch":
                    # Only valuable if we need to switch
                    score += 3.0
            elif card_cat == "Energy":
                score = 22.0  # playing energy from hand

        elif opt_type == OPT_ABILITY:
            score = 22.0  # abilities are generally useful

        elif opt_type == OPT_RETREAT:
            own_hp_frac = state.get("own_active_hp_fraction", 1.0)
            if own_hp_frac < 0.2:
                score = 30.0  # retreat to save a dying Pokemon
            else:
                score = 5.0  # low priority normally

        elif opt_type == OPT_END:
            score = -5.0  # should only end when nothing productive remains

        return score

    # ------------------------------------------------------------------
    # Setup Pokemon contexts (ctx=1,2)
    # ------------------------------------------------------------------

    def _handle_setup_pokemon(
        self,
        actions: list[dict],
        state: dict,
        ctx: int,
    ) -> tuple[int, str]:
        """Choose active (ctx=1) or bench (ctx=2) Pokemon from hand.

        Prefer: high-HP basics, attackers with energy already attached,
        evolution bases for the main attacker line.
        """
        if self.card_scorer:
            scores = [
                (i, self.card_scorer.score_for_setup(a, state, is_active=(ctx == 1)))
                for i, a in enumerate(actions)
            ]
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[0][0], f"setup_ctx{ctx}_card_score"

        # Fallback: prefer higher HP Pokemon, prefer evolution bases
        db = self._get_card_db()
        best_i, best_score = 0, -1.0
        for i, a in enumerate(actions):
            cid = a.get("card_id", 0)
            cdata = db.get(cid, {})
            hp = 0
            try:
                hp = int(cdata.get("fields", {}).get("HP", "0"))
            except (ValueError, TypeError):
                pass
            score = float(hp)
            # Bonus for evolution bases of our main line
            name = cdata.get("card_name", "").lower()
            if "dreepy" in name:
                score += 50  # evolution base for Dragapult
            if score > best_score:
                best_score = score
                best_i = i
        return best_i, f"setup_hp_score={best_score:.0f}"

    # ------------------------------------------------------------------
    # Switch context (ctx=3)
    # ------------------------------------------------------------------

    def _handle_switch(self, actions: list[dict], state: dict) -> tuple[int, str]:
        """Choose which bench Pokemon to switch in.

        Prefer: ready attackers > high HP > evolution targets.
        """
        # Check if we are selecting opponent's Pokemon (Boss's Orders)
        is_opponent_target = False
        if actions:
            p_idx = actions[0].get("raw", {}).get("playerIndex", -1)
            your_idx = state.get("your_index", 0)
            if p_idx >= 0 and p_idx != your_idx:
                is_opponent_target = True

        if is_opponent_target and self.target_scorer:
            scores = [
                (i, self.target_scorer.score_target(a, state))
                for i, a in enumerate(actions)
            ]
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[0][0], "target_selection_score"

        if self.card_scorer:
            scores = [
                (i, self.card_scorer.score_for_switch(a, state))
                for i, a in enumerate(actions)
            ]
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[0][0], "switch_card_score"

        # Fallback: first option
        return 0, "switch_fallback"

    # ------------------------------------------------------------------
    # Search result (ctx=7): pick card to add to hand
    # ------------------------------------------------------------------

    def _handle_search_result(self, actions: list[dict], state: dict) -> tuple[int, str]:
        """Choose which card to take from a search.

        Highly context-dependent — the card scorer handles this.
        """
        if self.card_scorer:
            scores = [
                (i, self.card_scorer.score_for_search(a, state))
                for i, a in enumerate(actions)
            ]
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[0][0], "search_card_score"

        # Fallback: prefer Pokemon > Energy > Trainer
        db = self._get_card_db()
        best_i, best_score = 0, -1.0
        for i, a in enumerate(actions):
            cid = a.get("card_id", 0)
            cdata = db.get(cid, {})
            score = 0.0
            # Simple heuristic: Pokemon for setup
            attacks = cdata.get("attacks", [])
            if attacks:
                score = 10.0  # has attacks, likely Pokemon
            if score > best_score:
                best_score = score
                best_i = i
        return best_i, f"search_fallback_score={best_score:.0f}"

    # ------------------------------------------------------------------
    # Discard context (ctx=8,30)
    # ------------------------------------------------------------------

    def _handle_discard(
        self, actions: list[dict], state: dict, ctx: int
    ) -> tuple[int, str]:
        """Choose which card/energy to discard.

        Prefer to discard: duplicates, least useful cards, excess energy.
        """
        if self.card_scorer:
            # Lower score = discard first
            scores = [
                (i, -self.card_scorer.score_for_search(a, state))
                for i, a in enumerate(actions)
            ]
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[0][0], f"discard_ctx{ctx}_card_score"

        return 0, f"discard_ctx{ctx}_fallback"

    # ------------------------------------------------------------------
    # Draw count (ctx=38)
    # ------------------------------------------------------------------

    def _handle_draw_count(self, actions: list[dict], state: dict) -> tuple[int, str]:
        """Choose how many cards to draw. Usually want maximum."""
        # Pick highest number available
        best_i, best_num = 0, -1
        for i, a in enumerate(actions):
            num = a.get("raw", {}).get("number", 0)
            if isinstance(num, int) and num > best_num:
                best_num = num
                best_i = i
        return best_i, f"draw_count={best_num}"

    # ------------------------------------------------------------------
    # Attach target contexts (ctx=21,22)
    # ------------------------------------------------------------------

    def _handle_attach_target(
        self, actions: list[dict], state: dict, ctx: int
    ) -> tuple[int, str]:
        """Choose attach source (21) or target (22).

        For target: prefer active attacker, then bench attackers needing energy.
        """
        if ctx == 22:
            # Prefer active (inPlayArea=4) over bench (inPlayArea=5)
            for i, a in enumerate(actions):
                raw = a.get("raw", {})
                if raw.get("inPlayArea") == 4:
                    return i, "attach_to_active"
            return 0, "attach_target_fallback"

        return 0, f"attach_ctx{ctx}_fallback"

    # ------------------------------------------------------------------
    # To-area contexts (ctx=4,5)
    # ------------------------------------------------------------------

    def _handle_to_area(
        self, actions: list[dict], state: dict, ctx: int
    ) -> tuple[int, str]:
        """Move card to active(4) or bench(5)."""
        return 0, f"to_area_ctx{ctx}"

    # ------------------------------------------------------------------
    # Generic fallback
    # ------------------------------------------------------------------

    def _handle_generic(
        self, actions: list[dict], state: dict, ctx: int
    ) -> tuple[int, str]:
        """Fallback for unknown contexts. Check if it's an opponent target."""
        if actions and self.target_scorer:
            p_idx = actions[0].get("raw", {}).get("playerIndex", -1)
            your_idx = state.get("your_index", 0)
            if p_idx >= 0 and p_idx != your_idx:
                scores = [
                    (i, self.target_scorer.score_target(a, state))
                    for i, a in enumerate(actions)
                ]
                scores.sort(key=lambda x: x[1], reverse=True)
                return scores[0][0], f"target_selection_ctx{ctx}"

        return 0, f"generic_ctx{ctx}_fallback"
