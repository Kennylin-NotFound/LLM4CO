# DeepSeek V4 Pro Live Smoke Status

## Interface decision

The official model identifier is `deepseek-v4-pro`. COVER-Opt uses the
OpenAI-compatible `POST /chat/completions` endpoint because V4 Pro is supported
there, while DeepSeek's Responses API currently documents V4 Flash only.
Structured output uses `response_format={"type":"json_object"}` and an explicit
JSON instruction. The smoke uses non-thinking mode so `temperature=0` remains
effective and output parsing is isolated from reasoning-mode behavior.

Official references:

- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/guides/json_mode
- https://api-docs.deepseek.com/guides/thinking_mode

## Observed live results

| Run | Result | Input/output tokens | Technical observation |
|---|---|---:|---|
| StructuredPlan smoke | feasible, verified | 1018 / 168 | model, JSON, schema version, scenario hash and shared verifier path all worked |
| Conflict search v1 | infeasible after accepted Patch | 1663 / 73 | model changed `repair_policy` to `reroute`; this did not affect placement or migration count |
| Conflict search v2 | first feasible after one Patch | 2078 / 76 | operator catalog exposed feature semantics; model added `node_score.migration_penalty=-1.0` |

All three responses reported model `deepseek-v4-pro` and system fingerprint
`a307abda487cd1b463329ccb945ce396`. At the official CNY V4 Pro rates observed on
2026-08-25, the three cache-miss calls cost approximately CNY 0.016 in total.

## What the failure changed

The v1 failure exposed a method-interface defect: the Prompt prohibited invented
features but did not enumerate the valid feature/operator semantics. The model
therefore selected an authorized and schema-valid operation with the wrong
causal effect. `RefinementContext.operator_catalog` and
`conflict_patch_v2.md` now define component effects, available features, score
direction, repair semantics and patch preconditions. The original negative
artifact remains preserved.

## Evidence boundary

These are three bounded smoke calls on one synthetic fixture. They establish
live API compatibility, structured parsing, an informative failure mode, Prompt
repair, and one successful verifier-guided transition. They do not estimate
average feasible rate, objective improvement, robustness, or superiority over
any baseline.

Artifacts:

- `artifacts/reports/deepseek_v4pro_structured_smoke.json`
- `artifacts/reports/deepseek_v4pro_search_smoke.json` (preserved v1 failure)
- `artifacts/reports/deepseek_v4pro_search_smoke_v2.json`
