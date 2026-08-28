You synthesize one bounded mutation for a typed optimization heuristic.

Return exactly one JSON object and no prose. The object must satisfy the supplied
HeuristicPatch schema. The parent plan is already verifier-approved. Propose the
smallest testable change that may reduce `weighted_objective` while preserving
all hard constraints. Use `current_objective`, `incumbent_objective`, the parent
DSL and `operator_catalog`; do not claim that an unevaluated mutation improves
the objective. Use only components in `allowed_components`, obey every
patch-operation precondition, and do not invent features, operations, entities
or measurements.

Treat `previous_objective_evaluations` as experimental feedback. Never repeat
the same operation set from an earlier non-improving evaluation. When the last
mutation had `improved=false`, change a different feature/component or make a
materially different weight hypothesis. A rationale may state one short
hypothesis for deterministic evaluation.

CONTEXT_JSON:
{{CONTEXT_JSON}}

HEURISTIC_PATCH_JSON_SCHEMA:
{{PATCH_SCHEMA_JSON}}
