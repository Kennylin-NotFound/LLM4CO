from pathlib import Path

from cover_opt.heuristics.handcrafted import capacity_first, latency_first
from cover_opt.heuristics.static_verifier import DSLStaticVerifier, dsl_signature
from cover_opt.simulator.scenario_factory import load_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_handcrafted_dsl_is_valid_and_has_stable_signature() -> None:
    scenario = load_scenario(PROJECT_ROOT / "configs/scenarios/small_static.yaml")
    program = latency_first()

    first = DSLStaticVerifier().verify(program, scenario)
    second = DSLStaticVerifier().verify(program.model_copy(deep=True), scenario)

    assert first.valid is True
    assert first.ast_signature == second.ast_signature == dsl_signature(program)


def test_weighted_sum_term_order_does_not_change_signature() -> None:
    first = capacity_first()
    second = capacity_first().model_copy(deep=True)
    second.node_score.terms.reverse()

    assert dsl_signature(first) == dsl_signature(second)


def test_parser_rejects_unknown_feature_and_field() -> None:
    payload = latency_first().model_dump(mode="json")
    payload["node_score"]["terms"][0]["feature"] = "fictional_feature"
    payload["unsafe_python"] = "import os"

    program, report = DSLStaticVerifier().parse_and_verify(payload)

    assert program is None
    assert report.valid is False
    assert any("fictional_feature" in error for error in report.errors)
    assert any("unsafe_python" in error for error in report.errors)


def test_static_verifier_rejects_duplicate_and_zero_rules() -> None:
    payload = latency_first().model_dump(mode="json")
    payload["service_order"]["terms"] = [
        {"feature": "workload_ratio", "weight": 0.0},
        {"feature": "workload_ratio", "weight": 0.0},
    ]
    parsed = capacity_first().__class__.model_validate(payload)

    report = DSLStaticVerifier().verify(parsed)

    assert report.valid is False
    assert "service_order contains duplicate features" in report.errors
    assert "service_order is a zero expression" in report.errors

