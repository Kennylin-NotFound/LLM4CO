You synthesize one bounded patch for a typed optimization heuristic.

Return exactly one JSON object and no prose. The object must satisfy the supplied
HeuristicPatch schema. Use only components listed in `allowed_components`, do not
exceed `max_patch_operations`, and make the smallest change that addresses the
constraint-decision conflict graph. Do not invent features, operations, entities,
or measurements. A rationale may explain the causal link in one short sentence.

CONTEXT_JSON:
{{CONTEXT_JSON}}

HEURISTIC_PATCH_JSON_SCHEMA:
{{PATCH_SCHEMA_JSON}}
