"""Phase 3 — Structured game state representation.

RULE: Only VISIBLE_NOW or INFERRED features. Never store hidden information
(opponent hand cards, prize cards, deck order, RNG seed).

Engine-verified prize count = 6 (Phase 1 probes). Blueprint's Pocket value
of 3 is REJECTED — updated below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GamePhase(Enum):
    OPENING = "opening"      # turns 1-2
    EARLY   = "early"        # turns 3-5
    MIDGAME = "midgame"      # turns 6-10
    LATE    = "late"         # turns 11+
    ENDGAME = "endgame"      # last 1-2 prizes each


class ResourcePressure(Enum):
    RICH        = "rich"         # ≥4 cards in hand
    ADEQUATE    = "adequate"     # 2-3
    CONSTRAINED = "constrained"  # 1
    CRITICAL    = "critical"     # 0


class BoardPosition(Enum):
    AHEAD           = "ahead"
    EVEN            = "even"
    BEHIND          = "behind"
    CRITICAL_BEHIND = "critical_behind"


# ---------------------------------------------------------------------------
# Board pieces
# ---------------------------------------------------------------------------

@dataclass
class PokemonInPlay:
    """A Pokémon on the board. Only VISIBLE_NOW information is stored."""

    card_id:           str
    card_name:         str
    max_hp:            int
    current_hp:        int
    damage_counters:   int
    attached_energy:   dict[str, int]   # energy_type -> count
    status_conditions: list[str]        # poison / sleep / paralyzed …
    is_ex:             bool
    stage:             str              # Basic / Stage 1 / Stage 2
    pokemon_type:      str
    retreat_cost:      int
    tools_attached:    list[str]
    attacks_available: list[dict]       # name, cost, damage
    can_attack:        bool = True
    can_retreat:       bool = True

    @property
    def hp_fraction(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return self.current_hp / self.max_hp

    @property
    def is_ko(self) -> bool:
        return self.current_hp <= 0

    @property
    def total_energy(self) -> int:
        return sum(self.attached_energy.values())


@dataclass
class PlayerState:
    """Complete visible state for one player."""

    player_id: int   # 0 = us, 1 = opponent

    # Board — all VISIBLE_NOW
    active: Optional[PokemonInPlay] = None
    bench:  list[PokemonInPlay]     = field(default_factory=list)

    # Resources
    hand_count:   int       = 0    # opponent: count only
    hand_cards:   list[str] = field(default_factory=list)  # own only
    discard_pile: list[str] = field(default_factory=list)
    # Engine-verified: 6 prizes (Phase 1 probes). Blueprint's 3 was Pocket assumption.
    prizes_remaining: int = 6
    deck_count:       int = 0

    # Derived
    board_presence: int = 0

    def compute_board_presence(self) -> int:
        count = 0
        if self.active and not self.active.is_ko:
            count += 1
        count += sum(1 for p in self.bench if not p.is_ko)
        self.board_presence = count
        return count

    @property
    def total_energy_in_play(self) -> int:
        total = self.active.total_energy if self.active else 0
        return total + sum(p.total_energy for p in self.bench)


# ---------------------------------------------------------------------------
# Top-level state
# ---------------------------------------------------------------------------

@dataclass
class StructuredGameState:
    """Complete structured game state.

    RULE: Only VISIBLE_NOW or INFERRED features.
    RULE: Never store HIDDEN information.
    """

    # Turn — VISIBLE_NOW
    turn_number:    int  = 0
    is_our_turn:    bool = True
    is_first_player: bool = True

    # Players
    us:       PlayerState = field(default_factory=lambda: PlayerState(player_id=0))
    opponent: PlayerState = field(default_factory=lambda: PlayerState(player_id=1))

    # Shared board
    stadium: Optional[str] = None
    weather: Optional[str] = None

    # Legal actions — VISIBLE_NOW
    legal_actions: list[dict] = field(default_factory=list)
    action_count:  int = 0

    # Derived strategic — INFERRED
    game_phase:        GamePhase        = GamePhase.OPENING
    resource_pressure: ResourcePressure = ResourcePressure.ADEQUATE
    board_position:    BoardPosition    = BoardPosition.EVEN
    prize_delta:       int = 0          # us.prizes_remaining - opp.prizes_remaining

    # History
    recent_actions:  list[dict] = field(default_factory=list)
    turns_since_ko:  int = 0

    def compute_derived_features(self) -> None:
        """Compute all derived strategic features from visible state."""

        # Game phase
        if self.turn_number <= 2:
            self.game_phase = GamePhase.OPENING
        elif self.turn_number <= 5:
            self.game_phase = GamePhase.EARLY
        elif self.turn_number <= 10:
            self.game_phase = GamePhase.MIDGAME
        else:
            max_prizes = 6  # engine-verified
            if min(self.us.prizes_remaining, self.opponent.prizes_remaining) <= 1:
                self.game_phase = GamePhase.ENDGAME
            else:
                self.game_phase = GamePhase.LATE

        # Prize delta (negative = we need fewer prizes = ahead)
        self.prize_delta = self.us.prizes_remaining - self.opponent.prizes_remaining

        # Board position
        if self.prize_delta <= -2:
            self.board_position = BoardPosition.AHEAD
        elif self.prize_delta <= 0:
            self.board_position = BoardPosition.EVEN
        elif self.prize_delta <= 1:
            self.board_position = BoardPosition.BEHIND
        else:
            self.board_position = BoardPosition.CRITICAL_BEHIND

        # Resource pressure
        hand = self.us.hand_count
        if hand >= 4:
            self.resource_pressure = ResourcePressure.RICH
        elif hand >= 2:
            self.resource_pressure = ResourcePressure.ADEQUATE
        elif hand >= 1:
            self.resource_pressure = ResourcePressure.CONSTRAINED
        else:
            self.resource_pressure = ResourcePressure.CRITICAL

        self.action_count = len(self.legal_actions)
        self.us.compute_board_presence()
        self.opponent.compute_board_presence()

    def to_feature_vector(self) -> dict:
        """Flat feature dict for model input.

        RULE: Only VISIBLE_NOW and INFERRED features.
        NEVER include: opponent_hand_cards, opponent_prize_cards,
                       deck_order, rng_seed.
        """
        return {
            # Turn
            "turn_number":      self.turn_number,
            "is_first_player":  int(self.is_first_player),
            # Our state
            "our_prizes":          self.us.prizes_remaining,
            "our_hand_count":      self.us.hand_count,
            "our_board_presence":  self.us.board_presence,
            "our_energy_in_play":  self.us.total_energy_in_play,
            "our_active_hp_fraction": (
                self.us.active.hp_fraction if self.us.active else 0.0),
            "our_active_damage": (
                self.us.active.damage_counters if self.us.active else 0),
            "our_bench_count": len(self.us.bench),
            # Opponent visible
            "opp_prizes":          self.opponent.prizes_remaining,
            "opp_hand_count":      self.opponent.hand_count,
            "opp_board_presence":  self.opponent.board_presence,
            "opp_energy_in_play":  self.opponent.total_energy_in_play,
            "opp_active_hp_fraction": (
                self.opponent.active.hp_fraction if self.opponent.active else 0.0),
            "opp_active_damage": (
                self.opponent.active.damage_counters if self.opponent.active else 0),
            "opp_is_ex": int(self.opponent.active.is_ex) if self.opponent.active else 0,
            # Derived strategic
            "game_phase":       self.game_phase.value,
            "prize_delta":      self.prize_delta,
            "board_position":   self.board_position.value,
            "resource_pressure": self.resource_pressure.value,
            "legal_action_count": self.action_count,
        }
