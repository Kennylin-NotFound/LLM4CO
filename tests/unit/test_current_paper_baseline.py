from pathlib import Path

import pytest

from cover_opt.baselines.code_runner import (
    ReplaySolverCodeRunner,
    SolverRunnerReplayMiss,
)
from cover_opt.baselines.current_paper import (
    CurrentPaperSolverGenBaseline,
    SolverGenerationBudgets,
)
from cover_opt.baselines.models import GeneratedSolverArtifact
from cover_opt.llm.replay import ReplayLLM
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_baseline() -> CurrentPaperSolverGenBaseline:
    return CurrentPaperSolverGenBaseline(
        llm=ReplayLLM.from_file(
            PROJECT_ROOT / "tests/fixtures/llm/replay_current_paper_solvergen.json"
        ),
        runner=ReplaySolverCodeRunner.from_file(
            PROJECT_ROOT
            / "tests/fixtures/solver_runner/replay_current_paper_execution.json"
        ),
        generation_template=(
            PROJECT_ROOT / "configs/prompts/current_paper_solver_generation.md"
        ).read_text(encoding="utf-8"),
        correction_template=(
            PROJECT_ROOT / "configs/prompts/current_paper_solver_correction.md"
        ).read_text(encoding="utf-8"),
    )


def artifact(iteration: int) -> GeneratedSolverArtifact:
    return GeneratedSolverArtifact.model_validate(
        {
            "iteration": iteration,
            "solver_backend": "gurobi_mip",
            "formulation": {
                "parameters": ["nodes"],
                "variables": ["x"],
                "constraints": ["unique placement"],
                "objective": "latency",
            },
            "code": "def solve(): pass",
        }
    )


def test_replay_code_runner_never_executes_and_checks_iteration() -> None:
    runner = ReplaySolverCodeRunner(
        [
            {
                "expected_iteration": 1,
                "attempt": 0,
                "status": "execution_error",
                "error_type": "syntax",
                "message": "fixture",
                "solver_status": "compile_failed",
            }
        ]
    )

    assert runner.safe_mode == "replay_only_no_code_execution"
    with pytest.raises(SolverRunnerReplayMiss, match="iteration mismatch"):
        runner.execute(artifact(0))


def test_solver_generation_budget_stops_before_successful_third_revision() -> None:
    result = make_baseline().run(
        scenario=load_scenario(
            PROJECT_ROOT / "configs/scenarios/small_static.yaml"
        ),
        budgets=SolverGenerationBudgets(
            max_llm_calls=2,
            max_execution_attempts=2,
            max_evaluator_calls=1,
        ),
    )

    assert result.status == "budget_exhausted"
    assert result.stop_reason == "llm_call_budget"
    assert result.solver_result is None
    assert result.statistics.llm_calls == 2
    assert [item.feedback_category for item in result.trajectory] == [
        "execution_error",
        "modeling_error",
    ]
