# Verified Simulator Contract (Phase 1)

Every claim below was checked against ONE of:
- (A) the bundled engine wrapper: `kaggle_environments.envs.cabt.cg.game`
  (`C:\Users\sarwa\AppData\Roaming\Python\Python314\site-packages\kaggle_environments\envs\cabt\`)
- (B) the official API reference: https://matsuoinstitute.github.io/cabt/api.html
- (C) a live battle against `cg.dll` on this machine (Windows), using a
  known-legal 60-card deck (public reference `decks/dragapult_ex/deck.csv`).

Status values: VERIFIED = reproduced locally; INFERENCE = consistent with (B)
but not independently reproduced; UNKNOWN = not yet resolved.

## 1. Engine lifecycle

| Fact | Status | Evidence |
|------|--------|----------|
| `battle_start(deck0, deck1)` requires two 60-card lists | VERIFIED | (A) raises `ValueError("The deck must contain 60 cards.")` |
| Legal deck → `errorPlayer == -1` | VERIFIED | (C) dragapult_ex deck: errorPlayer=-1, errorType=0, battlePtr set |
| Illegal deck (e.g. 60 copies of one ID) → rejected before battle_ptr is set | VERIFIED | (C) `[3]*60` → errorPlayer=0, errorType=3, battlePtr=None |
| First observation is the go-first decision | VERIFIED | (C) first obs: current.turn=0, current.result=-1, select.type=9 (YES_NO), select.context=41 (IS_FIRST) |
| `battle_select(list[int])` returns next observation | VERIFIED | (A) signature + (C) live play |
| `battle_select` out-of-range index → engine rejects | VERIFIED | (C) live loop: index in-range-but-rejected raised from lib.Select err |
| Out-of-range/native rejections surface as Python exceptions, never silent | VERIFIED | (A) `lib.Select` err → `IndexError`; adapter wraps into `BattleStepError` |
| `battle_finish()` frees engine memory | VERIFIED | (A) |

**Deck error codes (observed values):** errorType=3 on >4 duplicates / invalid composition; errorType=4 on unrecognized card IDs. Exact meaning per code is deduced from local reproduction, not from official docs → **INFERENCE**, to be re-confirmed in Phase 2.

## 2. Observation structure

| Fact | Status | Evidence |
|------|--------|----------|
| Obs keys: `select`, `logs`, `current`, `search_begin_input` | VERIFIED | (C) live dump; (A) `_get_battle_data()` adds `search_begin_input` |
| `current` keys: turn, turnActionCount, yourIndex, firstPlayer, supporterPlayed, stadiumPlayed, energyAttached, retreated, result, stadium, looking, players | VERIFIED | (C) |
| player keys: active, bench, benchMax, deckCount, discard, hand, handCount, prize, poisoned, burned, asleep, paralyzed, confused | VERIFIED | (C) |
| pokemon keys: appearThisTurn, energies, energyCards, hp, id, maxHp, preEvolution, serial, tools | VERIFIED | (C) |
| `players[i].hand` is a list for YOUR hand, `None` for the opponent (only handCount visible) | VERIFIED | (C) live dumps across a full game |
| prize slots are `None` while facedown | VERIFIED | (C) |
| `current.result` is `-1` until the match ends | VERIFIED | (C) |
| logs only cover events up to the current selection | VERIFIED | (B) description + (C) |

## 3. Decision interface

| SelectType | id | Seen live | Evidence |
|-----------|----|-----------|----------|
| MAIN | 0 | yes | (C) |
| CARD | 1 | yes | (C) |
| ENERGY | 4 | yes | (C) |
| COUNT | 8 | yes | (C) |
| YES_NO | 9 | yes | (C) IS_FIRST |
| ATTACK, EVOLVE, SKILL, … | 6,7,5,… | not yet | (B) |

| SelectContext | id | Seen live |
|---------------|----|-----------|
| SETUP_ACTIVE_POKEMON | 1 | yes |
| SETUP_BENCH_POKEMON | 2 | yes |
| SWITCH / TO_ACTIVE | 3 / 4 | yes |
| TO_HAND | 7 | yes |
| DISCARD | 8 | yes |
| ATTACH_TO | 22 | yes |
| DISCARD_ENERGY | 30 | yes |
| DRAW_COUNT | 38 | yes |
| IS_FIRST | 41 | yes |

Option fields observed: type, number, area, index, playerIndex, toolIndex, energyIndex, count, inPlayArea, inPlayIndex, attackId, cardId, serial, specialConditionType — matches (B).

## 4. Enums (from (B), used to type the contract)

- EnergyType: COLORLESS=0 … TEAM_ROCKET=11 (GRASS=1, FIRE=2, WATER=3, LIGHTNING=4, PSYCHIC=5, FIGHTING=6, DARKNESS=7, METAL=8, DRAGON=9, RAINBOW=10).
- CardType: POKEMON=0 … SPECIAL_ENERGY=6.
- SpecialConditionType: POISON/BURN/SLEEP/PARALYZE/CONFUSE.
- LogType incl. DRAW (own cardId revealed), DRAW_REVERSE (opponent, no cardId), MOVE_CARD vs MOVE_CARD_REVERSE (facedown).
- SelectType full list (MAIN…SPECIAL_CONDITION=10); SelectContext full list (MAIN…RECOVER_SPECIAL_CONDITION=48).

## 5. Search API (partial determinization)

`search_begin/search_step/search_end/search_release` exist in (B) but are NOT
exported by the pip binding (`kaggle_environments.envs.cabt.cg.game`).
Status: **UNKNOWN / not available on this build** — recorded, not assumed.
`obs["search_begin_input"]` is populated by the engine for agents that use it.

## 6. Behavior of the adapter under failure

- Bounds-checked selection: the adapter validates option indices against the
  last observation BEFORE calling the native DLL, because out-of-range indices
  crash it (native access violation → `OSError`). A rejection is recorded as
  `INVALID_ACTION`; the game is treated as a loss for the offending side.
- Agent exceptions are recorded as `AGENT_EXCEPTION` and fall back to the first
  option; the failure appears in the run record (never hidden).