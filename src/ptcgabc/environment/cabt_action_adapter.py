"""CABT Action Adapter.

Converts our policy's decision (option index) into the exact action format
that kaggle-environments / cabt expects.

SCHEMA SOURCE: empirical probing of the real cabt engine, 2026-09-13.

Action format (empirically verified):
  - Step 0: []  (both players submit empty or await)
  - Step 1, context=41: list of 60 integer card ids (the deck)
  - Normal steps: [option_index] (single int in a list)
  - Some contexts allow [] (optional action — pass/skip)
"""

from __future__ import annotations

from typing import Optional
from .cabt_observation_parser import CabtGameState, CabtSelect, CabtOption


# ---------------------------------------------------------------------------
# Deck submission
# ---------------------------------------------------------------------------

def build_deck_action(deck: list[int]) -> list[int]:
    """Build the deck-submission action for step 1 / context 41.

    CABT expects a list of exactly 60 integer card ids.
    Raises ValueError if deck is not exactly 60 cards.
    """
    if len(deck) != 60:
        raise ValueError(f"Deck must be exactly 60 cards; got {len(deck)}")
    return list(deck)


# ---------------------------------------------------------------------------
# Normal action translation
# ---------------------------------------------------------------------------

def build_action_from_option_index(
    option_index: int,
    gs:           CabtGameState,
) -> list[int]:
    """Build CABT action from a 0-based option index.

    Returns [option_index] for a normal decision.
    Returns [] for optional/pass contexts when option_index == -1.

    Validates that option_index is within the legal range.
    """
    if not gs.is_active:
        return []

    sel = gs.select
    if sel is None:
        return []

    if sel.is_deck_selection:
        raise ValueError(
            "Use build_deck_action() for deck-selection steps (context=41)"
        )

    n_options = len(sel.options)
    if n_options == 0:
        return []

    if option_index < 0:
        # -1 == pass/skip (empty action for optional contexts)
        return []

    if option_index >= n_options:
        raise ValueError(
            f"option_index {option_index} out of range [0, {n_options-1}]"
        )

    return [option_index]


def select_random_action(gs: CabtGameState, rng=None) -> list[int]:
    """Select a random legal option. Useful for baseline evaluation.

    Falls back to [] if no options available.
    """
    import random
    rng = rng or random
    sel = gs.select
    if sel is None or not sel.options:
        return []
    idx = rng.randrange(len(sel.options))
    return build_action_from_option_index(idx, gs)


def select_first_action(gs: CabtGameState) -> list[int]:
    """Select the first legal option (B0-SimulatorOrder equivalent)."""
    sel = gs.select
    if sel is None or not sel.options:
        return []
    return build_action_from_option_index(0, gs)


def select_pass_action(gs: CabtGameState) -> list[int]:
    """Select the pass/end-turn option if available, else first option."""
    sel = gs.select
    if sel is None:
        return []
    pass_idx = sel.pass_index()
    if pass_idx is not None:
        return build_action_from_option_index(pass_idx, gs)
    if sel.options:
        return build_action_from_option_index(0, gs)
    return []


# ---------------------------------------------------------------------------
# Policy bridge: convert existing Phase 3/4 agents to CABT actions
# ---------------------------------------------------------------------------

def agent_to_cabt_action(
    agent,
    gs:       CabtGameState,
    deck:     Optional[list[int]] = None,
) -> list[int]:
    """Bridge between existing Phase 3/4 agents and CABT action format.

    For deck-selection steps:   returns build_deck_action(deck)
    For normal steps:           converts agent.select_action() index -> CABT list

    agent must implement select_action(legal_actions, game_state, turn) -> (int, str)
    where legal_actions is a list of dicts with at least {"type": option_type}.
    """
    if not gs.is_active:
        return []

    sel = gs.select
    if sel is None:
        return []

    # Deck submission step
    if sel.is_deck_selection:
        if deck is None:
            raise ValueError("deck must be provided for deck-selection steps")
        return build_deck_action(deck)

    if not sel.options:
        return []

    # Convert CABT options to the agent's expected action dict format
    legal_actions = [
        {
            "type": _option_type_to_action_type(opt.option_type),
            "cabt_option_type": opt.option_type,
            "cabt_option_index": opt.index,
            "raw": opt.raw,
        }
        for opt in sel.options
    ]

    # Build game_state dict matching Phase 3/4 agent interface
    from .cabt_observation_parser import build_feature_dict
    game_state_dict = build_feature_dict(gs)

    try:
        idx, _reason = agent.select_action(legal_actions, game_state_dict, gs.turn)
    except Exception:
        idx = 0  # fallback: first option

    if idx < 0 or idx >= len(sel.options):
        idx = 0

    return build_action_from_option_index(idx, gs)


def _option_type_to_action_type(cabt_option_type: int) -> str:
    """Map CABT option type integers to string action-type labels.

    Based on empirically observed option types during real CABT probing.
    """
    _MAP = {
        0:  "numbered_choice",
        1:  "use_first",
        2:  "use_second",
        3:  "card_from_area",
        4:  "card_from_area",
        5:  "play_from_hand",
        6:  "attach_energy",
        7:  "attack",
        8:  "play_card_to_bench",
        9:  "play_card_to_active",
        10: "evolve",
        11: "retreat",
        12: "play_trainer",
        13: "use_ability",
        14: "pass",
    }
    return _MAP.get(cabt_option_type, f"unknown_{cabt_option_type}")
