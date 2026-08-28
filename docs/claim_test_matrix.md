# Claim-to-Test Matrix

All claim states begin as `planned`. A claim can become `implemented` only when
the referenced code and tests exist, and `supported` only when locked run
artifacts contain the required experiment evidence.

| Claim | Mechanism | Code owner | Gate test | Required experiment | Current state |
|---|---|---|---|---|---|
| Reproducible execution foundation | strict schemas, stable hashes, manifest and replay | `domain/`, `storage/`, `llm/` | Phase 1 unit and integration tests | repeated offline smoke run | implemented, not a paper result |
| Typed search reduces generation failures | typed heuristic AST and static verifier | `heuristics/` | Gate B DSL rejection and deterministic execution tests | raw plan vs raw code vs DSL validity/execution comparison | implemented, experiment pending |
| Conflict feedback improves targeted repair | exact/proxy attribution plus feature/action-authorized structural patch | `verifier/violations.py`, `verifier/conflict_graph.py`, `search/refiner.py`, `evaluation/ablation.py` | multi-constraint attribution, authorization, and control-switch fixtures | generic feedback vs conflict feedback paired live-model ablation | mechanism/control ablation implemented; v1.3 did not support the performance claim |
| Counterexample replay improves search efficiency | failed-scenario archive, failure-triggered bounded replay, eligible archive parent selection, and cross-run scenario campaign | `search/counterexamples.py`, `search/replay.py`, `search/archive.py`, `search/campaign.py`, `search/controller.py` | first-attempt exclusion, rejected-parent isolation, priority, parent selection, cross-run persistence, and no-replay/replay tests | calls-to-first-feasible and objective curve | in-run and cross-run replay mechanisms implemented; efficiency experiment pending |
| Typed multi-start improves coverage or quality | bounded full-DSL generation, static verification, deduplication, deterministic initial selection, and unified LLM-call budget | `llm/heuristic_generator.py`, `search/budgets.py`, `search/controller.py` | invalid output, duplicate, shared total-call/evaluator budget, and single/multi-start controls | budget-matched single-start vs multi-start online comparison | mechanism and budget accounting implemented; performance experiment pending |
| Shared bandwidth is enforced consistently | construction-time residual capacity and full-plan per-link aggregation | `simulator/link_state.py`, `heuristics/executor.py`, `verifier/plan_verifier.py` | two-flow shared-link mask and verifier fixtures | scenario sensitivity and baseline re-evaluation | implemented as constraint semantics, not a performance claim |
| Method supports dynamic deployment trade-offs | rolling horizon, migration accounting, fallback | `simulator/dynamic.py`, `evaluation/` | dynamic episode replay tests | QoS, migration and planning-time comparison | planned |
| Reconstructed paper solver generation documents the historical flow | P/V/C/O artifact, generated code, classified correction loop | `baselines/current_paper.py`, `baselines/code_runner.py` | replay success and budget tests | excluded from live claim until an equivalent safe execution backend exists | control flow implemented, not live-comparable |
| Structured generation improves one-shot reliability | strict plan schema plus scenario ID/hash binding | `baselines/llm_plan.py` | direct semantic rejection, structured binding, stale-hash rejection | DirectLLMPlan vs StructuredLLMPlan paired live comparison | replay baselines implemented, performance experiment pending |
| Verifier feedback is causally useful | none/generic/conflict-directed Prompt paths | `search/refiner.py`, `llm/patch_generator.py` | Prompt leakage audit and fixed-patch control | no-feedback vs generic vs conflict paired live ablation | real switches implemented, performance experiment pending |
| Feasible masks reduce invalid construction | eligibility/capacity/contact-window/shared-bandwidth candidate filters | `heuristics/executor.py`, `search/options.py` | same-DSL mask on/off fixture | paired no-mask ablation with violation burden | real switch implemented, performance experiment pending |
| Final claims follow a preregistered evidence contract | model lock, paired stages, budgets, metrics, statistics and claim gates | `evaluation/protocol.py`, `evaluation/final.py`, `evaluation/statistics.py` | strict schema, scenario/oracle preflight, resume and statistics tests | 20 paired seeds x 3 LLM repetitions after model lock | v1.3 completed 440/440 runs; all four preregistered primary claims were unsupported |

## Non-claims

- A successful mock or replay run does not demonstrate optimization quality.
- Schema validity does not imply plan feasibility.
- A generated heuristic candidate is not executable until the DSL verifier and executor accept it.
- No online-model or baseline comparison can be reported from current replay artifacts.
