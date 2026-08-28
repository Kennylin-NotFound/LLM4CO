# Reconstructed CurrentPaper-SolverGen Baseline

This baseline reconstructs the control flow described in the accepted paper.
It does not claim source-code or numerical reproduction.

| Paper-described element | Reconstruction | Current boundary |
|---|---|---|
| Extract `P/V/C/O` from a problem description | strict `FormulationArtifact` in every generated artifact | replayed output; extraction quality untested |
| RAG-assisted canonical formulation | prompt contract reserves the formulation stage | original knowledge base and retrieval traces unavailable |
| Generate Python code for a MIP solver such as Gurobi | generated code and backend name are persisted | Gurobi is declared but not invoked |
| Execute code against local tests | `SolverCodeRunner` protocol | current backend is replay-only and executes no model code |
| Classify execution errors | syntax/runtime outcome and dedicated correction purpose | implemented and replay-tested |
| Classify modeling errors | infeasible/unbounded/validation outcome and dedicated correction purpose | implemented and replay-tested |
| Iterate until success or a limit | explicit LLM, execution, evaluator, and wall-time budgets | implemented and budget-tested |
| Produce final deployment | replayed placement/routes | always rechecked by shared `PlanVerifier` and evaluator |

## Representative replay

The fixed three-iteration fixture follows:

1. Initial solver artifact returns a syntax execution error.
2. Code correction executes but reports an infeasible model.
3. Modeling correction returns a deployment that passes the shared verifier.

The final plan happens to match the current small-instance oracle artifact, but
`optimality_proven` remains false because the generated code was not executed
and the replay does not measure discovery reliability.

## Missing original evidence

- Original prompts, generated solver files, code templates, and unit tests.
- Exact RAG knowledge base, retrieved contexts, iteration limit, and retry rules.
- ChatGPT-4 snapshot/settings, random seeds, Gurobi version/configuration, and raw
  execution logs.
- Full parameters needed to reproduce the 5-satellite and 48/60/72-satellite
  figures.

A future executable runner must use an isolated subprocess or container with
CPU/time/file/network limits. Arbitrary generated code must never run in the
main research process.
