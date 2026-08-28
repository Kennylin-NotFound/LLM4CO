# Static COVER-Opt Method MVP Status

This document maps the method design to code and current evidence. It is an
implementation-status record, not a paper-results section.

| Method element | Code | Current evidence | Status boundary |
|---|---|---|---|
| Typed heuristic DSL | `heuristics/schema.py` | enum features, strict schema, no extra fields | implemented |
| DSL static verification | `heuristics/static_verifier.py` | unknown/duplicate/zero rules rejected; stable AST hash | implemented and unit-tested |
| Deterministic execution skeleton | `heuristics/executor.py` | topology-compatible service order, eligibility/capacity masks, path masks and trace | implemented and unit-tested |
| Shared plan verifier | `verifier/plan_verifier.py` | seven violation classes with decision attribution | implemented and fixture-tested |
| Feasible-only objective | `objective/evaluator.py` | infeasible plans rejected before scoring | implemented and fixture-tested |
| Constraint-decision conflict graph | `verifier/conflict_graph.py` | stable bipartite graph and component authorization | implemented and unit-tested |
| Typed authorized patch | `heuristics/patch.py` | transactional apply, scope check, final DSL verification | implemented and unit-tested |
| Bounded search controller | `search/controller.py` | evaluator/patch/time budgets, archive, stop reason and trajectory | implemented and integration-tested |
| Scripted counterexample repair | `configs/experiments/method_smoke.yaml` | one migration violation repaired in one authorized patch | control-flow evidence only |
| Structural diversity | `search/diversity.py`, `search/archive.py` | normalized component distance and deterministic farthest-first feasible selection | implemented and unit-tested |
| Counterexample archive and consumed replay | `search/counterexamples.py`, `search/replay.py`, `search/archive.py`, `search/controller.py` | pattern aggregation, bounded replay, repairable-parent selection and trace | implemented and controller-tested |
| Typed multi-start initialization | `llm/heuristic_generator.py`, `search/controller.py` | full DSL schema/static validation, deduplication, evaluator budget and deterministic selection | implemented and offline-controlled |
| Offline LLM Typed Patch boundary | `llm/patch_generator.py` | versioned prompt, strict schema parse, Mock/Replay integration and failure trace | implemented and integration-tested |
| Replay method smoke | `configs/experiments/replay_method_smoke.yaml` | recorded LLM response reproduces one authorized repair through the full loop | replay control-flow evidence only |
| Deterministic repair actions | `heuristics/repair.py` | reroute, repeated move, feasible swap and bounded backtracking with one shared attempt budget | implemented and unit-tested |
| Multi-counterexample regression replay | `search/regression.py`, `configs/experiments/regression_replay_suite.yaml` | two typed Patch mechanisms, three violation classes, per-case contracts and aggregate replay queue | implemented and integration-tested |
| Shared baseline/oracle interface | `evaluation/solvers.py`, `configs/experiments/baseline_smoke.yaml` | seeded Random, two no-repair Greedy baselines and exact enumeration over the bounded candidate set | implemented and integration-tested |
| Executable control ablations | `search/options.py`, `evaluation/ablation.py` | no/generic/targeted feedback, masks on/off, repair on/off and memory on/off across ten fixed variants | implemented and integration-tested |
| Reconstructed CurrentPaper-SolverGen | `baselines/current_paper.py`, `baselines/code_runner.py` | generation, execution-error correction, modeling-error correction and shared verification | replay-only control-flow evidence |
| One-shot LLM plan baselines | `baselines/llm_plan.py`, `configs/experiments/llm_plan_replay_suite.yaml` | Direct semantic failure, Structured scenario binding and shared verification under one-call contracts | replay-only control-flow evidence |
| Frozen formal experiment protocol | `evaluation/protocol.py`, `configs/experiments/formal_experiment_protocol.yaml` | paired stages, model lock, budgets, metrics, statistics, artifacts and five claim gates | implemented; live calls remain gated |
| Objective-aware hybrid search | `search/controller.py`, `search/refiner.py`, `search/probes.py` | feasible-parent objective context, incumbent rollback, stagnation gate and deterministic component-weight neighborhood | implemented and tested; single live smoke only |

## Method smoke trace

The scripted smoke intentionally creates a zero-migration-budget
counterexample. The initial latency-first DSL changes two placements and is
classified as `repairable`. The conflict graph permits `node_score` and
`repair_policy`. A scripted patch adds `migration_penalty` with weight `-10`,
after which the deterministic executor restores the previous placement and the
shared verifier marks the plan feasible.

This demonstrates typed feedback, authorization, re-execution, verification,
archive transition, and bounded termination. It does not demonstrate that an
LLM can discover the patch or that COVER-Opt outperforms a baseline.

## Deliberately incomplete

- `repair_policy` has deterministic bounded semantics for all four actions; broader scenarios and action-level ablations are not run yet.
- Structural-diversity scoring and post-selection are implemented; full batch-level multi-parent evolution remains pending.
- Counterexample frequency, repair-failure priority, scenario-batch loading and regression replay execution are implemented; the current suite has only two synthetic method fixtures.
- DeepSeek live generation, response cache, fingerprint gate, feasibility pilot and one objective-refinement smoke are implemented; cross-seed live performance remains pending.
- CP-SAT backend, executable sandboxed SolverGen runner, paper-scale scenario reconstruction, live-model ablations and statistical experiments remain pending.
