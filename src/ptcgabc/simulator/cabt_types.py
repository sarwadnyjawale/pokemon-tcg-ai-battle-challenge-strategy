"""Typed mirror of the verified cabt engine contract.

Everything here was cross-checked against:
1. Official API docs: https://matsuoinstitute.github.io/cabt/api.html
2. The bundled engine wrapper (kaggle_environments.envs.cabt.cabt)
3. A live battle against the bundled cg.dll on this machine.

See docs/simulator/verified_contract.md for the provenance table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class AreaType(IntEnum):
    DECK = 1
    HAND = 2
    DISCARD = 3
    ACTIVE = 4
    BENCH = 5
    PRIZE = 6
    STADIUM = 7
    ENERGY = 8
    TOOL = 9
    PRE_EVOLUTION = 10
    PLAYER = 11
    LOOKING = 12


class EnergyType(IntEnum):
    COLORLESS = 0
    GRASS = 1
    FIRE = 2
    WATER = 3
    LIGHTNING = 4
    PSYCHIC = 5
    FIGHTING = 6
    DARKNESS = 7
    METAL = 8
    DRAGON = 9
    RAINBOW = 10
    TEAM_ROCKET = 11


class CardType(IntEnum):
    POKEMON = 0
    ITEM = 1
    TOOL = 2
    SUPPORTER = 3
    STADIUM = 4
    BASIC_ENERGY = 5
    SPECIAL_ENERGY = 6


class SpecialConditionType(IntEnum):
    POISON = 0
    BURN = 1
    SLEEP = 2
    PARALYZE = 3
    CONFUSE = 4


class SelectType(IntEnum):
    MAIN = 0
    CARD = 1
    ATTACHED_CARD = 2
    CARD_OR_ATTACHED_CARD = 3
    ENERGY = 4
    SKILL = 5
    ATTACK = 6
    EVOLVE = 7
    COUNT = 8
    YES_NO = 9
    SPECIAL_CONDITION = 10


class SelectContext(IntEnum):
    MAIN = 0
    SETUP_ACTIVE_POKEMON = 1
    SETUP_BENCH_POKEMON = 2
    SWITCH = 3
    TO_ACTIVE = 4
    TO_BENCH = 5
    TO_FIELD = 6
    TO_HAND = 7
    DISCARD = 8
    TO_DECK = 9
    TO_DECK_BOTTOM = 10
    TO_PRIZE = 11
    NOT_MOVE = 12
    DAMAGE_COUNTER = 13
    DAMAGE_COUNTER_ANY = 14
    DAMAGE = 15
    REMOVE_DAMAGE_COUNTER = 16
    HEAL = 17
    EVOLVES_FROM = 18
    EVOLVES_TO = 19
    DEVOLVE = 20
    ATTACH_FROM = 21
    ATTACH_TO = 22
    DETACH_FROM = 23
    LOOK = 24
    EFFECT_TARGET = 25
    DISCARD_ENERGY_CARD = 26
    DISCARD_TOOL_CARD = 27
    SWITCH_ENERGY_CARD = 28
    DISCARD_CARD_OR_ATTACHED_CARD = 29
    DISCARD_ENERGY = 30
    TO_HAND_ENERGY = 31
    TO_DECK_ENERGY = 32
    SWITCH_ENERGY = 33
    SKILL_ORDER = 34
    ATTACK = 35
    DISABLE_ATTACK = 36
    EVOLVE = 37
    DRAW_COUNT = 38
    DAMAGE_COUNTER_COUNT = 39
    REMOVE_DAMAGE_COUNTER_COUNT = 40
    IS_FIRST = 41
    MULLIGAN = 42
    ACTIVATE = 43
    FIRST_EFFECT = 44
    MORE_DEVOLVE = 45
    COIN_HEAD = 46
    AFFECT_SPECIAL_CONDITION = 47
    RECOVER_SPECIAL_CONDITION = 48


class OptionType(IntEnum):
    NUMBER = 0
    YES = 1
    NO = 2
    CARD = 3
    TOOL_CARD = 4
    ENERGY_CARD = 5
    ENERGY = 6
    PLAY = 7
    ATTACH = 8
    EVOLVE = 9
    ABILITY = 10
    DISCARD = 11
    RETREAT = 12
    ATTACK = 13
    END = 14
    SKILL = 15
    SPECIAL_CONDITION = 16


class LogType(IntEnum):
    SHUFFLE = 0
    HAS_BASIC_POKEMON = 1
    TURN_START = 2
    TURN_END = 3
    DRAW = 4
    DRAW_REVERSE = 5
    MOVE_CARD = 6
    MOVE_CARD_REVERSE = 7
    SWITCH = 8
    CHANGE = 9
    PLAY = 10
    ATTACH = 11
    EVOLVE = 12
    DEVOLVE = 13
    MOVE_ATTACHED = 14
    ATTACK = 15
    HP_CHANGE = 16
    POISONED = 17
    BURNED = 18
    ASLEEP = 19
    PARALYZED = 20
    CONFUSED = 21
    COIN = 22
    RESULT = 23


# Result reasons per LogType.RESULT
RESULT_REASON = {1: "0 prize cards", 2: "no deck", 3: "no Active Pokemon", 4: "card effect"}


@dataclass
class CabtCard:
    id: int
    serial: int
    playerIndex: int

    @staticmethod
    def from_dict(d: dict) -> "CabtCard":
        return CabtCard(int(d["id"]), int(d["serial"]), int(d.get("playerIndex", -1)))


@dataclass
class CabtPokemon:
    id: int
    serial: int
    hp: int
    maxHp: int
    appearThisTurn: bool
    energies: list[int]
    energyCards: list[CabtCard]
    tools: list[CabtCard]
    preEvolution: list[CabtCard]
    playerIndex: int = -1

    @staticmethod
    def from_dict(d: dict) -> "CabtPokemon":
        return CabtPokemon(
            id=int(d["id"]),
            serial=int(d["serial"]),
            hp=int(d["hp"]),
            maxHp=int(d["maxHp"]),
            appearThisTurn=bool(d.get("appearThisTurn", False)),
            energies=[int(e) for e in d.get("energies", [])],
            energyCards=[CabtCard.from_dict(x) for x in d.get("energyCards", [])],
            tools=[CabtCard.from_dict(x) for x in d.get("tools", [])],
            preEvolution=[CabtCard.from_dict(x) for x in d.get("preEvolution", [])],
            playerIndex=int(d.get("playerIndex", -1)),
        )


@dataclass
class CabtPlayerState:
    active: list[CabtPokemon | None]
    bench: list[CabtPokemon]
    benchMax: int
    deckCount: int
    discard: list[CabtCard]
    hand: list[CabtCard] | None
    handCount: int
    prize: list[CabtCard | None]
    poisoned: bool
    burned: bool
    asleep: bool
    paralyzed: bool
    confused: bool


@dataclass
class CabtState:
    turn: int
    turnActionCount: int
    yourIndex: int
    firstPlayer: int
    supporterPlayed: bool
    stadiumPlayed: bool
    energyAttached: bool
    retreated: bool
    result: int
    stadium: list[CabtCard]
    looking: list[CabtCard | None] | None
    players: list[CabtPlayerState]


@dataclass
class CabtOption:
    type: int
    number: int | None = None
    area: int | None = None
    index: int | None = None
    playerIndex: int | None = None
    toolIndex: int | None = None
    energyIndex: int | None = None
    count: int | None = None
    inPlayArea: int | None = None
    inPlayIndex: int | None = None
    attackId: int | None = None
    cardId: int | None = None
    serial: int | None = None
    specialConditionType: int | None = None


@dataclass
class CabtSelectData:
    type: int
    context: int
    minCount: int
    maxCount: int
    remainDamageCounter: int
    remainEnergyCost: int
    option: list[CabtOption]
    deck: list[CabtCard] | None
    contextCard: CabtCard | None
    effect: CabtCard | None


@dataclass
class CabtLog:
    type: int
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class CabtObservation:
    """The raw engine observation (as delivered to the selecting agent)."""

    select: CabtSelectData | None
    logs: list[CabtLog]
    current: CabtState | None
    search_begin_input: str | None = None
    raw: dict[str, Any] | None = None

    @staticmethod
    def from_dict(d: dict) -> "CabtObservation":
        sel = d.get("select")
        cur = d.get("current")
        return CabtObservation(
            select=_parse_select(sel) if sel is not None else None,
            logs=[CabtLog(type=lg.get("type", -1), fields=lg) for lg in d.get("logs", []) or []],
            current=_parse_state(cur) if cur is not None else None,
            search_begin_input=d.get("search_begin_input"),
            raw=dict(d),
        )


def _parse_select(d: dict) -> CabtSelectData:
    opts = [CabtOption(**{k: v for k, v in o.items() if k != "type"}, type=int(o["type"])) for o in d.get("option", [])]
    return CabtSelectData(
        type=int(d["type"]),
        context=int(d["context"]),
        minCount=int(d.get("minCount", 0)),
        maxCount=int(d.get("maxCount", 0)),
        remainDamageCounter=int(d.get("remainDamageCounter", 0)),
        remainEnergyCost=int(d.get("remainEnergyCost", 0)),
        option=opts,
        deck=[CabtCard.from_dict(x) for x in d["deck"]] if d.get("deck") is not None else None,
        contextCard=CabtCard.from_dict(d["contextCard"]) if d.get("contextCard") else None,
        effect=CabtCard.from_dict(d["effect"]) if d.get("effect") else None,
    )


def _parse_state(d: dict) -> CabtState:
    players = [_parse_player(p) for p in d.get("players", [])]
    return CabtState(
        turn=int(d.get("turn", 0)),
        turnActionCount=int(d.get("turnActionCount", 0)),
        yourIndex=int(d.get("yourIndex", 0)),
        firstPlayer=int(d.get("firstPlayer", -1)),
        supporterPlayed=bool(d.get("supporterPlayed", False)),
        stadiumPlayed=bool(d.get("stadiumPlayed", False)),
        energyAttached=bool(d.get("energyAttached", False)),
        retreated=bool(d.get("retreated", False)),
        result=int(d.get("result", -1)),
        stadium=[CabtCard.from_dict(x) for x in d["stadium"]] if d.get("stadium") else [],
        looking=[CabtCard.from_dict(x) if x is not None else None for x in d["looking"]] if d.get("looking") is not None else None,
        players=players,
    )


def _parse_player(p: dict) -> CabtPlayerState:
    return CabtPlayerState(
        active=[CabtPokemon.from_dict(x) if x is not None else None for x in p.get("active", [])],
        bench=[CabtPokemon.from_dict(x) for x in p.get("bench", [])],
        benchMax=int(p.get("benchMax", 5)),
        deckCount=int(p.get("deckCount", 0)),
        discard=[CabtCard.from_dict(x) for x in p.get("discard", [])],
        hand=[CabtCard.from_dict(x) for x in p["hand"]] if p.get("hand") is not None else None,
        handCount=int(p.get("handCount", 0)),
        prize=[CabtCard.from_dict(x) if x is not None else None for x in p.get("prize", [])],
        poisoned=bool(p.get("poisoned", False)),
        burned=bool(p.get("burned", False)),
        asleep=bool(p.get("asleep", False)),
        paralyzed=bool(p.get("paralyzed", False)),
        confused=bool(p.get("confused", False)),
    )