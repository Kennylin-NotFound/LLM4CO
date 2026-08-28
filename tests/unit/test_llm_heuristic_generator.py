from pathlib import Path

from cover_opt.heuristics.handcrafted import latency_first
from cover_opt.llm.heuristic_generator import LLMHeuristicGenerator
from cover_opt.llm.protocol import LLMRequest, LLMResponse
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "configs/scenarios/small_static.yaml"
PROMPT_PATH = PROJECT_ROOT / "configs/prompts/initial_heuristic_v1.md"


class SequenceLLM:
    provider = "fixture"
    model = "sequence"

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        parsed = self.payloads[len(self.requests) - 1]
        return LLMResponse(
            request_id=request.request_id,
            request_fingerprint=request.fingerprint,
            provider=self.provider,
            model=self.model,
            raw_text="fixture",
            parsed=parsed,
        )


def test_initial_generator_rejects_invalid_and_deduplicates_valid_dsl() -> None:
    scenario = load_scenario(SCENARIO_PATH)
    valid = latency_first().model_dump(mode="json")
    invalid = {"version": "1.0", "service_order": valid["service_order"]}
    llm = SequenceLLM([invalid, valid, valid])
    generator = LLMHeuristicGenerator(
        llm=llm,
        prompt_template=PROMPT_PATH.read_text(encoding="utf-8"),
    )

    candidates = generator.generate_candidates(scenario, count=3)

    assert len(candidates) == 1
    assert [event.status for event in generator.events] == [
        "schema_or_static_error",
        "accepted",
        "duplicate",
    ]
    assert [request.metadata["proposal_index"] for request in llm.requests] == [
        0,
        1,
        2,
    ]
    assert all("Return exactly one JSON object" in item.prompt for item in llm.requests)
    assert generator.events[0].errors
    assert generator.events[1].ast_signature == generator.events[2].ast_signature
