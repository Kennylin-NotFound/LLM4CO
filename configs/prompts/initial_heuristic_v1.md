You are synthesizing one bounded, interpretable heuristic for a deterministic
microservice deployment solver. Return exactly one JSON object that conforms to
the supplied schema. Do not return Python, prose, a deployment plan, or fields
outside the schema.

The deterministic executor applies the heuristic in four stages:
1. order services by a weighted score;
2. choose the feasible node with the largest weighted score;
3. choose the feasible path with the largest weighted score;
4. apply only the listed bounded repair actions.

Use only features and actions in the operator catalog. Keep each weighted rule
small, use finite weights, and vary the design from other proposals by focusing
on the scenario and objective rather than inventing unsupported operators.

Proposal index: {{PROPOSAL_INDEX}}

Scenario:
{{SCENARIO_JSON}}

Operator catalog:
{{OPERATOR_CATALOG_JSON}}

Required JSON schema:
{{DSL_SCHEMA_JSON}}
