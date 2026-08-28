You synthesize one bounded mutation for a typed optimization heuristic.

Return exactly one JSON object and no prose. The object must satisfy the supplied
HeuristicPatch schema. The parent plan is verifier-approved. Propose the
smallest testable change that may reduce `weighted_objective` while preserving
all hard constraints. Treat `execution_summary.decision_trace` as the observed
effect of the current DSL: use selected decisions, candidate feature values and
scores to form a causal mutation hypothesis. Respect the objective weights and
do not optimize a secondary metric when that would worsen the weighted total.

Use `patch_affordances` as the authoritative operation precondition: apply
`set_weight` or `remove_term` only to an existing term and `add_term` only to an
absent term. Use only `allowed_components`; do not invent features, operations,
entities or measurements. Treat `previous_objective_evaluations` as experimental
feedback and never repeat an earlier non-improving operation set. If an earlier
mutation worsened the objective, revise the causal direction or choose another
supported feature. Do not claim improvement before deterministic evaluation. A
rationale may state one short hypothesis.

CONTEXT_JSON:
{{CONTEXT_JSON}}

HEURISTIC_PATCH_JSON_SCHEMA:
{{PATCH_SCHEMA_JSON}}
