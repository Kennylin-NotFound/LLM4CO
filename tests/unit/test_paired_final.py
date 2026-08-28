from __future__ import annotations

from collections import Counter
from pathlib import Path

from cover_opt.config import load_deepseek_paired_final
from cover_opt.evaluation.final import PairedFinalRunner, RunBoundLLM
from cover_opt.evaluation.protocol import load_formal_experiment_protocol
from cover_opt.evaluation.statistics import _exact_mcnemar, _holm_adjust
from cover_opt.hashing import sha256_json
from cover_opt.heuristics.handcrafted import latency_first
from cover_opt.heuristics.patch import HeuristicPatch
from cover_opt.llm.protocol import LLMRequest, LLMResponse, build_request
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.controller import SearchController
from cover_opt.search.generation import ScriptedPatchGenerator
from cover_opt.search.options import SearchFeatures
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.evaluation.final import PairedFinalScenarioFactory


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = (
    PROJECT_ROOT / "configs/experiments/deepseek_v4pro_paired_final_v1_3.yaml"
)


class RecordingLLM:
    provider = "test"
    model = "test-model"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            request_id=request.request_id,
            request_fingerprint=request.fingerprint,
            provider=self.provider,
            model=self.model,
            raw_text="{}",
            parsed={},
        )


class InvalidSchemaLLM(RecordingLLM):
    pass


def test_paired_final_preflight_covers_four_profiles_and_oracle() -> None:
    loaded = load_deepseek_paired_final(CONFIG_PATH)
    protocol = load_formal_experiment_protocol(loaded.config.protocol_path)

    result = PairedFinalRunner().preflight(
        config=loaded.config,
        protocol=protocol,
        config_hash=sha256_json(loaded.raw),
    )

    assert result.passed is True
    assert len(result.cases) == 20
    assert Counter(item.profile_id for item in result.cases) == {
        "migration_lock": 5,
        "qos_tight": 5,
        "joint_constraint": 5,
        "objective_control": 5,
    }
    assert all(item.oracle_optimality_proven for item in result.cases)
    assert result.cost_forecast.worst_case_cost_cny < 35.0


def test_run_bound_llm_separates_repetition_cache_identity() -> None:
    inner = RecordingLLM()
    first = RunBoundLLM(inner, run_key="method__s200__r0")
    second = RunBoundLLM(inner, run_key="method__s200__r1")
    request = build_request(
        purpose="test",
        prompt="same prompt",
        expected_output="object",
    )

    first.generate(request)
    second.generate(request)

    assert inner.requests[0].prompt == inner.requests[1].prompt
    assert inner.requests[0].fingerprint != inner.requests[1].fingerprint


def test_exact_mcnemar_and_holm_are_deterministic() -> None:
    p_value, treatment_only, control_only = _exact_mcnemar(
        [1.0] * 8 + [0.0] * 2,
        [0.0] * 8 + [1.0] * 2,
    )
    adjusted = _holm_adjust({"a": 0.01, "b": 0.04, "c": 0.2})

    assert treatment_only == 8
    assert control_only == 2
    assert 0.0 <= p_value <= 1.0
    assert adjusted == {"a": 0.03, "b": 0.08, "c": 0.2}


def test_paired_final_runner_materializes_and_resumes_one_shot_runs(
    tmp_path: Path,
) -> None:
    loaded = load_deepseek_paired_final(CONFIG_PATH)
    config = loaded.config.model_copy(
        update={
            "artifacts_root": tmp_path / "paired",
            "method_ids": ["direct_llm_plan"],
        }
    )
    protocol = load_formal_experiment_protocol(config.protocol_path)
    factory_calls = 0

    def factory(_settings):
        nonlocal factory_calls
        factory_calls += 1
        return InvalidSchemaLLM()

    runner = PairedFinalRunner(llm_factory=factory)
    preflight = runner.preflight(
        config=config,
        protocol=protocol,
        config_hash=sha256_json({"test": "one_shot_resume"}),
    )
    first = runner.run_live(
        config=config,
        protocol=protocol,
        preflight=preflight,
    )
    second = runner.run_live(
        config=config,
        protocol=protocol,
        preflight=preflight,
    )

    assert first.complete is True
    assert first.completed_run_count == 60
    assert second.completed_run_count == 60
    assert factory_calls == 60


def test_paired_final_runner_materializes_non_llm_runs(tmp_path: Path) -> None:
    loaded = load_deepseek_paired_final(CONFIG_PATH)
    config = loaded.config.model_copy(
        update={
            "artifacts_root": tmp_path / "paired",
            "method_ids": ["random_baseline"],
        }
    )
    protocol = load_formal_experiment_protocol(config.protocol_path)
    runner = PairedFinalRunner()
    preflight = runner.preflight(
        config=config,
        protocol=protocol,
        config_hash=sha256_json({"test": "non_llm"}),
    )

    manifest = runner.run_live(
        config=config,
        protocol=protocol,
        preflight=preflight,
    )

    assert manifest.complete is True
    assert manifest.completed_run_count == 20
    assert manifest.total_estimated_cost_cny == 0.0


def test_feasibility_probe_recovers_after_behavioral_noop() -> None:
    base = load_scenario(PROJECT_ROOT / "configs/scenarios/small_static.yaml")
    scenario = PairedFinalScenarioFactory().build(base=base, seed=301).scenario
    patches = [
        HeuristicPatch.model_validate(
            {
                "operations": [
                    {
                        "op": "set_weight",
                        "component": "path_score",
                        "feature": "path_latency",
                        "weight": -1.0,
                    }
                ]
            }
        ),
        HeuristicPatch.model_validate(
            {
                "operations": [
                    {
                        "op": "set_weight",
                        "component": "node_score",
                        "feature": "dependency_latency",
                        "weight": -1.0,
                    }
                ]
            }
        ),
    ]

    result = SearchController(
        features=SearchFeatures(
            objective_refinement_enabled=True,
            counterfactual_weight_probe_enabled=True,
        )
    ).run(
        scenario=scenario,
        initial_program=latency_first(),
        generator=ScriptedPatchGenerator(patches),
        budgets=SearchBudgets(
            max_patch_proposals=4,
            max_evaluator_calls=5,
            max_wall_time_seconds=30.0,
            stop_on_first_feasible=True,
        ),
    )

    assert result.best_candidate_id is not None
    assert result.statistics.outcome_rejections == 2
    assert result.statistics.numeric_probes == 2
    best = next(
        item for item in result.records if item.candidate_id == result.best_candidate_id
    )
    assert best.verification.feasible is True
    assert best.execution.plan.placement == {
        "ingest": "sat-b",
        "analyze": "sat-b",
        "respond": "sat-b",
    }
