Reconstruct the paper's solver-generation workflow for the supplied deployment
instance. Extract parameters, variables, constraints, and objective (P/V/C/O),
then emit Python solver code using a MIP-style backend.

Return exactly one JSON object matching GeneratedSolverArtifact. Do not include
markdown or prose outside the JSON object.

SCENARIO_JSON:
{{SCENARIO_JSON}}

GENERATED_SOLVER_ARTIFACT_SCHEMA:
{{ARTIFACT_SCHEMA_JSON}}
