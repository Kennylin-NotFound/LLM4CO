# Objective Refinement and Hybrid Search Status

## Why this stage was added

The original controller stopped at the first verifier-approved plan. That path
supported feasibility repair but did not yet implement the paper's central
optimization claim. The revised controller separates two phases:

1. **Feasibility refinement:** conflict-directed Typed Patches repair hard
   constraint violations.
2. **Objective refinement:** a feasible parent receives objective contribution,
   DAG latency, execution-decision and Patch-affordance feedback; every child is
   reverified before it can enter the feasible archive.

## Hybrid search mechanism

The LLM proposes a bounded structural Patch inside an authorized DSL component.
The deterministic controller then:

- records semantic Patch rejection and objective delta;
- rolls back to the incumbent after non-improvement;
- deduplicates operation-equivalent Patches even when rationale text differs;
- blocks an operator target after repeated non-improvement;
- expands an LLM-selected weighted-score component into a bounded sign-flip
  neighborhood while evaluator budget remains;
- retains only verifier-approved candidates for objective comparison.

This division makes the LLM responsible for structural search and the
deterministic kernel responsible for typed numeric probes, verification and
selection. It does not rely on the model to guess a precise scalar weight.

## Live diagnostic evidence

Early non-thinking smokes produced valid but non-improving mutations. A
thinking-enabled run exhausted `max_tokens=2048` before JSON output on three
attempts and hit the wall-time gate, so thinking mode is not eligible under the
current request budget.

The final hybrid smoke used `deepseek-v4-pro`, non-thinking mode, the locked
system fingerprint and the same limit of four LLM proposals/five evaluator
calls. It completed with:

| Item | Result |
|---|---:|
| Actual LLM calls | 2 |
| Deterministic numeric probes | 2 |
| Evaluator calls including initial plan | 5 |
| Initial weighted objective | 109.241524 |
| Best weighted objective | 94.291421 |
| Absolute improvement | 14.950103 |
| Schema/backend failures | 0 / 0 |
| Billed input/output tokens | 7925 / 190 |

`candidate_001_probe_02` placed all three services on `sat-b`, remained feasible
under the shared verifier and matched the exact-enumeration oracle's best plan
within the 33-candidate bounded set. Artifact:
`artifacts/reports/deepseek_v4pro_objective_smoke_v9_hybrid.json`, SHA-256
`c87fb2a5257923512cb5867e206b6202005ea1684cf2a222e44d03cf9f0b0e6c`.

## Evidence boundary

This is one synthetic small-instance diagnostic. It proves that the hybrid
control path can improve an already feasible plan and recover the bounded-set
oracle plan in this case. It does not establish an average improvement,
generalization, global optimality, or superiority over a baseline. Those claims
remain blocked on the preregistered paired-final experiment.

