import json
from pathlib import Path

from cover_opt.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs/experiments/ablation_control_suite.yaml"
METHOD_CONFIG_PATH = (
    PROJECT_ROOT / "configs/experiments/method_completion_suite.yaml"
)


def test_control_ablation_suite_persists_real_feature_switches(tmp_path: Path) -> None:
    output = tmp_path / "ablation_suite.json"

    exit_code = main(
        [
            "run-ablation-suite",
            "--config",
            str(CONFIG_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["evidence_status"] == (
        "offline_control_ablation_evidence_not_llm_performance"
    )
    suite = payload["suite_result"]
    assert suite["passed"] is True
    assert suite["variant_count"] == suite["passed_variant_count"] == 10
    variants = {item["variant_id"]: item for item in suite["variants"]}

    targeted = variants["targeted_irrelevant_patch"]
    generic = variants["generic_irrelevant_patch"]
    assert targeted["search_result"]["statistics"]["rejected_patches"] == 1
    assert generic["search_result"]["statistics"]["accepted_patches"] == 1
    assert targeted["prompt_contract"]["contains_constraint_decision_graph"] is True
    assert generic["prompt_contract"]["contains_constraint_decision_graph"] is False

    repair_on = variants["repair_enabled"]
    repair_off = variants["repair_disabled"]
    assert repair_on["search_result"]["best_candidate_id"] == "candidate_000"
    assert repair_off["search_result"]["best_candidate_id"] is None

    memory_off = variants["counterexample_memory_disabled"]
    assert memory_off["prompt_contract"]["contains_counterexample_summary"] is False
    assert memory_off["search_result"]["counterexamples"] == []

    no_feedback = variants["no_feedback_fixed_patch"]
    assert no_feedback["prompt_contract"]["request_purpose"] == "no_feedback_patch"
    assert no_feedback["prompt_contract"]["contains_feedback_details"] is False
    assert no_feedback["prompt_contract"]["contains_counterexample_summary"] is False
    assert no_feedback["generation_trace"][0]["request"]["metadata"][
        "conflict_graph_signature"
    ] is None

    masks_on = variants["feasible_masks_enabled"]
    masks_off = variants["feasible_masks_disabled"]
    assert masks_on["search_result"]["best_candidate_id"] == "candidate_000"
    assert masks_off["search_result"]["best_candidate_id"] is None
    assert masks_off["initial_violation_types"] == ["node_eligibility"]
    placement_events = [
        item
        for item in masks_off["search_result"]["records"][0]["execution"]["trace"]
        if item["stage"] == "placement"
    ]
    assert placement_events
    assert all(item["feasible_masks_enabled"] is False for item in placement_events)


def test_method_completion_suite_isolates_replay_and_multistart(
    tmp_path: Path,
) -> None:
    output = tmp_path / "method_completion_suite.json"

    exit_code = main(
        [
            "run-ablation-suite",
            "--config",
            str(METHOD_CONFIG_PATH),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    suite = payload["suite_result"]
    assert suite["passed"] is True
    assert suite["variant_count"] == suite["passed_variant_count"] == 6
    variants = {item["variant_id"]: item for item in suite["variants"]}

    replay_off = variants["memory_without_replay"]
    replay_on = variants["memory_with_bounded_replay"]
    assert replay_off["search_result"]["statistics"]["counterexample_replays"] == 0
    assert replay_on["search_result"]["statistics"]["counterexample_replays"] == 1
    assert any(
        event["event"] == "counterexample_replayed"
        for event in replay_on["search_result"]["trajectory"]
    )
    replay_event = next(
        event
        for event in replay_on["search_result"]["trajectory"]
        if event["event"] == "counterexample_replayed"
    )
    assert replay_event["parent_candidate_id"] == "candidate_000"
    rejected = next(
        record
        for record in replay_on["search_result"]["records"]
        if record["candidate_id"] == "candidate_001"
    )
    assert rejected["expansion_eligible"] is False
    assert rejected["expansion_block_reason"] == "outcome_rejected"

    single = variants["fixed_single_start"]
    multi = variants["llm_typed_multi_start"]
    assert single["search_result"]["best_candidate_id"] is None
    assert multi["search_result"]["best_candidate_id"] == "candidate_init_001"
    assert multi["initial_generation_trace"][0]["status"] == "accepted"
    assert multi["prompt_contract"]["initial_generation_calls"] == 1
    selection = multi["search_result"]["trajectory"][-1]
    assert selection["event"] == "initial_candidate_selected"
    assert selection["source"] == "generated_initial"
