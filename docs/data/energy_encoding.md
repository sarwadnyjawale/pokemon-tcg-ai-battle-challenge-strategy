# Energy Symbol Encoding (Phase 1)

## Rule
`data/processed/energy_symbol_registry.json` is the ONLY source of truth for
energy-symbol semantics. Symbols are scanned from the CSV, never hard-coded as
eternal truth. Unknown symbols are recorded as UNKNOWN until cross-checked
against the engine (owner: engine contract, not the data layer).

## Observed symbols (primary file, `EN_Card_Data (1).csv`)

| Symbol | Meaning (registry status) | cabt EnergyType |
|--------|---------------------------|-----------------|
| G | Grass — VERIFIED (INFERENCE vs engine) | GRASS=1 |
| R | Fire — VERIFIED (INFERENCE) | FIRE=2 |
| W | Water — VERIFIED (INFERENCE) | WATER=3 |
| L | Lightning — VERIFIED (INFERENCE) | LIGHTNING=4 |
| P | Psychic — VERIFIED (INFERENCE) | PSYCHIC=5 |
| F | Fighting — VERIFIED (INFERENCE) | FIGHTING=6 |
| D | Darkness — VERIFIED (INFERENCE) | DARKNESS=7 |
| M | Metal — VERIFIED (INFERENCE) | METAL=8 |
| C | Colorless — VERIFIED (INFERENCE) | COLORLESS=0 |
| ex | Card marker (ex label), NOT energy — UNKNOWN | — |
| V | Card marker (V label), NOT energy — UNKNOWN | — |
| A | marker ("A" vs "B" attack cost?) — UNKNOWN | — |
| N | marker — UNKNOWN | — |
| Team Rocket | Trainer's Pokémon marker — UNKNOWN | TEAM_ROCKET=11 is an energy type; do not conflate |
| ACE SPEC | card class marker — UNKNOWN | — |
| (竜 U+7ADC) | Dragon type appears directly in the **Type** column (71 rows), not inside braces — VERIFIED observation | DRAGON=9 |

Meaning mapping is labeled INFERENCE because it is inferred from the cabt enum
ordering + standard PTCG convention and has NOT yet been independently
reproduced end-to-end in the engine (no `api.all_card_data()` in the pip
binding). Cross-check scheduled before Phase 2.

## Encoding mechanics
- CSV files are UTF-8. File `EN Card Data (1).csv` carries a UTF-8 BOM.
- Cost/damage/effect cells contain embedded newlines; CSV must be parsed with
  the `csv` module (naive line splitting undercounts rows).
- `AttackCost` is preserved verbatim now (raw). Structured parsing is deferred
  to Phase 4/5 and must go through this registry.