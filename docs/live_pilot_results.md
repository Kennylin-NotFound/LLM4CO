# DeepSeek COVER-Opt Live Pilot Results

## Evidence status

Both pilot runs are diagnostic and not claim eligible. They validate the live
method interface, typed Patch path, deterministic verifier loop, model lock,
usage accounting and failure recording on five bounded static instances. They
do not establish average performance, cross-constraint generalization or
superiority over a baseline.

## Frozen controls

- Stage: `live_pilot`, seeds 100-104, one model repetition
- Model: `deepseek-v4-pro`
- System fingerprint: `a307abda487cd1b463329ccb945ce396`
- Prompt hash: `50946a993beb969645254054cdff3faae5508b0634a120d3a7075c91fd78b0db`
- Protocol hash: `d078fd0c8fc5268ac4bcf50ee9dcfe836902295a6fceecba35210e53bdff30dd`
- Budget per case: four Patch proposals and five evaluator calls

## Run summaries

| Run | Feasible | LLM calls | Evaluator calls | Schema/backend failures | Billed tokens (in/out) | Estimated cost |
|---|---:|---:|---:|---:|---:|---:|
| v1, before semantic-retry fix | 4/5 | 7 | 8 | 0/0 | 8541/315 | CNY 0.027513 |
| v2, after semantic-retry fix | 5/5 | 4 | 9 | 0/0 | 8577/320 | CNY 0.027651 |

The v1 artifact hash is
`7c1e82ff68e63ff587b988319876513490559f4520a1a9f829048a1b4019d9d5`.
The v2 artifact hash is
`aa7bf7b44bd824bb534083989e134816d8a5cdc32e22d63a6fd8dbf954da3f59`.

## Failure analysis and method change

For seed 104 in v1, the model returned a schema-valid
`set_weight(node_score, migration_penalty, -1.0)` Patch. The parent DSL did not
contain that feature, so the authorized Patch applier correctly rejected the
operation. Because the unchanged refinement context produced the same request
fingerprint, three later attempts replayed the cached invalid response and
exhausted the Patch budget.

The controller now records typed semantic-rejection feedback containing the
Patch signature, payload, errors and occurrence count. The next model request
receives this bounded history, and a stable Patch signature prevents an already
rejected Patch from reaching the applier twice. Integration tests cover both
recovery after one semantic rejection and duplicate interception.

All four nontrivial v2 cases produced
`add_term(node_score, migration_penalty, -1.0)` on their first request and
became verifier-approved after one evaluator call. Therefore the new retry path
was not activated in v2. The 4/5 to 5/5 difference cannot be attributed
causally to semantic-rejection feedback; the mechanism is supported by the
deterministic regression tests, while v2 only confirms that the revised live
pipeline remains operational.

## Gate decision

The pilot passes the interface-stability gate and permits construction of the
paired-final harness. Claim-eligible live runs remain blocked until all of the
following pass offline preflight:

1. deterministic multi-constraint scenario generation for all frozen seeds;
2. one uniform result schema and budget enforcement across every compared method;
3. live-capable adapters for each LLM baseline and COVER-Opt ablation;
4. complete artifact, failure-ledger and cost-forecast checks.

