"""Internal canonical data contracts (blueprint §7–§9).

The canonical layer is lossless: it preserves raw values and source lineage.
Model views may flatten/summarize the canonical layer later, never earlier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .provenance import ResultSource


class ContractValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractValidationError(message)


# ---------------------------------------------------------------------------
# Card / Attack layers
# ---------------------------------------------------------------------------


@dataclass
class Attack:
    """One move/attack row-group on a card (blueprint §3, §8)."""

    name: str
    cost: str = ""          # raw cost expression, preserved verbatim
    damage: str = ""        # raw damage expression (may contain '+', 'x', '?')
    effect: str = ""        # raw effect text, preserved verbatim
    move_row_index: int = -1  # source row within the card's rows
    source_rows: list[int] = field(default_factory=list)

    def validate(self) -> "Attack":
        _require(isinstance(self.name, str), "attack name must be str")
        return self

    def to_dict(self, full: bool = True) -> dict:
        d: dict[str, Any] = {
            "name": self.name,
            "cost": self.cost,
            "damage": self.damage,
            "effect": self.effect,
        }
        if full:
            d.update({"move_row_index": self.move_row_index, "source_rows": list(self.source_rows)})
        return d


@dataclass
class Card:
    """Canonical card. Lossless; preserves every raw value and its lineage."""

    card_id: str
    card_name: str
    category: str            # Pokémon / Trainer / Energy (raw, mapped via schema)
    source_file: str
    source_row_indices: list[int]
    raw_rows: list[dict[str, Any]]
    # card-level fields (raw strings until schema VERIFIED mapping)
    fields: dict[str, Any] = field(default_factory=dict)
    attacks: list[Attack] = field(default_factory=list)
    transformation_version: str = "1.0"

    def source_lineage(self) -> dict[str, Any]:
        return {
            "file": self.source_file,
            "row_indices": list(self.source_row_indices),
            "transformation_version": self.transformation_version,
        }

    def validate(self) -> "Card":
        _require(bool(self.card_id), "card_id must be non-empty")
        _require(bool(self.card_name), "card_name must be non-empty")
        _require(self.source_row_indices, "a canonical card must have ≥1 source row")
        _require(len(self.raw_rows) == len(self.source_row_indices), "raw_rows must align with source_row_indices")
        for a in self.attacks:
            a.validate()
        return self

    def to_dict(self, full: bool = True) -> dict:
        d: dict[str, Any] = {
            "card_id": self.card_id,
            "card_name": self.card_name,
            "category": self.category,
            "attacks": [a.to_dict(full=full) for a in self.attacks],
            "fields": dict(self.fields),
        }
        if full:
            d["source_lineage"] = self.source_lineage()
        return d


@dataclass
class Effect:
    """Structured interpretation of a move/trainer effect.

    Only filled when confident; otherwise UNKNOWN, never guessed (blueprint §6).
    raw_text is always preserved.
    """

    raw_text: str
    effect_type: str = "UNKNOWN"
    target: str = "UNKNOWN"
    source: str = "UNKNOWN"
    quantity: str = "UNKNOWN"
    condition: str = "UNKNOWN"
    timing: str = "UNKNOWN"
    restriction: str = "UNKNOWN"
    side_effect: str = "UNKNOWN"
    status: str = "UNKNOWN"  # VERIFIED / AMBIGUOUS / UNKNOWN / UNUSED

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "effect_type": self.effect_type,
            "target": self.target,
            "source": self.source,
            "quantity": self.quantity,
            "condition": self.condition,
            "timing": self.timing,
            "restriction": self.restriction,
            "side_effect": self.side_effect,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Game state layers
# ---------------------------------------------------------------------------


@dataclass
class PlayerState:
    player_index: int
    active: list[Any] = field(default_factory=list)      # Pokémon (0/1)
    bench: list[Any] = field(default_factory=list)
    hand: list[Any] | None = None                        # None => hidden (opponent)
    hand_count: int = 0
    prize: list[Any] = field(default_factory=list)       # None slots => facedown
    deck_count: int = 0
    discard: list[Any] = field(default_factory=list)
    bench_max: int = 5
    poisoned: bool = False
    burned: bool = False
    asleep: bool = False
    paralyzed: bool = False
    confused: bool = False

    def validate(self) -> "PlayerState":
        _require(-1 <= self.player_index <= 1, "player_index must be 0 or 1 (or -1)")
        _require(len(self.active) <= 1, "active must have 0 or 1 elements")
        _require(len(self.bench) <= self.bench_max, f"bench cannot exceed bench_max={self.bench_max}")
        return self


@dataclass
class GameState:
    turn: int = 0
    turn_action_count: int = 0
    your_index: int = 0
    first_player: int = -1
    supporter_played: bool = False
    stadium_played: bool = False
    energy_attached: bool = False
    retreated: bool = False
    result: int = -1               # -1 not finished; else winning player index
    stadium: list[Any] = field(default_factory=list)
    looking: list[Any] | None = None
    players: list[PlayerState] = field(default_factory=list)

    def validate(self) -> "GameState":
        _require(len(self.players) in (0, 2), "players must be 0 or 2 entries")
        for p in self.players:
            p.validate()
        _require(-1 <= self.result <= 2, "result must be -1 (running), 0, 1, or 2 (draw)")
        return self


@dataclass
class Action:
    """Canonical action (blueprint §8). source_index points at the actual option."""

    action_id: str
    action_type: str = "UNKNOWN"
    parameters: dict[str, Any] = field(default_factory=dict)
    target: str = "UNKNOWN"
    resource_cost: str = ""
    resource_gain: str = ""
    immediate_effect: str = "UNKNOWN"
    strategic_features: dict[str, Any] = field(default_factory=dict)
    source_index: int = -1
    legality_status: str = "VERIFIED"  # VERIFIED / INVALID / UNKNOWN
    raw_option: dict[str, Any] | None = None

    def validate(self) -> "Action":
        _require(bool(self.action_id), "action_id required")
        _require(self.source_index >= -1, "source_index must be >= -1")
        return self


@dataclass
class Observation:
    """Canonical observation (blueprint §1, §7).

    This is the internal interface produced by the simulator adapter and
    consumed by the information guard + policy layers.
    """

    raw: dict[str, Any]
    visible_state: GameState | None
    legal_actions: list[Action]
    metadata: dict[str, Any] = field(default_factory=dict)
    source: ResultSource = ResultSource.LOCAL_EXPERIMENT

    def validate(self) -> "Observation":
        _require(isinstance(self.raw, dict), "raw must be a dict")
        for a in self.legal_actions:
            a.validate()
        if self.visible_state is not None:
            self.visible_state.validate()
        return self


@dataclass
class Deck:
    """A 60-card deck. card_ids may repeat (max 4 copies of non-energy cards)."""

    decklist: list[str]           # 60 entries, card IDs
    name: str = ""
    source: str = ""

    def validate(self) -> "Deck":
        _require(len(self.decklist) == 60, f"deck must be 60 cards, got {len(self.decklist)}")
        return self

    def to_dict(self) -> dict:
        return {"name": self.name, "source": self.source, "decklist": list(self.decklist)}


@dataclass
class OpponentBelief:
    """Never force certainty (blueprint §10). P(archetype | evidence)."""

    archetype_probs: dict[str, float] = field(default_factory=dict)
    deck_belief: dict[str, float] = field(default_factory=dict)  # card_id -> prob
    uncertainty: float = 1.0

    def validate(self) -> "OpponentBelief":
        _require(0.0 <= self.uncertainty <= 1.0, "uncertainty must be in [0,1]")
        _require(abs(sum(self.archetype_probs.values()) - 1.0) < 1e-6 or not self.archetype_probs,
                 "archetype_probs must sum to 1 when non-empty")
        return self


# ---------------------------------------------------------------------------
# Experiment / evaluation records
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    """One comparison result with uncertainty (blueprint §3, §15)."""

    experiment_id: str
    model: str
    deck: str
    opponents: list[str]
    games: int
    wins: int
    losses: int = 0
    draws: int = 0
    win_rate: float = 0.0
    ci: list[float] = field(default_factory=lambda: [0.0, 0.0])
    seed: int = -1
    source: ResultSource = ResultSource.LOCAL_EXPERIMENT
    environment: str = "MOCK"
    fallback_rate: float = 0.0
    crash_rate: float = 0.0
    invalid_action_rate: float = 0.0
    game_length_mean: float = 0.0
    runtime_s: float = 0.0
    notes: str = ""

    def validate(self) -> "EvaluationResult":
        _require(self.games > 0, "games must be > 0")
        _require(self.wins + self.losses + self.draws <= self.games, "games accounting exceeds games")
        _require(self.environment in ("MOCK", "VERIFIED_REAL", "REAL_SIMULATOR_UNAVAILABLE"),
                 f"invalid environment {self.environment}")
        return self

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "source": self.source.value,
            "model": self.model,
            "deck": self.deck,
            "opponents": list(self.opponents),
            "games": self.games,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "win_rate": round(self.win_rate, 4),
            "ci": [round(x, 4) for x in self.ci],
            "seed": self.seed,
            "environment": self.environment,
            "fallback_rate": round(self.fallback_rate, 4),
            "crash_rate": round(self.crash_rate, 4),
            "invalid_action_rate": round(self.invalid_action_rate, 4),
            "game_length_mean": round(self.game_length_mean, 4),
            "runtime": round(self.runtime_s, 4),
            "notes": self.notes,
        }


@dataclass
class ExperimentConfig:
    """Every experiment must be named and fully configured (blueprint §15)."""

    experiment_id: str
    phase: int
    model: str
    deck: str
    opponents: list[str]
    seed: int
    environment: str = "MOCK"
    games: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> "ExperimentConfig":
        _require(bool(self.experiment_id), "experiment_id is mandatory")
        _require(1 <= self.phase <= 6, "phase must be in 1..6")
        _require(bool(self.model), "model is mandatory")
        _require(self.games >= 0, "games must be >= 0")
        return self