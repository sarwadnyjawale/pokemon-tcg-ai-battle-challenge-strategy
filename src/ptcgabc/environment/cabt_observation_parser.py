"""CABT Observation Parser.

Converts raw CABT observations (Struct/dict from kaggle-environments) into the
project's canonical GameState representation.

SCHEMA SOURCE: empirical probing of the real cabt engine, 2026-09-13.
All field names and types are derived from actual observations — nothing invented.

Information-visibility contract (engine-verified):
  own hand     -> current.players[yourIndex].hand       (list of card dicts)
  opp hand     -> current.players[1-yourIndex].hand     (null — HIDDEN)
  opp handCount-> current.players[1-yourIndex].handCount (visible count only)
  prizes       -> current.players[*].prize              (6 nulls — count visible, cards hidden)
  board        -> current.players[*].active + bench     (both visible)
  deck count   -> current.players[*].deckCount          (visible)
  discard      -> current.players[*].discard            (visible)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Canonical internal game-state representation
# (derived only from fields that CABT actually exposes)
# ---------------------------------------------------------------------------

@dataclass
class CabtCardRef:
    """A card reference visible on the board."""
    card_id:      int
    serial:       int             # unique instance id within this game
    player_index: int


@dataclass
class CabtInPlayCard:
    """A Pokemon in the active or bench position."""
    card_id:          int
    serial:           int
    player_index:     int
    hp:               int
    max_hp:           int
    appear_this_turn: bool
    energies:         list[int]      # energy type ids attached
    energy_cards:     list[CabtCardRef]
    tools:            list[Any]
    pre_evolution:    list[Any]

    @property
    def hp_fraction(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0

    @property
    def is_ko(self) -> bool:
        return self.hp <= 0


@dataclass
class CabtPlayerState:
    """Visible state for one player.

    own_player=True  => hand is visible
    own_player=False => hand is None (hidden); only hand_count visible
    """
    player_index: int
    own_player:   bool

    active:     list[CabtInPlayCard] = field(default_factory=list)
    bench:      list[CabtInPlayCard] = field(default_factory=list)
    bench_max:  int = 5
    deck_count: int = 0
    discard:    list[Any] = field(default_factory=list)
    prize_count: int = 6       # number of prize slots (cards hidden)
    hand_count:  int = 0
    hand:        Optional[list[CabtCardRef]] = None   # None if opponent

    poisoned:   bool = False
    burned:     bool = False
    asleep:     bool = False
    paralyzed:  bool = False
    confused:   bool = False

    @property
    def total_energy_in_play(self) -> int:
        total = sum(len(c.energies) for c in self.active)
        total += sum(len(c.energies) for c in self.bench)
        return total

    @property
    def board_presence(self) -> int:
        return (1 if self.active and not self.active[0].is_ko else 0) + len(self.bench)


@dataclass
class CabtOption:
    """One legal option from select.option."""
    index:        int              # 0-based position in option list
    option_type:  int              # raw type integer from CABT
    raw:          dict = field(default_factory=dict)   # full raw option dict


@dataclass
class CabtSelect:
    """The select object — decision request from the engine."""
    select_type:         int
    context:             int
    min_count:           int
    max_count:           int
    remain_damage_counter: int
    remain_energy_cost:  int
    options:             list[CabtOption]
    is_deck_selection:   bool = False    # True when context=41 (submit deck)

    @property
    def option_count(self) -> int:
        return len(self.options)

    @property
    def has_pass(self) -> bool:
        return any(o.option_type == 14 for o in self.options)

    def pass_index(self) -> Optional[int]:
        for o in self.options:
            if o.option_type == 14:
                return o.index
        return None


@dataclass
class CabtGameState:
    """Canonical game state derived from one real CABT observation.

    Only fields actually provided by the CABT engine are populated here.
    No inference, no invention.
    """
    # Episode metadata
    step:                   int
    remaining_overage_time: float
    is_active:              bool    # True if this player must make a decision now

    # Turn state (None at step 0 before game starts)
    turn:                   int = 0
    turn_action_count:      int = 0
    your_index:             int = 0
    first_player:           int = -1     # -1 before determined
    supporter_played:       bool = False
    stadium_played:         bool = False
    energy_attached:        bool = False
    retreated:              bool = False
    result:                 int = -1     # -1=ongoing, 0/1 = winning player

    # Players (index 0 = player 0, index 1 = player 1)
    players:                list[CabtPlayerState] = field(default_factory=list)

    # Decision to make
    select:                 Optional[CabtSelect] = None

    # Raw logs since last step
    logs:                   list[dict] = field(default_factory=list)

    # Opaque engine state (pass through for deck search)
    search_begin_input:     Optional[str] = None

    @property
    def own_player(self) -> Optional[CabtPlayerState]:
        if not self.players or self.your_index >= len(self.players):
            return None
        return self.players[self.your_index]

    @property
    def opp_player(self) -> Optional[CabtPlayerState]:
        opp_idx = 1 - self.your_index
        if not self.players or opp_idx >= len(self.players):
            return None
        return self.players[opp_idx]

    @property
    def is_terminal(self) -> bool:
        return self.result >= 0

    @property
    def legal_option_count(self) -> int:
        return self.select.option_count if self.select else 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _to_dict(v: Any) -> Any:
    """Recursively convert kaggle-environments Struct to plain dict."""
    if hasattr(v, "items"):
        return {k: _to_dict(vv) for k, vv in v.items()}
    if isinstance(v, list):
        return [_to_dict(x) for x in v]
    return v


def _parse_card_ref(raw: dict) -> CabtCardRef:
    return CabtCardRef(
        card_id      = int(raw.get("id", 0)),
        serial       = int(raw.get("serial", 0)),
        player_index = int(raw.get("playerIndex", 0)),
    )


def _parse_in_play(raw: dict) -> CabtInPlayCard:
    energy_cards_raw = raw.get("energyCards") or []
    return CabtInPlayCard(
        card_id          = int(raw.get("id", 0)),
        serial           = int(raw.get("serial", 0)),
        player_index     = int(raw.get("playerIndex", 0)),
        hp               = int(raw.get("hp", 0)),
        max_hp           = int(raw.get("maxHp", 0)),
        appear_this_turn = bool(raw.get("appearThisTurn", False)),
        energies         = list(raw.get("energies") or []),
        energy_cards     = [_parse_card_ref(c) for c in energy_cards_raw],
        tools            = list(raw.get("tools") or []),
        pre_evolution    = list(raw.get("preEvolution") or []),
    )


def _parse_player(raw: dict, own: bool) -> CabtPlayerState:
    active_raw = [c for c in (raw.get("active") or []) if c is not None]
    bench_raw  = [c for c in (raw.get("bench")  or []) if c is not None]
    hand_raw   = raw.get("hand")            # None for opponent
    prize_raw  = raw.get("prize") or []

    ps = CabtPlayerState(
        player_index = int(raw.get("playerIndex", 0)) if "playerIndex" in raw else -1,
        own_player   = own,
        bench_max    = int(raw.get("benchMax", 5)),
        deck_count   = int(raw.get("deckCount", 0)),
        discard      = list(raw.get("discard") or []),
        prize_count  = len(prize_raw),
        hand_count   = int(raw.get("handCount", 0)),
        poisoned     = bool(raw.get("poisoned", False)),
        burned       = bool(raw.get("burned", False)),
        asleep       = bool(raw.get("asleep", False)),
        paralyzed    = bool(raw.get("paralyzed", False)),
        confused     = bool(raw.get("confused", False)),
    )
    ps.active = [_parse_in_play(c) for c in active_raw]
    ps.bench  = [_parse_in_play(c) for c in bench_raw]

    if hand_raw is not None:
        ps.hand = [_parse_card_ref(c) for c in hand_raw]
    else:
        ps.hand = None  # hidden (opponent)

    return ps


def _parse_select(raw: dict) -> CabtSelect:
    options_raw = raw.get("option") or []
    options = [
        CabtOption(
            index       = i,
            option_type = int(opt.get("type", -1)),
            raw         = opt,
        )
        for i, opt in enumerate(options_raw)
    ]
    context = int(raw.get("context", 0))
    return CabtSelect(
        select_type           = int(raw.get("type", 0)),
        context               = context,
        min_count             = int(raw.get("minCount", 1)),
        max_count             = int(raw.get("maxCount", 1)),
        remain_damage_counter = int(raw.get("remainDamageCounter", 0)),
        remain_energy_cost    = int(raw.get("remainEnergyCost", 0)),
        options               = options,
        is_deck_selection     = (context == 41),
    )


def parse_observation(raw_obs: Any, player_index: int = 0) -> CabtGameState:
    """Convert a raw CABT observation (Struct or dict) into CabtGameState.

    raw_obs: the observation object returned by kaggle-environments
    player_index: which player this observation belongs to (0 or 1)

    RULE: Only fields actually provided by CABT are used.
          No inference, no invention, no fallback to MockSimulator.
    """
    obs = _to_dict(raw_obs)

    step  = int(obs.get("step", 0))
    ovt   = float(obs.get("remainingOverageTime", 600.0))
    logs  = list(obs.get("logs") or [])
    sbi   = obs.get("search_begin_input")
    sel_raw = obs.get("select")
    cur     = obs.get("current")

    # Determine if this player is active (has a select to respond to)
    is_active = sel_raw is not None

    gs = CabtGameState(
        step                   = step,
        remaining_overage_time = ovt,
        is_active              = is_active,
        logs                   = [_to_dict(l) for l in logs],
        search_begin_input     = sbi,
    )

    if sel_raw:
        gs.select = _parse_select(sel_raw)

    if cur:
        gs.turn             = int(cur.get("turn", 0))
        gs.turn_action_count = int(cur.get("turnActionCount", 0))
        gs.your_index       = int(cur.get("yourIndex", player_index))
        gs.first_player     = int(cur.get("firstPlayer", -1))
        gs.supporter_played = bool(cur.get("supporterPlayed", False))
        gs.stadium_played   = bool(cur.get("stadiumPlayed", False))
        gs.energy_attached  = bool(cur.get("energyAttached", False))
        gs.retreated        = bool(cur.get("retreated", False))
        gs.result           = int(cur.get("result", -1))

        players_raw = cur.get("players") or []
        your_idx = gs.your_index
        gs.players = []
        for i, p_raw in enumerate(players_raw):
            own = (i == your_idx)
            ps  = _parse_player(p_raw, own=own)
            ps.player_index = i
            gs.players.append(ps)

    return gs


def extract_legal_options(gs: CabtGameState) -> list[CabtOption]:
    """Return the list of legal options from the current game state.

    Returns [] if not active or no select present.
    """
    if not gs.is_active or gs.select is None:
        return []
    return list(gs.select.options)


def build_feature_dict(gs: CabtGameState) -> dict:
    """Build a feature dict for policy consumption.

    RULE: Only fields actually visible per the CABT information-visibility contract.
          Opponent hand contents are NEVER included (they are null in obs).
    """
    own = gs.own_player
    opp = gs.opp_player

    features: dict = {
        "step":           gs.step,
        "turn":           gs.turn,
        "your_index":     gs.your_index,
        "first_player":   gs.first_player,
        "is_active":      int(gs.is_active),
        "result":         gs.result,
        # Own visible state
        "own_deck_count":   own.deck_count        if own else 0,
        "own_hand_count":   own.hand_count         if own else 0,
        "own_prize_count":  own.prize_count        if own else 6,
        "own_bench_count":  len(own.bench)         if own else 0,
        "own_has_active":   int(bool(own and own.active)),
        "own_active_hp":    own.active[0].hp       if own and own.active else 0,
        "own_active_maxhp": own.active[0].max_hp   if own and own.active else 0,
        "own_active_hp_fraction": own.active[0].hp_fraction if own and own.active else 0.0,
        "own_energy_in_play": own.total_energy_in_play if own else 0,
        "own_board_presence": own.board_presence   if own else 0,
        # Turn modifiers (visible)
        "supporter_played": int(gs.supporter_played),
        "energy_attached":  int(gs.energy_attached),
        "retreated":        int(gs.retreated),
        # Opponent VISIBLE state only
        "opp_deck_count":   opp.deck_count          if opp else 0,
        "opp_hand_count":   opp.hand_count           if opp else 0,   # count only!
        "opp_prize_count":  opp.prize_count          if opp else 6,
        "opp_bench_count":  len(opp.bench)           if opp else 0,
        "opp_has_active":   int(bool(opp and opp.active)),
        "opp_active_hp":    opp.active[0].hp         if opp and opp.active else 0,
        "opp_active_maxhp": opp.active[0].max_hp     if opp and opp.active else 0,
        "opp_active_hp_fraction": opp.active[0].hp_fraction if opp and opp.active else 0.0,
        "opp_energy_in_play": opp.total_energy_in_play if opp else 0,
        "opp_board_presence": opp.board_presence     if opp else 0,
        # Legal actions
        "legal_option_count": gs.legal_option_count,
        "is_deck_selection":  int(gs.select.is_deck_selection if gs.select else False),
        # Derived strategic features
        "prize_delta":    ((own.prize_count if own else 6) - (opp.prize_count if opp else 6)),
        "game_phase":     _game_phase(gs.turn),
    }
    return features


def _game_phase(turn: int) -> str:
    if turn <= 2:   return "opening"
    if turn <= 5:   return "early"
    if turn <= 10:  return "midgame"
    return "late"
