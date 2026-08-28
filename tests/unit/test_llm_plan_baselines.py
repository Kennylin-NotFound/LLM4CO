from pathlib import Path

from cover_opt.baselines.llm_plan import (
    DirectLLMPlanBaseline,
    StructuredLLMPlanBaseline,
)
from cover_opt.domain.models import ViolationType
from cover_opt.llm.replay import ReplayLLM
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO = PROJECT_ROOT / "configs/scenarios/small_static.yaml"


def test_direct_plan_is_semantically_checked_by_shared_verifier() -> None:
    baseline = DirectLLMPlanBaseline.from_template_file(
        llm=ReplayLLM.from_file(
            PROJECT_ROOT / "tests/fixtures/llm/replay_direct_llm_plan.json"
        ),
        path=PROJECT_ROOT / "configs/prompts/direct_llm_plan.md",
    )

    result = baseline.run(load_scenario(SCENARIO))

    assert result.status == "infeasible"
    assert result.stop_reason == "infeasible_plan"
    assert result.llm_calls == 1
    assert result.solver_result is not None
    assert result.solver_result.verification is not None
    assert ViolationType.NODE_ELIGIBILITY in {
        item.violation_type for item in result.solver_result.verification.violations
    }
    assert result.solver_result.objective is None


def test_structured_plan_is_bound_to_scenario_and_verified() -> None:
    scenario = load_scenario(SCENARIO)
    baseline = StructuredLLMPlanBaseline.from_template_file(
        llm=ReplayLLM.from_file(
            PROJECT_ROOT / "tests/fixtures/llm/replay_structured_llm_plan.json"
        ),
        path=PROJECT_ROOT / "configs/prompts/structured_llm_plan.md",
    )

    result = baseline.run(scenario)

    assert result.status == "feasible"
    assert result.stop_reason == "verified_plan"
    assert result.solver_result is not None
    assert result.solver_result.verification is not None
    assert result.solver_result.verification.feasible is True
    assert result.solver_result.objective is not None
    assert result.solver_result.optimality_proven is False
    assert result.trajectory[0].artifact["scenario_hash"] == scenario.stable_hash


def test_structured_plan_rejects_stale_scenario_hash_before_verification() -> None:
    scenario = load_scenario(SCENARIO)
    llm = ReplayLLM(
        [
            {
                "purpose": "structured_llm_plan",
                "parsed": {
                    "schema_version": "1.0.0",
                    "scenario_id": scenario.scenario_id,
                    "scenario_hash": "stale",
                    "placement": {"ingest": "sat-a"},
                    "routes": [],
                },
            }
        ]
    )
    baseline = StructuredLLMPlanBaseline.from_template_file(
        llm=llm,
        path=PROJECT_ROOT / "configs/prompts/structured_llm_plan.md",
    )

    result = baseline.run(scenario)

    assert result.status == "generation_error"
    assert result.stop_reason == "scenario_mismatch"
    assert result.solver_result is None
    assert result.trajectory[0].generation_status == "scenario_mismatch"
