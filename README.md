# COVER-Opt Implementation

This directory contains the reproducible implementation of COVER-Opt. The
current delivery is a complete controlled prototype: a deterministic problem
kernel, typed heuristic DSL, constraint verifier, conflict-directed patch
boundary, structural candidate archive, failure-triggered replay scheduler,
cross-run replay campaign, bounded search controller, live provider adapter,
and resumable experiment harness.

## Current capabilities

- Strict schemas for scenarios, plans, violations, heuristic metadata, and run manifests.
- YAML-backed experiment and scenario configuration.
- Provider-independent LLM protocol with deterministic mock and offline replay backends.
- Run artifact store with request, response, result, and manifest persistence.
- CLI commands for contract validation, offline smoke runs, and manifest inspection.
- Deterministic service-DAG completion-time evaluation and K-shortest routing.
- Simplified, reproducible Walker Delta time-slot scenario generation.
- Seven-class hard-constraint verification, shared-link bandwidth aggregation, explicit exact/proxy attribution, and feasible-only objective evaluation.
- Typed DSL validation, deterministic execution, conflict graphs, feature/action-authorized patches, structural diversity, archive-backed counterexample replay, and budgeted search.
- Optional full typed-DSL LLM initialization with static validation, deduplication, and deterministic multi-start selection.
- Unified LLM-call accounting across typed initialization and Patch generation,
  with one total call gate in the search result.
- Versioned conflict-patch prompt with strict `HeuristicPatch` parsing through Mock and Replay LLM backends.
- Verifier-guided bounded repair actions for rerouting, service moves, swaps, and capacity-pruned backtracking.
- Contract-based multi-counterexample regression replay with aggregate violation coverage and replay priority.
- Shared Random/Greedy/Exact solver result contract and a bounded small-instance enumeration oracle.
- Real feature switches and a ten-variant offline control-ablation suite,
  including no-feedback and no-feasible-mask execution paths.
- A separate six-variant method-completion suite isolating replay, multi-start,
  and feasible-mask behavior without changing the frozen historical suite.
- A configured cross-run replay campaign that persists the failed scenario,
  eligible parent DSL, counterexample state, replay trajectory, and budgets.
- Replay-only reconstruction of the paper's solver-generation and classified self-correction loop.
- One-shot DirectLLMPlan and scenario-bound StructuredLLMPlan replay baselines.
- Machine-validated formal experiment protocol with live-call, budget, metric,
  artifact, statistical, and claim-upgrade gates.
- DeepSeek V4 Pro ChatCompletions adapter with strict JSON parsing, bounded
  retries, local response cache, API-key isolation, and fingerprint drift checks.
- Frozen v1.3 paired-final scenario profiles, exact-oracle preflight, per-run
  artifact resumption, cost accounting, scenario-level paired statistics, and
  automatic claim gates.
- Outcome-aware rejection and rollback for patches that change the AST but do
  not improve placement, routes, or the violation profile, plus bounded
  counterfactual probes during feasibility refinement.
- A bounded interview demo that runs offline by default and produces a compact
  evidence summary without API cost.

The candidate emitted by the Phase 1 smoke flow is explicitly marked as an
unvalidated stub. It is not a working heuristic DSL and is not research
evidence for solution quality.

## Run locally

```powershell
python -m pip install -e .
python -m pytest
python -m cover_opt validate-contract --contract research_contract.yaml
python -m cover_opt generate-walker --config configs/scenarios/walker_dynamic.yaml --time-slot 0 --output artifacts/reports/walker_slot_0000.json
python -m cover_opt simulate-static --scenario configs/scenarios/small_static.yaml --placement configs/placements/small_static_previous.yaml --output artifacts/reports/small_static_result.json
python -m cover_opt run-scripted-search --config configs/experiments/method_smoke.yaml --output artifacts/reports/method_smoke.json
python -m cover_opt run-replay-search --config configs/experiments/replay_method_smoke.yaml --output artifacts/reports/replay_method_smoke.json
python -m cover_opt run-regression-replay --config configs/experiments/regression_replay_suite.yaml --output artifacts/reports/regression_replay_suite.json
python -m cover_opt run-baseline-smoke --config configs/experiments/baseline_smoke.yaml --output artifacts/reports/baseline_smoke.json
python -m cover_opt run-ablation-suite --config configs/experiments/ablation_control_suite.yaml --output artifacts/reports/ablation_control_suite.json
python -m cover_opt run-ablation-suite --config configs/experiments/method_completion_suite.yaml --output artifacts/reports/method_completion_suite.json
python -m cover_opt run-counterexample-replay-campaign --config configs/experiments/counterexample_replay_campaign.yaml --output artifacts/reports/counterexample_replay_campaign.json
python -m cover_opt run-current-paper-replay --config configs/experiments/current_paper_replay.yaml --output artifacts/reports/current_paper_replay.json
python -m cover_opt run-llm-plan-replay-suite --config configs/experiments/llm_plan_replay_suite.yaml --output artifacts/reports/llm_plan_replay_suite.json
python -m cover_opt validate-experiment-protocol --protocol configs/experiments/formal_experiment_protocol.yaml
python -m cover_opt run-deepseek-structured-smoke --config configs/experiments/deepseek_v4pro_structured_smoke.yaml --output artifacts/reports/deepseek_v4pro_structured_smoke.json
python -m cover_opt run-deepseek-search-smoke --config configs/experiments/deepseek_v4pro_search_smoke.yaml --output artifacts/reports/deepseek_v4pro_search_smoke_v2.json
python -m cover_opt preflight-paired-final --config configs/experiments/deepseek_v4pro_paired_final_v1_3.yaml --output artifacts/paired_final_v1_3/preflight.json
python -m cover_opt run-deepseek-paired-final --config configs/experiments/deepseek_v4pro_paired_final_v1_3.yaml --preflight artifacts/paired_final_v1_3/preflight.json
python -m cover_opt analyze-paired-final --protocol configs/experiments/formal_experiment_protocol.yaml --artifacts-root artifacts/paired_final_v1_3 --output artifacts/paired_final_v1_3/analysis.json --markdown-output artifacts/paired_final_v1_3/results.md
python -m cover_opt run-offline --config configs/experiments/offline_smoke.yaml --llm mock
python -m cover_opt run-offline --config configs/experiments/offline_smoke.yaml --llm replay --replay-file tests/fixtures/llm/replay_offline_smoke.json
```

For the shortest end-to-end interview demo, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1
powershell -ExecutionPolicy Bypass -File scripts/run_interview_demo.ps1 -Verify
```

The optional `-Live` switch runs one bounded DeepSeek method smoke. It is not a
performance experiment and reads `DEEPSEEK_API_KEY` only from the process or
Windows User environment.

Each offline run writes an immutable directory under `artifacts/runs/` with a
manifest and LLM trace. Later phases will extend the same contracts instead of
creating a separate experiment path.

## Evidence boundary

- Implemented and tested: schema validation, hashing, manifests, mock/replay,
  deterministic routing/latency, PlanVerifier, typed DSL, conflict-directed
  patches, structural-diversity selection, consumed counterexample replay with
  archive parent selection, failed-scenario campaign replay, typed multi-start
  initialization with unified LLM-call accounting,
  strict offline LLM Patch generation, bounded repair actions, bounded search,
  one-shot plan baselines, real no-feedback/no-mask paths, and a frozen formal
  experiment contract, DeepSeek V4 Pro live adapter, five-seed pilot, objective
  refinement, paired-final preflight/runner/statistics, and outcome-aware
  rejection with feasibility probes.
- v1.3 completed 440/440 run artifacts with no infrastructure failures, but all
  four preregistered primary claims were not supported. Do not describe the
  controlled results as a significant performance improvement.
- v1.4 holdout was paused after 196 run artifacts to keep the current delivery
  bounded. It has no final manifest or analysis and is diagnostic evidence only.
- Deferred: CP-SAT, sandboxed generated-code execution, paper-scale scenario
  reconstruction, complete dynamic episodes, production Kubernetes integration,
  and LLM training.
- See `docs/system_completion_status.md` and
  `docs/v1_4_partial_holdout_status.md` for the current delivery boundary.
- Chinese acceptance and interview materials are available at
  `../06_技术岗位面试支撑材料.md`,
  `docs/audit/07_完整管线与方法论验收说明.md`, and
  `docs/planning/08_后续研究TODO与实验重启指南.md`.
