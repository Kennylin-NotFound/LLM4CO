Generate one deployment plan for the supplied scenario. Return exactly one JSON
object matching StructuredPlanArtifact. Bind the output to the supplied
`scenario_id` and `scenario_hash`. Do not include markdown or prose outside the
JSON object. This is a one-shot baseline: there is no feedback, search, repair,
or second attempt.

SCENARIO_JSON:
{{SCENARIO_JSON}}

STRUCTURED_PLAN_ARTIFACT_SCHEMA:
{{ARTIFACT_SCHEMA_JSON}}
