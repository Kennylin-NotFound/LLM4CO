# COVER-Opt Control Ablation Status

This artifact validates that method switches change real inputs and control
flow. It is not an LLM-quality or optimization-performance experiment.

| Variant | Single changed mechanism | Verified control-flow outcome |
|---|---|---|
| `targeted_valid_patch` | conflict-directed feedback | node-score Patch accepted; first feasible after two evaluations |
| `generic_valid_patch` | generic feedback | same useful Patch accepted without decision-level conflict graph |
| `targeted_irrelevant_patch` | targeted component authorization | unrelated path-score Patch rejected before executor; one evaluation |
| `generic_irrelevant_patch` | generic all-component authorization | unrelated Patch executed; still infeasible after two evaluations |
| `repair_enabled` | repair actions on | bounded backtracking recovers the initial greedy dead end |
| `repair_disabled` | repair actions off | identical DSL remains a rejected partial plan |
| `counterexample_memory_disabled` | memory off | no counterexample summary, archive, or replay queue |
| `no_feedback_fixed_patch` | verifier feedback removed | Prompt has no violations, conflict graph, or counterexample summary |
| `feasible_masks_enabled` | construction masks on | identical no-repair DSL constructs a verified plan |
| `feasible_masks_disabled` | construction masks off | all-node candidate space produces an eligibility violation rejected by verifier |

The suite is defined in `configs/experiments/ablation_control_suite.yaml` and
persisted as `artifacts/reports/ablation_control_suite.json`. Replay responses
are fixed, so this suite supports causal implementation checks but cannot show
that conflict feedback improves a live model's average repair rate.

## Remaining empirical work

A separate `configs/experiments/method_completion_suite.yaml` now isolates
memory-without-replay vs replay after a failed repair, fixed single-start vs
typed LLM multi-start, and mask on/off across six offline variants. The
multi-start path records initial, Patch, and total LLM calls under one gate.
`configs/experiments/counterexample_replay_campaign.yaml` additionally proves
that a full failed scenario and eligible parent DSL are consumed by a later,
independent search run. These are mechanism checks only and do not alter the
frozen ten-variant suite above.

- Run paired live-model trials with locked scenarios, seeds, call budgets, and
  response cache.
- Report feasible rate, calls to first feasible, schema/authorization failures,
  objective, tokens, latency, and confidence intervals.
- Add no-diversity and alternative replay-order variants after their comparison
  contracts are fixed; no-feedback, no-mask, replay, and multi-start now affect
  the actual Prompt/executor/controller path.
