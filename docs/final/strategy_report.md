# PTCG AI Battle Challenge: Strategic Decision-Making via Semantic State Evaluation

 ABSTRACT

Developing autonomous agents for the Pokémon Trading Card Game (PTCG) requires navigating immense state-space complexity, incomplete information, and rigid legality constraints. Rather than attempting unguided search (e.g., MCTS) or premature reinforcement learning on a raw action space, we constructed an evidence-driven, deterministic evaluation architecture. By dynamically parsing low-level engine observations into a semantically enriched tactical state, our agent maps abstract CABT options to concrete strategic values. Paired with a fast-attacking Pikachu Aggro deck and a Symbolic Consequence Evaluator to enforce principled action sequencing, the system achieved a 29.2% win rate against a random opponent and zero legal errors across extended local CABT simulation benchmarks. This report details the failure-driven optimization loop, dynamic attack evaluation, and the architectural discoveries that guided our development process.

 1. PROBLEM

The Pokémon TCG operates as a highly complex Partially Observable Markov Decision Process (POMDP). Agents face 60-card decks, multi-turn setup dependencies, stochastic consequences, and a variable-length game loop where the action-space branches heavily. A single turn may require a sequence of dependent actions: evolving a Pokémon, attaching an Energy card, playing a Supporter, making sub-selections (like targeting cards to discard), and finally attacking.

The primary technical bottleneck lies in the simulation interface. The CABT engine expects integer arrays mapping to discrete options, devoid of natural game text. Translating these low-level, index-based commands into a semantic understanding of the game state is the fundamental challenge of building a competitive agent.

 2. STRATEGIC THESIS

Our core thesis frames the challenge as a semantic legal-action decision problem under partial information. Early in development, we conducted a capability audit of the CABT environment to determine if forward-simulation (MCTS or shallow rollouts) was viable. The exposed Python cloning mechanism did not safely isolate native CABT state in our audit, so native H=1 rollout was rejected. Consequently, the intelligence challenge is strictly zero-step: “What is the strategically best legal action given only the current visible state?”

To answer this, our architecture layers progressively richer semantic interpretations over the raw state:

CABT Observation → Information Firewall → Canonical Semantic State → Legal Action Enrichment → Context Routing → Card/Tempo Intelligence → Dynamic Attack Semantics → Symbolic Consequence Reasoning → Action Ranking.

 3. REAL CABT ENVIRONMENT

The agent interfaces natively with the verified `cg.dll` CABT engine via `kaggle_environments`. To bridge the gap between the agent's logic and the engine's requirements, the `enriched_adapter.py` module acts as a robust translation layer.

CABT supplies raw options such as `{"type": 13, "attackId": 456}`. The adapter intercepts these options, caches the minimum `attackId` seen for a specific card, and maps the global engine ID back to our canonical database attacks array. Crucially, the adapter manages complex sub-selections (like resolving a required 2-card discard from Ultra Ball) by matching the engine's `minCount` constraints. This careful bridging resulted in a measured legal error rate of 0 across all evaluated benchmarks.

 4. INFORMATION CONSTRAINTS

Adherence to the engine's information boundaries is maintained through a dedicated information firewall (`LeakageGuard`). The agent operates entirely on the `visible_state`.

Opponent hand contents, deck order, and face-down prize cards are never exposed to the policy layer. When calculating KO probabilities or threat levels, the agent relies exclusively on the opponent's `max_hp` minus their visible `damage`. Uncertainty is evaluated strictly through mathematical expectation based on visible text.

 5. DECK–POLICY INTERACTION

One of our strongest discoveries is the relationship between deck complexity and agent capability. We initially evaluated a Dragapult ex evolution-heavy archetype. Telemetry revealed a structural flaw: the agent suffered a 75% “setup failure” rate, frequently losing within the first 3 turns before it could establish a Stage 2 attacker.

We hypothesized that shifting to a Basic-heavy deck would bypass this cognitive bottleneck.

Deck Comparison (n=60 vs random, REAL_CABT_LOCAL)

| Deck | Win Rate | Mean Attacks/Game | Zero-Attack Rate |
|------|----------|-------------------|------------------|
| Dragapult ex (Evolution) | 5.0% | 1.42 | 75.0% |
| Pikachu ex (Aggro) | 18.3% | 5.35 | 41.6% |

Changing the deck dramatically reduced the number of decisions required before productive attacking became possible, suggesting that deck selection and policy design cannot be treated independently.

 6. FINAL ARCHITECTURE

The final agent operates through a deterministic, context-aware pipeline:

```text
REAL CABT OBSERVATION
        ↓
INFORMATION FIREWALL
        ↓
CANONICAL GAME STATE
        ↓
SEMANTIC LEGAL ACTIONS
        ↓
CONTEXT ROUTER
        ↓
┌──────────────────────────────────┐
│ Card Value Scorer                │
│ Tempo / Setup Scorer             │
│ Dynamic Attack Evaluator         │
│ Action Safety Gate               │
│ Symbolic Consequence Evaluator   │
└──────────────────────────────────┘
        ↓
ACTION RANKING
        ↓
LEGAL CABT ACTION
```

- Context Router:** Categorizes the decision type (`MAIN`, `CARD_SELECTION`, `SETUP`).
- Tempo Scorer:** Evaluates action priority based on current board state.
- Attack Evaluator:** Calculates `GUARANTEED_KO`, `PROBABLE_KO`, or `NO_KO` by dynamically mapping attacks to the current board state.
- **Symbolic Consequence Evaluator:** Emulates one-step consequence reasoning by enforcing action sequencing (for example, penalizing drawing cards before attaching available Energy when that would destroy guaranteed board development).

 7. EXPERIMENTAL METHOD

Development was strictly empirical. Every major addition was benchmarked independently.

Experiment Evolution (vs random, REAL_CABT_LOCAL)**

| Experiment | Hypothesis | Result | Decision |
|------------|------------|--------|----------|
| B6 Baseline | Starting heuristic foundation | 11.7% | BASELINE |
| EXP-003 (Tempo) | Tempo scoring improves priorities | 11.7% | KEEP |
| EXP-005 (Full) | Combined scoring synergizes | 16.7% | KEEP |
| EXP-006 (Target) | Target scoring isolates threats | 11.7% | REJECT |
| EXP-008 (Tactical) | Symbolic sequencing prevents errors | 29.2% | KEEP |

 8. KEY DISCOVERIES

Native Engine Constraints: Our most informative architectural discovery occurred during an attempt to implement Monte Carlo Tree Search (MCTS) and shallow rollouts. The exposed Python cloning mechanism did not safely isolate native CABT state in our audit, so native H=1 rollout was rejected. Because the engine operates on a shared singleton pointer (`Battle.battle_ptr`), consequence-aware rollouts corrupted the live game. This limitation guided our architectural pivot towards zero-step semantic evaluation.

Symbolic Consequence Reasoning: Because native rollouts were rejected, we built a `TacticalConsequenceEvaluator` to approximate one-step planning. It symbolically evaluates the opportunity cost of sequencing errors. For example, if the agent attempts to play Professor's Research while holding an unattached Energy card, the evaluator applies a penalty for destroying guaranteed board development. Paired evaluations demonstrated that this sequencing change produced a significant improvement in the measured benchmark.

 9. FAILED TARGET-SELECTION EXPERIMENT

In EXP-006, we implemented a `TargetSelectionScorer` to evaluate opponent Bench threats for Boss's Orders plays.

Negative Experiment (n=120 vs random, REAL_CABT_LOCAL)

- Baseline (EXP-005): 23.3% WR
- Static Target (EXP-006): 11.7% WR

Why it failed: The heuristic overvalued high-threat targets without considering tactical feasibility. The agent frequently used its single Supporter action to pull a 200+ HP attacker into the active spot without having the damage to KO it. By walling itself against a threat it could not exploit, the agent triggered its own demise. Rejecting this component indicated that indiscriminate targeting is actively harmful to tempo.

 10. DYNAMIC ATTACK EVALUATION

Static card text evaluation is insufficient for PTCG. We implemented a dynamic `AttackContext` that ingests the live board state.

For example, Pikachu ex's “Circle Circuit” reads: 50 × number of Benched Pokémon. Our corrected dynamic evaluator computes `50 * context.own_bench_count` at runtime. Similarly, KO classification is evaluated securely via `remaining_hp = context.opp_max_hp - context.opp_damage`, ensuring the agent accurately categorizes `GUARANTEED_KO`s.

 11. FINAL RESULTS

The final frozen configuration (`EXP-008-L1.0` + Pikachu Aggro) was benchmarked against local agents.

Final Verified Results (n=120, REAL_CABT_LOCAL):

- vs random WR: 29.2% (95% CI: [21.8%, 37.8%])
- vs first WR: 6.7% (95% CI: [3.4%, 12.6%])
- Legal Errors: 0
- Zero-Attack Rate: 47.5%
- Latency: ~0.04 ms/decision

These measurements are derived purely from local CABT evaluation experiments. No official Kaggle Simulation leaderboard score exists or is claimed by this project.

 12. ROBUSTNESS AND LIMITATIONS

We recognize several strict limitations bound by current evidence:

1. No Official Simulation Entry The agent was not submitted to the official matchmaking servers; performance claims reflect local baselines.
2. Engine Forking Constraints: The singleton limitation prevents MCTS and native rollouts through the exposed Python interface.
3. Overlapping Confidence Intervals: Due to the extreme variance of card draw RNG, our 95% confidence intervals remain wide even at n=120.
4. No True Lookahead: The agent operates on a zero-step horizon via symbolic consequence heuristics rather than true game-tree expansion.
5.Incomplete Ability Semantics: Some complex Pokémon Abilities are scored using generic heuristic values rather than deep semantic parsing.

 13. WHAT WE WOULD DO NEXT

If development continued, future work would focus on:

- Engine Decoupling:** Modifying the native DLL hooks to support true isolated memory forks, enabling lookahead planning.
- Learned Action Ranking:** Using gathered telemetry and counterfactual logs to train a small, lightweight MLP or logistic regression model over semantic scoring features, replacing some hand-crafted tempo coefficients.

 14. CONCLUSION

We constructed an evidence-driven, deterministic evaluation architecture for the Pokémon TCG. By focusing on fixing observable failure modes (setup crashes, target blinding, dynamic damage miscalculation) and enforcing a zero-tolerance policy for legal errors, we produced a stable engine capable of navigating a complex POMDP. While the system relies on heuristic semantic state evaluation rather than self-play RL, this transparent foundation provides the syntactic and semantic correctness necessary for future researchers to implement stable tree search or reinforcement learning without being obstructed by fundamental engine translation failures.
