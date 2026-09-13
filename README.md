# PTCG AI Battle Challenge — Strategy Research Project

Research-grade, reproducible work on The Pokémon Company's **PTCG AI Battle
Challenge** (Simulation + Strategy categories on Kaggle).

> **Final frozen configuration:** EXP-008-L1.0 · **Deck:** Pikachu Aggro ·
> **Local REAL_CABT result:** 29.2% vs. random (n=120) · **Legal errors:** 0
>
> All performance figures are from local `REAL_CABT_LOCAL` evaluation. They
> are not official Kaggle Simulation leaderboard results.

## Honest status

- **Simulation entered:** `FALSE`
- There is **no** official Simulation rating, leaderboard position, or
  matchmaking result for this team.
- Every local gameplay result is labeled `LOCAL_EXPERIMENT`, never an official
  result.
- The project distinguishes: `OFFICIAL_KAGGLE_RESULT`, `LOCAL_EXPERIMENT`,
  `PUBLIC_REFERENCE`, `HYPOTHESIS`, `INFERENCE`, `UNKNOWN`.

## Status (2026-09-13) — ALL PHASES COMPLETE

| Phase | Title | Status | Tests |
|---|---|---|---|
| 1 | Foundation and Truth (data + simulator) | **DONE** | 29 |
| 2 | Deck and Strategic Intelligence | **DONE** | 38 |
| 3 | Baseline Agents and Decision Framework | **DONE** | 78 |
| 4 | Learning and Strategic Reasoning | **DONE** | 39 |
| 5 | Robustness, Ablation, Adversarial Eval | **DONE** | 26 |
| 6 | Final System, Evidence, and Report | **DONE** | 27 |

**Total: 237 tests passing.**  
See `results/phase6/checkpoint.md` and `docs/final/strategy_report.md`.

## Structure

```
blueprint.md                   Master implementation spec (6 phases)
docs/                          Phase documentation and audit reports
  final/strategy_report.md     Kaggle Strategy writeup (~1000 words)
data/raw                       Source files (immutable, hashed)
data/processed                 Derived canonical artifacts (1267 cards)
src/ptcgabc/
  data/                        CSV ingest, canonical build, provenance
  simulator/                   verified_adapter.py (real cabt engine)
  deck/                        DeckValidator, DeckAnalyzer, candidates
  state/                       StructuredGameState (hidden-info firewall)
  agents/
    baselines/                 B0-B4, B6 baseline agents
    learned/                   LinearActionScorer, REINFORCE trainer
  evaluation/                  Evaluator, ablation, adversarial
  visualization/               report_builder.py (evidence + writeup)
tests/                         237 tests across all phases
scripts/phase{1-6}_pipeline.py Phase orchestration scripts
results/phase{1-6}/            Evidence outputs and checkpoints
```

## Key findings

- **Engine-verified rules** (not blueprint guesses): 60-card deck, 7 opening hand,
  6 prizes, 4-copy non-energy limit, unlimited basic energy.
- **Hidden-information firewall** enforced: `to_feature_vector()` never exposes
  opponent hand, prize cards, deck order, or RNG seed.
- **Architecture decision tree** correctly blocked RL escalation on mock — Q1
  (learned > heuristic) only resolvable with real cabt engine.
- **FORCED_SACRIFICE** is consistently the hardest adversarial condition (WR ~59%),
  consistent across all agents.
- **0 legal errors, 0 catastrophic errors** across all 6 baseline agents.
- **Provenance audit PASS**: no `OFFICIAL_KAGGLE_RESULT` label anywhere.

## Final agent and evidence

The frozen policy converts CABT's low-level legal options into semantic actions,
routes them by decision context, and ranks them with card value, tempo, dynamic
attack, safety, and symbolic-consequence evaluators. It only uses visible game
information. See [the final architecture](results/final_submission/final_architecture.md),
[evidence table](results/final_submission/evidence_table.md), and
[strategy report](docs/final/strategy_report.md).

| Metric | Final result |
|---|---:|
| Agent | EXP-008-L1.0 |
| Deck | Pikachu Aggro |
| Opponent | Random |
| Games | 120 |
| Win rate | 29.2% (95% CI 21.8%–37.8%) |
| Legal errors | 0 |
| Policy latency | ~0.04 ms/decision |
| Official Simulation entry | No |

### Architecture

<img src="gitimages/Architecture%20digram.png" alt="Semantic agent architecture" width="900">

*Semantic evaluation turns legal CABT actions into context-aware policy choices.*

### Benchmark progression

<img src="gitimages/Pok%C3%A9mon%20TCG%20AI%20Benchmark%20Progress.png" alt="Benchmark progress" width="900">

*Benchmark results are local REAL_CABT measurements, not official leaderboard scores.*

### Deck-policy interaction

<img src="gitimages/Semantic%20Evaluation%20for%20Pok%C3%A9mon%20TCG%20AI.png" alt="Semantic evaluation and deck-policy interaction" width="900">

<img src="gitimages/ChatGPT%20Image%20Sep%2013%2C%202026%2C%2011_41_31%20PM.png" alt="Pikachu Aggro strategy illustration" width="900">

*The four project visuals summarize the semantic-policy approach and the Pikachu Aggro strategy.*

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -q
python scripts/audit_provenance.py
```

The native CABT engine and any restricted competition assets are not included.
Obtain them through the official competition distribution under its terms.

## Phases

1. Foundation and truth (data + environment verification) — **DONE**
2. Deck and strategic intelligence — **DONE**
3. Real baselines and decision framework — **DONE**
4. Learning and strategic reasoning — **DONE**
5. Robustness, ablation, adversarial testing — **DONE**
6. Final system and Strategy writeup — **DONE**

All phases complete. See `results/phase6/evidence_package.json` for the full
provenance-labeled evidence chain. Source: LOCAL_EXPERIMENT throughout.
