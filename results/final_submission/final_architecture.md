# Final Architecture Description

**Project:** PTCG AI Battle Challenge (Agent Optimization)
**Status:** IMPLEMENTED (Final Submission Freeze)

This document describes the actual implemented and verified architecture. Rejected/experimental components (like Target Selection EXP-006/007) are specifically excluded from the primary execution path.

## 1. Real CABT Interface (`environment/cabt_adapter.py`)
- **Status: IMPLEMENTED**
- Integrates directly with the `cg.dll` engine via `kaggle_environments`. 
- Ensures all evaluation metrics are gathered from real gameplay simulations, bypassing the static constraints of `MockSimulator`.

## 2. Information Firewall (`agent/information_guard.py`)
- **Status: IMPLEMENTED**
- Enforces strict constraints on observation parsing.
- Ensures opponent hand contents, deck order, and hidden prize identities are never exposed to the policy layer.

## 3. Canonical State & Legal Action Representation (`environment/enriched_adapter.py`)
- **Status: IMPLEMENTED**
- Maps the raw CABT dictionary output to semantic features.
- Bridging the engine's raw `attackId` (a globally contiguous integer) to the exact attack semantics by dynamic `_CARD_MIN_ATTACK_ID` caching.
- Dynamically enriches each CABT `option` (e.g., matching a `play` option to its exact `card_category`).

## 4. Context Router (`policy/context_router.py`)
- **Status: IMPLEMENTED**
- Prevents "context blindness" by intercepting CABT's distinct input modes (`MAIN`, `CARD_SELECTION`, `SETUP`, `NUMBER_CHOICE`).
- Routes `MAIN` context requests to the `TempoScorer` and search/setup requests to the `CardValueScorer`.

## 5. Card Level Intelligence (`policy/card_value.py`)
- **Status: IMPLEMENTED**
- Scores specific cards based on game phase and board needs.
- Identifies Evolution bases, basic attackers, and critical Trainers (draw vs search).

## 6. Tempo Scorer (`policy/tempo.py`)
- **Status: IMPLEMENTED**
- Core engine for strategic decision making in the `MAIN` context.
- Implements dynamic priority: `Attack > Evolve > Attach > Play > End`.
- Avoids arbitrary "always attack" rules by evaluating the strategic consequence of actions based on current game phase and board state.

## 7. Semantic Attack & Ability Evaluation (`policy/attack_value.py`, `policy/ability_value.py`)
- **Status: IMPLEMENTED**
- Dynamically parses canonical database string properties.
- Injects current board state (`AttackContext`) to correctly map multiplier damages (e.g. `50 * own_bench_count` for Pikachu ex's Circle Circuit).
- Evaluates `GUARANTEED_KO`, `PROBABLE_KO`, `CONDITIONAL_KO`, and `NO_KO` dynamically based on remaining opponent HP.

## 8. Symbolic Tactical Consequence Evaluator (`policy/tactical_consequence.py`)
- **Status: IMPLEMENTED**
- Replaces native MCTS/rollouts due to native DLL constraints.
- Emulates 1-step lookahead by enforcing optimal sequencing. For example, applies a massive mathematical penalty if the agent attempts to play a hand-discarding Supporter *before* attaching an available Energy card.

## 9. Action Safety Gate (`policy/action_safety.py`)
- **Status: IMPLEMENTED**
- End-turn discipline logic that penalizes ending the turn when a productive action (attack, evolve, attach energy) is legally available.

## 10. Deck Selection Methodology
- **Status: IMPLEMENTED**
- Identified the evolution bottleneck of the Dragapult ex deck.
- Evaluated 4 distinct archetypes locally.
- Pivoted to the `Pikachu Aggro` deck, bypassing early-game failure cascades.

## Components Not Included
- **Sequencing Lookahead / Native MCTS:** REJECTED (Hardware/Engine Blocker). The `kaggle_environments` `env.clone()` fails to fork the native `cg.dll` C++ state because it utilizes a singleton pointer (`Battle.battle_ptr`). Safe consequence-evaluation is physically impossible without native DLL access.
- **Target Selection (EXP-006/007):** REJECTED. Found to induce excessive opportunity cost (wasting Supporter usage on unkillable Bench threats).
- **Opponent Modelling:** Not implemented.
- **Reinforcement Learning (PPO):** Not implemented.
