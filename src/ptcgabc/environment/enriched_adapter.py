"""Enriched CABT Action Adapter + Benchmark Runner with Decision Telemetry.

Fixes the critical information-loss bottleneck identified in Phase 0 audit:
CABT options carry structural parameters (attackId, index, area) but NOT
gameplay semantics (damage, effect_category, energy_cost). This module
enriches options using the board state and canonical card database.

Also provides a reproducible benchmark runner that records per-decision
telemetry for Phase 3 failure analysis.

RULES:
  - Only uses VISIBLE information from the CABT observation.
  - All results labeled REAL_CABT_LOCAL.
  - Never fabricates card data — uses canonical_cards.json lookup.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .cabt_observation_parser import (
    CabtGameState,
    CabtOption,
    CabtPlayerState,
    CabtInPlayCard,
    build_feature_dict,
    parse_observation,
    extract_legal_options,
)
from .cabt_action_adapter import build_deck_action, build_action_from_option_index


# ---------------------------------------------------------------------------
# Card database loader
# ---------------------------------------------------------------------------

_CARD_DB: dict[int, dict] | None = None


def _load_card_db() -> dict[int, dict]:
    """Load canonical card database for attack/effect lookup."""
    global _CARD_DB
    if _CARD_DB is not None:
        return _CARD_DB

    db_path = Path(__file__).parent.parent.parent.parent / "data" / "processed" / "canonical_cards.json"
    if not db_path.exists():
        _CARD_DB = {}
        return _CARD_DB

    raw = json.loads(db_path.read_text(encoding="utf-8"))
    cards = raw.get("cards", [])
    db: dict[int, dict] = {}
    for c in cards:
        try:
            cid = int(c["card_id"])
        except (ValueError, KeyError):
            continue
        db[cid] = c
    _CARD_DB = db
    return _CARD_DB


def _parse_damage(dmg_str: str) -> int:
    """Parse damage string like '200', '30+', '50x' into base integer."""
    if not dmg_str:
        return 0
    cleaned = dmg_str.strip().rstrip("+x×?")
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _card_stage(card_data: dict) -> str:
    """Extract stage from card data."""
    fields = card_data.get("fields", {})
    stage = fields.get("Stage (Pokémon)/Type (Energy and Trainer)", "")
    if "Basic" in stage:
        return "Basic"
    elif "Stage 1" in stage or "STAGE1" in stage:
        return "Stage 1"
    elif "Stage 2" in stage or "STAGE2" in stage:
        return "Stage 2"
    return stage


def _card_category(card_data: dict) -> str:
    """Determine if card is Pokemon, Trainer, or Energy."""
    fields = card_data.get("fields", {})
    stage = fields.get("Stage (Pokémon)/Type (Energy and Trainer)", "")
    stage_lower = stage.lower()
    if "basic" in stage_lower or "stage" in stage_lower:
        return "Pokemon"
    elif "item" in stage_lower or "supporter" in stage_lower or "stadium" in stage_lower or "tool" in stage_lower:
        return "Trainer"
    elif "energy" in stage_lower:
        return "Energy"
    # Check attacks — Pokemon have attacks
    if card_data.get("attacks"):
        return "Pokemon"
    return "Unknown"


def _trainer_effect_category(card_data: dict) -> str:
    """Infer trainer effect category from card data."""
    name = card_data.get("card_name", "").lower()
    attacks = card_data.get("attacks", [])
    effect_text = ""
    for a in attacks:
        effect_text += " " + a.get("effect", "").lower()

    if any(kw in effect_text for kw in ["draw", "look at the top"]):
        return "draw"
    if any(kw in effect_text for kw in ["search", "find", "look"]):
        return "search"
    if any(kw in effect_text for kw in ["discard", "remove"]):
        return "discard"
    if any(kw in effect_text for kw in ["switch", "retreat"]):
        return "switch"
    if any(kw in effect_text for kw in ["heal", "remove damage"]):
        return "heal"

    # Known cards by name
    known = {
        "professor's research": "draw",
        "iono": "draw",
        "carmine": "draw",
        "ultra ball": "search",
        "buddy-buddy poffin": "search",
        "arven": "search",
        "boss's orders": "gust",
        "night stretcher": "search",
        "rare candy": "evolve",
        "crushing hammer": "discard",
        "counter catcher": "gust",
        "earthen vessel": "search",
        "pal pad": "search",
    }
    for kn, cat in known.items():
        if kn in name:
            return cat

    return "utility"


# ---------------------------------------------------------------------------
# Enriched action dict builder
# ---------------------------------------------------------------------------

@dataclass
class EnrichedAction:
    """An action dict enriched with gameplay semantics from the CABT observation."""
    option_index: int
    option_type: int       # raw CABT option type
    action_type: str       # string label (attack, attach_energy, play_trainer, etc.)

    # Populated from board state + card DB
    card_id: int = 0
    card_name: str = ""
    damage: int = 0
    effect_category: str = ""
    energy_cost: int = 0
    hand_change: int = 0
    is_supporter: bool = False
    card_category: str = ""  # Pokemon, Trainer, Energy
    targets_bench: bool = False

    # Context
    raw: dict = field(default_factory=dict)

    def to_agent_dict(self) -> dict:
        """Convert to the dict format expected by Phase 3/4 agents."""
        return {
            "type": self.action_type,
            "cabt_option_type": self.option_type,
            "cabt_option_index": self.option_index,
            "damage": self.damage,
            "effect_category": self.effect_category,
            "energy_cost": self.energy_cost,
            "hand_change": self.hand_change,
            "card_id": self.card_id,
            "card_name": self.card_name,
            "card_category": self.card_category,
            "is_supporter": self.is_supporter,
            "raw": self.raw,
        }


# OptionType constants (from cabt_types.py)
OPT_NUMBER = 0
OPT_YES = 1
OPT_NO = 2
OPT_CARD = 3
OPT_TOOL_CARD = 4
OPT_ENERGY_CARD = 5
OPT_ENERGY = 6
OPT_PLAY = 7
OPT_ATTACH = 8
OPT_EVOLVE = 9
OPT_ABILITY = 10
OPT_DISCARD = 11
OPT_RETREAT = 12
OPT_ATTACK = 13
OPT_END = 14
OPT_SKILL = 15

_ACTION_TYPE_MAP = {
    OPT_NUMBER: "numbered_choice",
    OPT_YES: "yes",
    OPT_NO: "no",
    OPT_CARD: "card_from_area",
    OPT_TOOL_CARD: "card_from_area",
    OPT_ENERGY_CARD: "energy_card",
    OPT_ENERGY: "energy",
    OPT_PLAY: "play_from_hand",
    OPT_ATTACH: "attach_energy",
    OPT_EVOLVE: "evolve",
    OPT_ABILITY: "use_ability",
    OPT_DISCARD: "discard",
    OPT_RETREAT: "retreat",
    OPT_ATTACK: "attack",
    OPT_END: "pass",
    OPT_SKILL: "skill",
}


_CARD_MIN_ATTACK_ID = {}

def enrich_options(
    gs: CabtGameState,
    card_db: dict[int, dict] | None = None,
) -> list[EnrichedAction]:
    """Convert CABT options into enriched action dicts with gameplay semantics."""
    if card_db is None:
        card_db = _load_card_db()

    if gs.select is None or not gs.select.options:
        return []

    own = gs.own_player
    hand_cards = []
    if own and own.hand:
        hand_cards = [(c.card_id, c.serial) for c in own.hand]

    active = own.active[0] if own and own.active else None

    # Pre-scan attack IDs to maintain the min-ID cache for mapping
    if active:
        for opt in gs.select.options:
            if opt.option_type == OPT_ATTACK:
                aid = opt.raw.get("attackId", -1)
                if aid >= 0:
                    cid = active.card_id
                    if cid not in _CARD_MIN_ATTACK_ID:
                        _CARD_MIN_ATTACK_ID[cid] = aid
                    else:
                        _CARD_MIN_ATTACK_ID[cid] = min(_CARD_MIN_ATTACK_ID[cid], aid)

    enriched: list[EnrichedAction] = []
    for opt in gs.select.options:
        ea = EnrichedAction(
            option_index=opt.index,
            option_type=opt.option_type,
            action_type=_ACTION_TYPE_MAP.get(opt.option_type, f"unknown_{opt.option_type}"),
            raw=opt.raw,
        )

        if opt.option_type == OPT_ATTACK:
            if active:
                cdata = card_db.get(active.card_id, {})
                attacks = cdata.get("attacks", [])
                attack_id = opt.raw.get("attackId", -1)
                
                # Use dynamic mapping
                mapped_idx = -1
                if active.card_id in _CARD_MIN_ATTACK_ID and attack_id >= 0:
                    mapped_idx = attack_id - _CARD_MIN_ATTACK_ID[active.card_id]
                
                if 0 <= mapped_idx < len(attacks):
                    atk = attacks[mapped_idx]
                    ea.damage = _parse_damage(atk.get("damage", ""))
                    ea.card_name = atk.get("name", "")
                    cost_str = atk.get("cost", "")
                    ea.energy_cost = len(cost_str.replace(" ", "")) if cost_str else 0
                ea.card_id = active.card_id
            ea.action_type = "attack"

        elif opt.option_type == OPT_PLAY:
            # Playing a card from hand
            hand_idx = opt.raw.get("index", 0)
            if hand_idx < len(hand_cards):
                cid = hand_cards[hand_idx][0]
                ea.card_id = cid
                cdata = card_db.get(cid, {})
                ea.card_name = cdata.get("card_name", "")
                cat = _card_category(cdata)
                ea.card_category = cat
                if cat == "Pokemon":
                    ea.action_type = "play_pokemon"
                elif cat == "Trainer":
                    ea.action_type = "play_trainer"
                    ea.effect_category = _trainer_effect_category(cdata)
                    fields = cdata.get("fields", {})
                    stage = fields.get("Stage (Pokémon)/Type (Energy and Trainer)", "").lower()
                    ea.is_supporter = "supporter" in stage
                elif cat == "Energy":
                    ea.action_type = "attach_energy"

        elif opt.option_type == OPT_ATTACH:
            ea.action_type = "attach_energy"
            hand_idx = opt.raw.get("index", 0)
            if hand_idx < len(hand_cards):
                ea.card_id = hand_cards[hand_idx][0]
                cdata = card_db.get(ea.card_id, {})
                ea.card_name = cdata.get("card_name", "")

        elif opt.option_type == OPT_EVOLVE:
            ea.action_type = "evolve"
            hand_idx = opt.raw.get("area", 0)
            # The evolution target is at inPlayArea/inPlayIndex
            # The evolving card is from hand at index
            idx = opt.raw.get("index", 0)
            if idx < len(hand_cards):
                ea.card_id = hand_cards[idx][0] if opt.raw.get("area", 0) == 2 else 0
                cdata = card_db.get(ea.card_id, {})
                ea.card_name = cdata.get("card_name", "")

        elif opt.option_type == OPT_ABILITY:
            ea.action_type = "use_ability"
            # Abilities are from Pokemon on the board
            area = opt.raw.get("area", 0)
            idx = opt.raw.get("index", 0)
            if area == 4 and active:  # active
                ea.card_id = active.card_id
                cdata = card_db.get(ea.card_id, {})
                ea.card_name = cdata.get("card_name", "")
            elif area == 5 and own and idx < len(own.bench):  # bench
                bench_mon = own.bench[idx]
                ea.card_id = bench_mon.card_id
                cdata = card_db.get(ea.card_id, {})
                ea.card_name = cdata.get("card_name", "")

        elif opt.option_type == OPT_RETREAT:
            ea.action_type = "retreat"
            if active:
                ea.card_id = active.card_id
                # Retreat cost from card DB
                cdata = card_db.get(active.card_id, {})
                retreat_str = cdata.get("fields", {}).get("Retreat", "")
                ea.energy_cost = int(retreat_str) if retreat_str.isdigit() else 0

        elif opt.option_type == OPT_END:
            ea.action_type = "pass"

        elif opt.option_type == OPT_CARD:
            ea.action_type = "card_from_area"
            # Generic card selection — used for various contexts
            area = opt.raw.get("area", 0)
            idx = opt.raw.get("index", 0)
            player_idx = opt.raw.get("playerIndex", gs.your_index)
            # Area 2 = hand
            if area == 2 and idx < len(hand_cards):
                ea.card_id = hand_cards[idx][0]
                cdata = card_db.get(ea.card_id, {})
                ea.card_name = cdata.get("card_name", "")
                ea.card_category = _card_category(cdata)
            # Area 5 = bench
            elif area == 5:
                target_player = gs.players[player_idx] if player_idx < len(gs.players) else None
                if target_player and idx < len(target_player.bench):
                    bench_mon = target_player.bench[idx]
                    ea.card_id = bench_mon.card_id
                    cdata = card_db.get(ea.card_id, {})
                    ea.card_name = cdata.get("card_name", "")
                    ea.card_category = "Pokemon"
            # Area 4 = active
            elif area == 4:
                target_player = gs.players[player_idx] if player_idx < len(gs.players) else None
                if target_player and target_player.active:
                    ea.card_id = target_player.active[0].card_id
                    cdata = card_db.get(ea.card_id, {})
                    ea.card_name = cdata.get("card_name", "")
                    ea.card_category = "Pokemon"
            # Area 3 = discard
            elif area == 3:
                target_player = gs.players[player_idx] if player_idx < len(gs.players) else None
                if target_player and idx < len(target_player.discard):
                    disc = target_player.discard[idx]
                    if isinstance(disc, dict):
                        ea.card_id = int(disc.get("id", 0))
                    elif hasattr(disc, "card_id"):
                        ea.card_id = disc.card_id
                    cdata = card_db.get(ea.card_id, {})
                    ea.card_name = cdata.get("card_name", "")
                    ea.card_category = _card_category(cdata)
            # Area 1 = deck (cards revealed during search/look)
            elif area == 1:
                # During search, card_id may be in the option raw data
                card_id_raw = opt.raw.get("cardId", opt.raw.get("serial", 0))
                if card_id_raw:
                    ea.card_id = int(card_id_raw) if card_id_raw else 0
                    cdata = card_db.get(ea.card_id, {})
                    ea.card_name = cdata.get("card_name", "")
                    ea.card_category = _card_category(cdata)
            # Area 12 = looking (search results visible)
            elif area == 12:
                # During look/search, use the card serial/id if available
                card_id_raw = opt.raw.get("cardId", opt.raw.get("serial", 0))
                if card_id_raw:
                    ea.card_id = int(card_id_raw) if card_id_raw else 0
                    cdata = card_db.get(ea.card_id, {})
                    ea.card_name = cdata.get("card_name", "")
                    ea.card_category = _card_category(cdata)

        enriched.append(ea)

    return enriched


def build_enriched_feature_dict(gs: CabtGameState) -> dict:
    """Build feature dict with improved game phase using prize state."""
    features = build_feature_dict(gs)

    # Override game_phase with prize-aware logic
    own = gs.own_player
    opp = gs.opp_player
    own_prizes = own.prize_count if own else 6
    opp_prizes = opp.prize_count if opp else 6
    turn = gs.turn

    if turn <= 2:
        phase = "opening"
    elif turn <= 5:
        phase = "early"
    elif min(own_prizes, opp_prizes) <= 1:
        phase = "endgame"
    elif turn <= 10:
        phase = "midgame"
    else:
        phase = "late"

    features["game_phase"] = phase

    # Select context (for context router)
    if gs.select:
        features["select_context"] = gs.select.context
        features["select_type"] = gs.select.select_type
    else:
        features["select_context"] = -1
        features["select_type"] = -1

    # Additional features for scoring
    features["our_prizes"] = own_prizes
    features["opp_prizes"] = opp_prizes
    features["our_active_max_hp"] = (own.active[0].max_hp if own and own.active else 0)
    features["opp_active_max_hp"] = (opp.active[0].max_hp if opp and opp.active else 0)
    features["our_active_damage"] = (
        (own.active[0].max_hp - own.active[0].hp) if own and own.active else 0
    )
    features["opp_active_damage"] = (
        (opp.active[0].max_hp - opp.active[0].hp) if opp and opp.active else 0
    )
    features["our_bench_count"] = len(own.bench) if own else 0
    features["opp_bench_count"] = len(opp.bench) if opp else 0
    # opp_is_ex: check if opponent active's card name contains "ex"
    if opp and opp.active:
        cdb = _load_card_db()
        opp_card = cdb.get(opp.active[0].card_id, {})
        features["opp_is_ex"] = int("ex" in opp_card.get("card_name", "").lower())
    else:
        features["opp_is_ex"] = 0

    return features


# ---------------------------------------------------------------------------
# Decision telemetry
# ---------------------------------------------------------------------------

@dataclass
class DecisionRecord:
    """Per-decision telemetry for failure analysis."""
    game_id: str
    step: int
    turn: int
    select_type: int
    select_context: int
    option_count: int
    option_types: list[int]
    chosen_index: int
    chosen_type: int
    chosen_action_type: str
    reason: str
    scores: list[float]          # score for each option
    is_fallback: bool = False
    enriched_actions: list[dict] = field(default_factory=list)
    board_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "step": self.step,
            "turn": self.turn,
            "select_type": self.select_type,
            "select_context": self.select_context,
            "option_count": self.option_count,
            "option_types": self.option_types,
            "chosen_index": self.chosen_index,
            "chosen_type": self.chosen_type,
            "chosen_action_type": self.chosen_action_type,
            "reason": self.reason,
            "scores": [round(s, 4) for s in self.scores],
            "is_fallback": self.is_fallback,
            "board_summary": self.board_summary,
        }


@dataclass
class EpisodeRecord:
    """Complete telemetry for one game."""
    game_id: str
    source: str = "REAL_CABT_LOCAL"
    agent_name: str = ""
    opponent: str = ""
    winner: int = -1
    total_steps: int = 0
    total_turns: int = 0
    legal_errors: int = 0
    fallback_count: int = 0
    decisions: list[DecisionRecord] = field(default_factory=list)
    reward_p0: float = 0.0
    reward_p1: float = 0.0
    end_reason: str = ""
    deck_name: str = ""
    elapsed_s: float = 0.0
    decision_times_ms: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "source": self.source,
            "agent_name": self.agent_name,
            "opponent": self.opponent,
            "winner": self.winner,
            "total_steps": self.total_steps,
            "total_turns": self.total_turns,
            "legal_errors": self.legal_errors,
            "fallback_count": self.fallback_count,
            "reward_p0": self.reward_p0,
            "reward_p1": self.reward_p1,
            "end_reason": self.end_reason,
            "deck_name": self.deck_name,
            "elapsed_s": round(self.elapsed_s, 3),
            "mean_decision_ms": (
                round(sum(self.decision_times_ms) / len(self.decision_times_ms), 2)
                if self.decision_times_ms else 0.0
            ),
            "p95_decision_ms": (
                round(sorted(self.decision_times_ms)[int(len(self.decision_times_ms) * 0.95)], 2)
                if self.decision_times_ms else 0.0
            ),
            "n_decisions": len(self.decisions),
            "decisions": [d.to_dict() for d in self.decisions],
        }


# ---------------------------------------------------------------------------
# Enriched CABT game runner with telemetry
# ---------------------------------------------------------------------------

def _board_summary(gs: CabtGameState) -> dict:
    """Compact board summary for telemetry (visible info only)."""
    own = gs.own_player
    opp = gs.opp_player
    return {
        "turn": gs.turn,
        "own_active_hp": own.active[0].hp if own and own.active else None,
        "own_active_maxhp": own.active[0].max_hp if own and own.active else None,
        "own_active_id": own.active[0].card_id if own and own.active else None,
        "own_bench": len(own.bench) if own else 0,
        "own_hand": own.hand_count if own else 0,
        "own_prizes": own.prize_count if own else 6,
        "own_energy": own.total_energy_in_play if own else 0,
        "opp_active_hp": opp.active[0].hp if opp and opp.active else None,
        "opp_active_maxhp": opp.active[0].max_hp if opp and opp.active else None,
        "opp_active_id": opp.active[0].card_id if opp and opp.active else None,
        "opp_bench": len(opp.bench) if opp else 0,
        "opp_hand": opp.hand_count if opp else 0,
        "opp_prizes": opp.prize_count if opp else 6,
    }


def run_instrumented_game(
    agent,
    opponent: str = "random",
    deck: list[int] | None = None,
    game_id: str = "CABT-INST-001",
    max_steps: int = 500,
    card_db: dict[int, dict] | None = None,
) -> EpisodeRecord:
    """Run one instrumented CABT game with full decision telemetry.

    Unlike CabtGame, this uses enriched actions and records per-decision scores.
    """
    from .cabt_adapter import require_cabt, CabtGame

    ke = require_cabt()
    if deck is None:
        deck = CabtGame.DRAGAPULT_DECK
    if card_db is None:
        card_db = _load_card_db()

    env = ke.make("cabt", debug=False)
    trainer = env.train([None, opponent])

    agent_name = getattr(agent, "name", type(agent).__name__)
    episode = EpisodeRecord(
        game_id=game_id,
        agent_name=agent_name,
        opponent=opponent,
        deck_name="dragapult_ex_reference",
    )

    if hasattr(agent, "reset"):
        agent.reset()

    obs = trainer.reset()
    step_num = 0
    done = False
    t_start = time.time()

    while not done and step_num < max_steps:
        gs = parse_observation(obs, player_index=0)

        try:
            obs_d = dict(obs) if hasattr(obs, "keys") else {}
            sel_raw = obs_d.get("select")

            if sel_raw is None:
                # Step 0: submit deck
                action = list(deck)
            elif gs.select and gs.select.is_deck_selection:
                # Context 41: confirm deck
                action = [0]
            elif gs.select and gs.select.options:
                # Normal game step — use enriched actions
                enriched = enrich_options(gs, card_db)
                legal_actions = [ea.to_agent_dict() for ea in enriched]
                game_state_dict = build_enriched_feature_dict(gs)

                # Time the decision
                t_dec = time.time()
                is_fallback = False
                try:
                    idx, reason = agent.select_action(legal_actions, game_state_dict, gs.turn)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    idx = 0
                    reason = "fallback_exception"
                    is_fallback = True
                    episode.fallback_count += 1
                dec_ms = (time.time() - t_dec) * 1000
                episode.decision_times_ms.append(dec_ms)

                if idx < 0 or idx >= len(enriched):
                    idx = 0
                    is_fallback = True
                    episode.fallback_count += 1

                # Compute scores for all options (for telemetry)
                scores = []
                if hasattr(agent, "score_features"):
                    # B6 LegalActionScorer
                    from ..agents.baselines.legal_action_scorer import extract_action_features
                    for i, la in enumerate(legal_actions):
                        feats = extract_action_features(la, i, game_state_dict)
                        scores.append(agent.score_features(feats))
                elif hasattr(agent, "_score"):
                    # B3/B4
                    for la in legal_actions:
                        scores.append(agent._score(la, game_state_dict))
                else:
                    scores = [0.0] * len(legal_actions)

                # Record decision
                dr = DecisionRecord(
                    game_id=game_id,
                    step=step_num,
                    turn=gs.turn,
                    select_type=gs.select.select_type,
                    select_context=gs.select.context,
                    option_count=len(enriched),
                    option_types=[e.option_type for e in enriched],
                    chosen_index=idx,
                    chosen_type=enriched[idx].option_type,
                    chosen_action_type=enriched[idx].action_type,
                    reason=reason,
                    scores=scores,
                    is_fallback=is_fallback,
                    enriched_actions=[e.to_agent_dict() for e in enriched],
                    board_summary=_board_summary(gs),
                )
                episode.decisions.append(dr)

                action = build_action_from_option_index(idx, gs)
            else:
                action = []
        except Exception:
            action = []
            episode.legal_errors += 1

        obs, reward, done, info = trainer.step(action)
        step_num += 1
        episode.total_turns = gs.turn

    # Terminal
    episode.total_steps = step_num
    episode.elapsed_s = time.time() - t_start
    final = env.state
    if len(final) >= 2:
        episode.reward_p0 = float(final[0].get("reward", 0) or 0)
        episode.reward_p1 = float(final[1].get("reward", 0) or 0)
        if episode.reward_p0 > episode.reward_p1:
            episode.winner = 0
        elif episode.reward_p1 > episode.reward_p0:
            episode.winner = 1
        else:
            episode.winner = -1
    episode.end_reason = "terminal" if done else "max_steps"

    return episode


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def wilson_ci(wins: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 1.0
    z = 1.96
    p = wins / total
    n = total
    center = (p + z**2 / (2*n)) / (1 + z**2/n)
    margin = (z * math.sqrt(p*(1-p)/n + z**2/(4*n**2))) / (1 + z**2/n)
    return max(0.0, center - margin), min(1.0, center + margin)


@dataclass
class BenchmarkCondition:
    """One benchmark condition (agent x opponent x deck)."""
    agent_factory: Any       # callable() -> agent
    agent_name: str
    opponent: str
    deck: list[int]
    deck_name: str
    n_games: int
    label: str = ""


@dataclass
class BenchmarkResult:
    """Result of one benchmark condition."""
    label: str
    agent_name: str
    opponent: str
    deck_name: str
    n_games: int
    wins: int = 0
    losses: int = 0
    draws: int = 0
    win_rate: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    mean_steps: float = 0.0
    total_legal_errors: int = 0
    total_fallbacks: int = 0
    mean_decision_ms: float = 0.0
    episodes: list[EpisodeRecord] = field(default_factory=list)

    def compute(self):
        if not self.episodes:
            return
        self.n_games = len(self.episodes)
        self.wins = sum(1 for e in self.episodes if e.winner == 0)
        self.losses = sum(1 for e in self.episodes if e.winner == 1)
        self.draws = sum(1 for e in self.episodes if e.winner == -1)
        self.win_rate = self.wins / self.n_games
        self.ci_lower, self.ci_upper = wilson_ci(self.wins, self.n_games)
        self.mean_steps = sum(e.total_steps for e in self.episodes) / self.n_games
        self.total_legal_errors = sum(e.legal_errors for e in self.episodes)
        self.total_fallbacks = sum(e.fallback_count for e in self.episodes)
        all_dec_times = [t for e in self.episodes for t in e.decision_times_ms]
        self.mean_decision_ms = sum(all_dec_times) / len(all_dec_times) if all_dec_times else 0.0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "agent_name": self.agent_name,
            "opponent": self.opponent,
            "deck_name": self.deck_name,
            "source": "REAL_CABT_LOCAL",
            "n_games": self.n_games,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "win_rate": round(self.win_rate, 4),
            "ci_lower": round(self.ci_lower, 4),
            "ci_upper": round(self.ci_upper, 4),
            "mean_steps": round(self.mean_steps, 1),
            "total_legal_errors": self.total_legal_errors,
            "total_fallbacks": self.total_fallbacks,
            "mean_decision_ms": round(self.mean_decision_ms, 2),
        }


def run_benchmark(
    conditions: list[BenchmarkCondition],
    output_dir: Path,
    seed: int = 42,
) -> list[BenchmarkResult]:
    """Run full benchmark across all conditions with telemetry.

    All results labeled REAL_CABT_LOCAL.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    card_db = _load_card_db()
    results: list[BenchmarkResult] = []
    t0 = time.time()

    print(f"\n[BENCHMARK] {len(conditions)} conditions")
    print(f"[BENCHMARK] Source: REAL_CABT_LOCAL — NOT official Kaggle result")

    for cond in conditions:
        br = BenchmarkResult(
            label=cond.label or f"{cond.agent_name}_vs_{cond.opponent}",
            agent_name=cond.agent_name,
            opponent=cond.opponent,
            deck_name=cond.deck_name,
            n_games=cond.n_games,
        )
        print(f"\n  Condition: {br.label} ({cond.n_games} games)")

        rng = random.Random(seed + hash(br.label) % 10000)

        for i in range(cond.n_games):
            agent = cond.agent_factory()
            gid = f"BM-{br.label}-G{i:04d}"
            ep = run_instrumented_game(
                agent=agent,
                opponent=cond.opponent,
                deck=cond.deck,
                game_id=gid,
                card_db=card_db,
            )
            br.episodes.append(ep)
            w = "W" if ep.winner == 0 else ("L" if ep.winner == 1 else "D")
            if (i + 1) % max(1, cond.n_games // 5) == 0:
                cur_wr = sum(1 for e in br.episodes if e.winner == 0) / len(br.episodes)
                print(f"    [{i+1}/{cond.n_games}] {w} steps={ep.total_steps} wr={cur_wr:.1%}")

        br.compute()
        results.append(br)
        print(f"  Result: WR={br.win_rate:.1%} CI=[{br.ci_lower:.3f}, {br.ci_upper:.3f}] "
              f"errors={br.total_legal_errors} fallbacks={br.total_fallbacks}")

    elapsed = time.time() - t0

    # Save summary
    summary = {
        "source": "REAL_CABT_LOCAL",
        "note": "NOT official Kaggle result",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(elapsed, 1),
        "seed": seed,
        "conditions": [r.to_dict() for r in results],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    # Save raw episodes (trajectories)
    traj_dir = output_dir.parent / "trajectories"
    traj_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        for ep in r.episodes:
            ep_path = traj_dir / f"{ep.game_id}.json"
            ep_path.write_text(json.dumps(ep.to_dict(), indent=2), encoding="utf-8")

    # Print leaderboard
    print(f"\n[BENCHMARK] Complete in {elapsed:.1f}s")
    print(f"{'Condition':<35} {'WR':>8} {'CI':>22} {'Err':>5} {'FB':>5}")
    print("-" * 80)
    for r in sorted(results, key=lambda x: -x.win_rate):
        ci = f"[{r.ci_lower:.3f}, {r.ci_upper:.3f}]"
        print(f"{r.label:<35} {r.win_rate:>8.1%} {ci:>22} {r.total_legal_errors:>5} {r.total_fallbacks:>5}")

    return results
