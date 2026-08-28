You synthesize one bounded mutation for a typed optimization heuristic.

Return exactly one JSON object and no prose. The object must satisfy the supplied
HeuristicPatch schema. The parent plan is verifier-approved. Propose the
smallest testable change that may reduce `weighted_objective` while preserving
all hard constraints.

Base the hypothesis on observed evidence, not generic optimization advice:

- use `current_weighted_contributions` to identify the dominant objective term;
- use `execution_summary.latency_breakdown` to locate processing or communication cost;
- use `execution_summary.decision_trace` to see which candidate features and scores caused each selected decision;
- account for the fact that every weighted-score component selects the largest score.

Use `patch_affordances` as the authoritative operation precondition. Apply
`set_weight` or `remove_term` only to an existing term and `add_term` only to an
absent term. Never use an operation target listed in `blocked_operator_targets`;
those targets have exhausted their local search allowance after repeated
non-improvement. Use only `allowed_components`; do not invent features,
operations, entities or measurements.

Treat `previous_objective_evaluations` as experimental feedback. Never repeat an
earlier non-improving operation set. If an earlier mutation worsened or did not
change the objective, revise the causal direction or explore another supported,
unblocked feature. Do not claim improvement before deterministic evaluation. A
rationale may state one short hypothesis.

CONTEXT_JSON:
{{CONTEXT_JSON}}

HEURISTIC_PATCH_JSON_SCHEMA:
{{PATCH_SCHEMA_JSON}}
