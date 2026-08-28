# One-Shot LLM Plan Baseline Status

`DirectLLMPlan` and `StructuredLLMPlan` isolate plan-generation behavior from
COVER-Opt search. Each method receives one scenario, makes exactly one LLM
call, emits one plan, and then uses the same `PlanVerifier` and
`ObjectiveEvaluator` as every other solver. Neither baseline receives feedback,
Typed Patch generation, candidate search, counterexample memory, or repair.

## Contract difference

- `DirectLLMPlan` returns only `placement` and `routes`. It has no scenario
  identity binding.
- `StructuredLLMPlan` returns a versioned artifact containing `scenario_id` and
  `scenario_hash`; stale or cross-scenario output is rejected before plan
  verification.

The replay suite intentionally stores an ineligible Direct placement and a
valid Structured placement. This proves that schema success and semantic
feasibility are separate states and that the shared verifier remains the final
authority. It does not prove StructuredLLMPlan performs better on a live model.

Artifact: `artifacts/reports/llm_plan_replay_suite.json`.
