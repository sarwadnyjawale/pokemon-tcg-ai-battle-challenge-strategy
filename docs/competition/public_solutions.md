# Public References — Simulation Track (Phase 1)

All third-party material used anywhere in this project must be listed here and
labeled PUBLIC_REFERENCE. Public references are NEVER re-labeled as local or
official results.

| Reference | URL | What it provides | Label |
|-----------|-----|------------------|-------|
| AnishGharat / pokemon-kaggle | https://github.com/AnishGharat/pokemon-kaggle | Example agents (dragapult_ex, mega_lucario_ex, generic_ai, random_baseline), deckbuilder, eval harness, `EN_Card_Data.csv`, and verified-legal `decks/dragapult_ex/deck.csv` used for engine contract tests | PUBLIC_REFERENCE |
| Kaggle — Strategy competition | https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy | Official rules, 2000-word limit, 70/20/10 rubric | OFFICIAL_DOCUMENTATION |
| Kaggle — Simulation competition | https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-simulation | Official simulation scoring (TrueSkill-like, μ₀=600), submission `.tar.gz` contract | OFFICIAL_DOCUMENTATION |
| cabt engine docs | https://matsuoinstitute.github.io/cabt/ (api.html) | Full enum / dataclass reference for the engine contract | OFFICIAL_DOCUMENTATION |
| kaggle-environments (pip) | installed package under site-packages | Bundled `cg.dll` / wrapper used for VERIFIED_REAL local games | PUBLIC_REFERENCE |

## Rules
- Any code or deck JSON copied from a reference carries that reference's label
  in its metadata (see `src/ptcgabc/provenance.py`).
- `decks/dragapult_ex/deck.csv` is used ONLY to run engine contract tests; it is
  not claimed as our deck.