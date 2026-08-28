# DeepSeek COVER-Opt Live Pilot Protocol

## Purpose

The live pilot is a diagnostic gate between single-case smoke tests and the
claim-eligible paired final experiment. It checks whether the frozen Prompt,
typed Patch path, verifier loop, artifact schema, token accounting and cost
controls remain stable across five distinct instances. Pilot results cannot
support paper, resume, or interview performance claims.

## Bounded static pilot scenarios

Seeds 100-104 are mapped to five deterministic perturbations of
`small_static.yaml`. Each case varies compute rate, link rate/bandwidth,
distance, workload and data volume within fixed narrow ranges. Each also uses a
different eligibility/capacity-valid previous placement and a zero migration
budget. This creates distinct deployment instances while keeping the diagnostic
focus on verifier-guided placement repair.

These fixtures are not calibrated orbital or network simulations. Their only
purpose is method-interface testing under controlled instance variation.

## Frozen controls

- Prompt SHA-256: `50946a993beb969645254054cdff3faae5508b0634a120d3a7075c91fd78b0db`
- Model: `deepseek-v4-pro`
- System fingerprint: `a307abda487cd1b463329ccb945ce396`
- Thinking: disabled; temperature 0; top-p 1
- Per case: at most 4 Patch proposals and 5 evaluator calls
- Stage: exactly one model repetition for seeds 100-104
- Worst-case preflight cost cap: CNY 1.0

## Reported diagnostics

The runner records per-case scenario and hash, initial/final violation classes,
feasibility, calls to first feasible, schema/backend failures, local cache hits,
billed tokens, estimated cost, semantic Patch rejections, duplicate interception,
observed model fingerprints, full LLM trace and full search trajectory. The
aggregate reports feasible rate and efficiency only as pilot diagnostics.
