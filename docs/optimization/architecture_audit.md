# PTCG AI Battle Challenge — Architecture Audit (Phase 0)

**Date:** 2026-09-13
**Source:** Repository forensic analysis of entire codebase
**Status:** All 270 tests passing. Real CABT engine available.

---

## 1. SUBSYSTEM CLASSIFICATION

| Subsystem | Module | Status | Notes |
|-----------|--------|--------|-------|
| **Contracts/Types** | `contracts.py` | IMPLEMENTED | Card, Attack, Effect, GameState, Action, Observation, Deck, OpponentBelief, EvaluationResult, ExperimentConfig |
| **Error Taxonomy** | `errors.py` | IMPLEMENTED | FailureCategory, BehaviourSource, StrategicFailureType, FailureRecord, DecisionOutcome |
| **Provenance** | `provenance.py` | IMPLEMENTED | ResultSource enum, EnvironmentType enum, provenance tagging |
| **Reproducibility** | `reproduce.py` | IMPLEMENTED | seed_everything, environment_snapshot, write_json |
| **Information Guard** | `agent/information_guard.py` | IMPLEMENTED | LeakageGuard, field visibility rules |
| **Baseline Agents B0-B4** | `agents/baselines/baseline_agents.py` | IMPLEMENTED | SimulatorOrder, Random, SimpleHeuristic, TacticalGreedy, StrategicHeuristic |
| **B6 Legal Action Scorer** | `agents/baselines/legal_action_scorer.py` | IMPLEMENTED | ActionFeatures, feature extraction, heuristic weight scoring |
| **Learned Scorer** | `agents/learned/learned_scorer.py` | IMPLEMENTED | LinearActionScorer, LearnedActionScorerAgent, SelfPlayTrainer, architecture_decision_tree |
| **CABT Observation Parser** | `environment/cabt_observation_parser.py` | IMPLEMENTED | CabtGameState, CabtPlayerState, CabtSelect, CabtOption, build_feature_dict |
| **CABT Action Adapter** | `environment/cabt_action_adapter.py` | PARTIALLY_IMPLEMENTED | Maps option_type int → string label, BUT does not extract attack damage/effect/energy_cost from CABT option raw data |
| **CABT Game Loop** | `environment/cabt_adapter.py` | IMPLEMENTED | CabtGame, CabtSelfPlayRunner, CabtRunSummary |
| **Game State** | `state/game_state.py` | IMPLEMENTED | StructuredGameState, PokemonInPlay, PlayerState, GamePhase, ResourcePressure, BoardPosition |
| **Evaluator** | `evaluation/evaluator.py` | IMPLEMENTED | run_evaluation, MockSimulator, wilson_confidence_interval, run_all_baselines |
| **Adversarial** | `evaluation/adversarial.py` | IMPLEMENTED | AdversarialScenario, run_adversarial_evaluation, compute_robustness_summary |
| **Ablation** | `evaluation/ablation.py` | IMPLEMENTED | AblationCondition, FrozenBenchmark, run_ablation_study, FailureAnalyzer |
| **Mock Simulator** | `simulator/mock.py` | IMPLEMENTED | MockSimulator (testing only) |
| **CABT Types** | `simulator/cabt_types.py` | IMPLEMENTED | Full typed mirror of engine contract: OptionType, SelectContext, CabtObservation |
| **Verified Adapter** | `simulator/verified_adapter.py` | IMPLEMENTED | RealCabtBattle, run_reachable_game, translate_raw |
| **Deck Candidates** | `deck/candidates.py` | IMPLEMENTED | 4 candidate decks (Pikachu aggro, Mewtwo control, Gardevoir midrange, Dragapult reference) |
| **Deck Validator** | `deck/deck.py` | IMPLEMENTED | DeckValidator, DeckAnalyzer |
| **Deck Rules** | `deck/rules.py` | IMPLEMENTED | 60-card rules, copy limits |
| **Data Pipeline** | `data/` | IMPLEMENTED | CSV ingest, canonical cards, energy, evolution, schema registry |
| **Visualization** | `visualization/report_builder.py` | IMPLEMENTED | Report generation |
| **Experiment Metadata** | `experiments/metadata.py` | IMPLEMENTED | Experiment tracking |
| **Opponent Belief Model** | — | CONCEPTUAL_ONLY | OpponentBelief dataclass exists in contracts.py but no inference logic |
| **Strategic State Representation** | — | PARTIALLY_IMPLEMENTED | StructuredGameState exists but not connected to real CABT observation flow |
| **Search/Lookahead** | — | CONCEPTUAL_ONLY | Not implemented |
| **Policy Router** | — | CONCEPTUAL_ONLY | Not implemented |
| **Decision Telemetry** | — | PROTOTYPE | Step-level log in CabtGame but no per-option scoring telemetry |

---

## 2. CRITICAL FINDING: ACTION BRIDGE IS INFORMATION-LOSSY

**This is the #1 bottleneck preventing agent improvement on real CABT.**

### The Problem

`cabt_action_adapter.py:agent_to_cabt_action()` converts CABT options into action dicts:
```python
{"type": "attack", "cabt_option_type": 7, "cabt_option_index": 0, "raw": {...}}
```

The agents (B2-B6) score actions based on properties that are **NOT populated**:
- `action.get("damage", 0)` → always 0
- `action.get("effect_category", "")` → always ""
- `action.get("energy_cost", 0)` → always 0
- `action.get("hand_change", 0)` → always 0

The raw CABT option dict has `attackId`, `area`, `index`, `playerIndex`, `serial`, etc. — but **NOT** damage values, effect descriptions, or energy costs.

### Impact

All B2-B6 scoring logic is effectively blind when playing real CABT. The only signal is the action type string (attack/trainer/energy/pass/evolve), which is a very coarse signal. This explains:
- B1-Random: 0% WR vs CABT random
- B4-StrategicHeuristic: 0% WR vs CABT random
- B6-LegalActionScorer: 20% WR vs CABT random

The 20% WR for B6 likely comes from its end-turn penalty preventing unnecessary passing.

### Root Cause

CABT options are low-level engine actions (attach energy card at index X to Pokemon at bench position Y). They carry structural parameters (`area`, `index`, `playerIndex`, `attackId`) but not gameplay semantics (damage dealt, effect text).

To get action semantics, the agent must:
1. Cross-reference `option.attackId` or `option.cardId` with the canonical card database to get damage/effect
2. Infer action consequences from the board state change

---

## 3. MOCK SIMULATOR FINDING

Phase 3-6 mock results are **completely uninformative**. All agents show identical 65.07% WR because MockSimulator outcomes are action-independent (random prize drain unrelated to agent choices).

This was correctly noted in phase4/phase6 caveats but means all existing win rates from phases 3-6 carry zero strategy signal.

---

## 4. REAL CABT BASELINE (n=10, existing)

| Agent | vs | Games | WR | Legal Errors |
|-------|-----|-------|------|-------------|
| B1-Random | random | 10 | 0.0% | 0 |
| B0-SimulatorOrder | random | 10 | 10.0% | 0 |
| B4-StrategicHeuristic | random | 10 | 0.0% | 0 |
| B6-LegalActionScorer | random | 10 | 20.0% | 0 |
| B1-Random | first | 10 | 0.0% | 0 |

**Note:** n=10 is far too small for useful inference. 95% CI for 20% WR at n=10 is approximately [3.6%, 48.1%].

---

## 5. GAME PHASE DETERMINATION

`_game_phase(turn)` uses only turn count:
- ≤2: opening, ≤5: early, ≤10: midgame, >10: late

It does NOT consider prize counts, board state, or deck depletion. The `StructuredGameState.compute_derived_features()` does consider prizes for endgame, but this is in the structured state module which is NOT connected to the real CABT flow.

---

## 6. DECK ANALYSIS

4 candidate decks exist. Only the Dragapult reference deck has been engine-verified (used in CABT integration). All decks are structurally valid (60 cards) with real card IDs from the canonical database.

The `CabtGame.DRAGAPULT_DECK` hardcoded in `cabt_adapter.py` is the only deck used in real games.

---

## 7. HIGHEST-PRIORITY GAPS

1. **Action semantics bridge** — CABT options → agent-readable action dicts with damage, effect, energy_cost populated from card DB or board state
2. **Game phase using prize state** — Phase inference should use prize counts + board, not just turn number
3. **Decision telemetry** — Per-option scoring not recorded
4. **Sample size** — n=10 games is insufficient; need n≥50+ per condition
5. **Board state features to action scoring** — Agents receive board-level features but cannot map them to specific option consequences
6. **Seat alternation** — Current baseline only tests agent as player 0
