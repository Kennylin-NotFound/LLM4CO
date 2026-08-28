from pathlib import Path

from cover_opt.domain.models import ScenarioInstance
from cover_opt.heuristics.handcrafted import latency_first
from cover_opt.llm.mock import MockLLM
from cover_opt.llm.heuristic_generator import LLMHeuristicGenerator
from cover_opt.llm.patch_generator import LLMPatchGenerator
from cover_opt.llm.replay import ReplayLLM
from cover_opt.search.budgets import SearchBudgets
from cover_opt.search.controller import SearchController
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"
PROMPT_PATH = PROJECT_ROOT / "configs/prompts/conflict_patch.md"
INITIAL_PROMPT_PATH = PROJECT_ROOT / "configs/prompts/initial_heuristic_v1.md"
REPLAY_PATH = PROJECT_ROOT / "tests/fixtures/llm/replay_conflict_patch.json"


def zero_migration_scenario() -> ScenarioInstance:
    base = load_scenario(SCENARIO_PATH)
    payload = base.model_dump(mode="json")
    payload["migration_budget"] = 0
    return ScenarioInstance.model_validate(payload)


def migration_patch_payload() -> dict:
    return {
        "version": "1.0",
        "operations": [
            {
                "op": "add_term",
                "component": "node_score",
                "feature": "migration_penalty",
                "weight": -10.0,
            }
        ],
        "rationale": "Penalize placement changes under the zero migration budget.",
    }


def generator_for(llm) -> LLMPatchGenerator:
    return LLMPatchGenerator.from_template_file(llm=llm, path=PROMPT_PATH)


def test_mock_llm_generates_a_schema_valid_patch_for_the_full_search_loop() -> None:
    llm = MockLLM(responses={"conflict_patch": migration_patch_payload()})
    generator = generator_for(llm)

    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(max_patch_proposals=1, max_evaluator_calls=2),
    )

    assert result.stop_reason == "first_feasible"
    assert result.best_candidate_id == "candidate_001"
    assert generator.events[0].status == "schema_valid"
    assert generator.events[0].request_fingerprint == (
        generator.events[0].response.request_fingerprint
    )
    assert generator.events[0].request.metadata["allowed_components"] == [
        "node_score",
        "repair_policy",
    ]
    assert '"counterexample_summary"' in generator.events[0].request.prompt
    assert result.replay_queue == [result.counterexamples[0].counterexample_id]
    assert result.statistics.initial_generation_calls == 0
    assert result.statistics.patch_generation_calls == 1
    assert result.statistics.total_llm_calls == 1


def test_replay_llm_reproduces_the_same_typed_patch_path_offline() -> None:
    generator = generator_for(ReplayLLM.from_file(REPLAY_PATH))

    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(max_patch_proposals=1, max_evaluator_calls=2),
    )

    assert result.stop_reason == "first_feasible"
    assert generator.events[0].response is not None
    assert generator.events[0].response.replayed is True


def test_invalid_llm_payload_is_recorded_and_never_reaches_executor() -> None:
    generator = generator_for(
        MockLLM(responses={"conflict_patch": {"unexpected": "payload"}})
    )

    result = SearchController().run(
        scenario=zero_migration_scenario(),
        initial_program=latency_first(),
        generator=generator,
        budgets=SearchBudgets(max_patch_proposals=1, max_evaluator_calls=2),
    )

    assert result.stop_reason == "patch_budget"
    assert result.statistics.patch_proposals == 1
    assert result.statistics.rejected_patches == 1
    assert result.statistics.evaluator_calls == 1
    assert result.statistics.patch_generation_calls == 1
    assert result.statistics.total_llm_calls == 1
    assert generator.events[0].status == "schema_error"
    assert [event["event"] for event in result.trajectory] == [
        "candidate_evaluated",
        "patch_generation_failed",
    ]


def test_initial_and_patch_generation_share_one_total_llm_budget() -> None:
    scenario = zero_migration_scenario()
    initial_generator = LLMHeuristicGenerator(
        llm=MockLLM(
            responses={
                "initial_heuristic": latency_first().model_dump(mode="json")
            }
        ),
        prompt_template=INITIAL_PROMPT_PATH.read_text(encoding="utf-8"),
    )
    patch_generator = generator_for(
        MockLLM(responses={"conflict_patch": migration_patch_payload()})
    )

    result = SearchController().run(
        scenario=scenario,
        initial_program=latency_first(),
        initial_generator=initial_generator,
        initial_generation_count=1,
        generator=patch_generator,
        budgets=SearchBudgets(
            max_patch_proposals=1,
            max_total_llm_calls=1,
            max_evaluator_calls=2,
        ),
    )

    assert result.stop_reason == "llm_call_budget"
    assert result.statistics.initial_generation_calls == 1
    assert result.statistics.patch_generation_calls == 0
    assert result.statistics.total_llm_calls == 1
    assert result.statistics.patch_proposals == 0
    assert len(result.initial_generation_trace) == 1
    assert result.initial_generation_trace[0]["status"] == "accepted"
    assert patch_generator.events == []
    assert any(
        event["event"] == "initial_candidate_skipped"
        and event["reason"] == "duplicate_ast_signature"
        for event in result.trajectory
    )
