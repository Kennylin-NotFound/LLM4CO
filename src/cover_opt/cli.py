from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from cover_opt.config import (
    load_ablation_suite,
    load_baseline_smoke,
    load_current_paper_replay,
    load_deepseek_structured_smoke,
    load_deepseek_search_smoke,
    load_deepseek_live_pilot,
    load_deepseek_paired_final,
    load_llm_plan_replay_suite,
    load_replay_regression_suite,
    load_replay_campaign,
    load_replay_search,
    load_scripted_search,
    load_yaml,
)
from cover_opt.baselines.code_runner import ReplaySolverCodeRunner
from cover_opt.baselines.current_paper import CurrentPaperSolverGenBaseline
from cover_opt.baselines.llm_plan import (
    DirectLLMPlanBaseline,
    StructuredLLMPlanBaseline,
)
from cover_opt.evaluation.ablation import AblationRunner
from cover_opt.evaluation.protocol import load_formal_experiment_protocol
from cover_opt.evaluation.pilot import DeepSeekLivePilotRunner
from cover_opt.evaluation.final import (
    PairedFinalRunner,
    artifact_hash,
    load_preflight,
    save_preflight,
)
from cover_opt.evaluation.statistics import PairedFinalAnalyzer, render_markdown
from cover_opt.contracts import validate_research_contract
from cover_opt.hashing import sha256_file
from cover_opt.hashing import sha256_json
from cover_opt.heuristics.handcrafted import (
    capacity_no_repair,
    capacity_first,
    latency_first,
    latency_no_repair,
    migration_aware,
)
from cover_opt.evaluation.solvers import (
    ExactEnumerationOracle,
    HeuristicBaseline,
    RandomBaseline,
)
from cover_opt.llm.patch_generator import LLMPatchGenerator
from cover_opt.llm.deepseek import DeepSeekChatLLM
from cover_opt.llm.replay import ReplayLLM
from cover_opt.runtime import run_offline
from cover_opt.search.controller import SearchController, ScriptedPatchGenerator
from cover_opt.search.campaign import (
    CampaignSeedRun,
    CounterexampleReplayCampaignRunner,
)
from cover_opt.search.regression import RegressionReplayRunner
from cover_opt.simulator.scenario_factory import load_scenario
from cover_opt.simulator.static import StaticSimulator
from cover_opt.simulator.walker import (
    generate_walker_scenario,
    load_walker_scenario_config,
)


def _write_json_atomic(path: Path, payload: Any) -> Path:
    output = path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cover-opt",
        description="COVER-Opt reproducible research CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    contract_parser = subparsers.add_parser(
        "validate-contract", help="Validate the frozen Phase 0 research contract."
    )
    contract_parser.add_argument(
        "--contract", type=Path, default=Path("research_contract.yaml")
    )

    run_parser = subparsers.add_parser(
        "run-offline", help="Run the Phase 1 mock/replay longitudinal smoke flow."
    )
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--llm", choices=("mock", "replay"), default=None)
    run_parser.add_argument("--replay-file", type=Path)
    run_parser.add_argument(
        "--artifacts-root", type=Path, default=Path("artifacts/runs")
    )

    show_parser = subparsers.add_parser("show-run", help="Print one persisted manifest.")
    show_parser.add_argument("--run-dir", type=Path, required=True)

    walker_parser = subparsers.add_parser(
        "generate-walker", help="Generate one deterministic Walker Delta time-slot scenario."
    )
    walker_parser.add_argument("--config", type=Path, required=True)
    walker_parser.add_argument("--time-slot", type=int, required=True)
    walker_parser.add_argument("--output", type=Path, required=True)

    simulation_parser = subparsers.add_parser(
        "simulate-static",
        help="Select deterministic routes and evaluate one fixed placement.",
    )
    simulation_parser.add_argument("--scenario", type=Path, required=True)
    simulation_parser.add_argument("--placement", type=Path, required=True)
    simulation_parser.add_argument("--output", type=Path, required=True)
    simulation_parser.add_argument("--k-paths", type=int, default=3)

    method_parser = subparsers.add_parser(
        "run-scripted-search",
        help="Run an offline scripted COVER-Opt method-control smoke test.",
    )
    method_parser.add_argument("--config", type=Path, required=True)
    method_parser.add_argument("--output", type=Path, required=True)

    replay_method_parser = subparsers.add_parser(
        "run-replay-search",
        help="Replay recorded LLM patches through the typed COVER-Opt method loop.",
    )
    replay_method_parser.add_argument("--config", type=Path, required=True)
    replay_method_parser.add_argument("--output", type=Path, required=True)

    regression_parser = subparsers.add_parser(
        "run-regression-replay",
        help="Run a fixed multi-counterexample offline replay regression suite.",
    )
    regression_parser.add_argument("--config", type=Path, required=True)
    regression_parser.add_argument("--output", type=Path, required=True)

    baseline_parser = subparsers.add_parser(
        "run-baseline-smoke",
        help="Run shared-interface random, greedy, and small exact baselines.",
    )
    baseline_parser.add_argument("--config", type=Path, required=True)
    baseline_parser.add_argument("--output", type=Path, required=True)

    ablation_parser = subparsers.add_parser(
        "run-ablation-suite",
        help="Run fixed feature-switch control ablations with offline replay.",
    )
    ablation_parser.add_argument("--config", type=Path, required=True)
    ablation_parser.add_argument("--output", type=Path, required=True)

    campaign_parser = subparsers.add_parser(
        "run-counterexample-replay-campaign",
        help=(
            "Persist failed scenarios and replay them in bounded later search runs."
        ),
    )
    campaign_parser.add_argument("--config", type=Path, required=True)
    campaign_parser.add_argument("--output", type=Path, required=True)

    current_paper_parser = subparsers.add_parser(
        "run-current-paper-replay",
        help="Replay the reconstructed paper solver-generation correction loop.",
    )
    current_paper_parser.add_argument("--config", type=Path, required=True)
    current_paper_parser.add_argument("--output", type=Path, required=True)
    llm_plan_parser = subparsers.add_parser(
        "run-llm-plan-replay-suite",
        help="Replay one-shot direct and schema-bound LLM plan baselines.",
    )
    llm_plan_parser.add_argument("--config", type=Path, required=True)
    llm_plan_parser.add_argument("--output", type=Path, required=True)
    protocol_parser = subparsers.add_parser(
        "validate-experiment-protocol",
        help="Validate the frozen formal experiment and claim-gate contract.",
    )
    protocol_parser.add_argument("--protocol", type=Path, required=True)
    deepseek_parser = subparsers.add_parser(
        "run-deepseek-structured-smoke",
        help="Run one live DeepSeek structured-plan smoke under the locked protocol.",
    )
    deepseek_parser.add_argument("--config", type=Path, required=True)
    deepseek_parser.add_argument("--output", type=Path, required=True)
    deepseek_search_parser = subparsers.add_parser(
        "run-deepseek-search-smoke",
        help="Run one live DeepSeek conflict-directed Typed Patch search smoke.",
    )
    deepseek_search_parser.add_argument("--config", type=Path, required=True)
    deepseek_search_parser.add_argument("--output", type=Path, required=True)
    deepseek_pilot_parser = subparsers.add_parser(
        "run-deepseek-live-pilot",
        help="Run the frozen five-seed DeepSeek COVER-Opt diagnostic pilot.",
    )
    deepseek_pilot_parser.add_argument("--config", type=Path, required=True)
    deepseek_pilot_parser.add_argument("--output", type=Path, required=True)
    paired_preflight_parser = subparsers.add_parser(
        "preflight-paired-final",
        help="Build and verify the frozen paired-final scenarios without live calls.",
    )
    paired_preflight_parser.add_argument("--config", type=Path, required=True)
    paired_preflight_parser.add_argument("--output", type=Path, required=True)
    paired_final_parser = subparsers.add_parser(
        "run-deepseek-paired-final",
        help="Run or resume the frozen DeepSeek paired-final experiment.",
    )
    paired_final_parser.add_argument("--config", type=Path, required=True)
    paired_final_parser.add_argument("--preflight", type=Path, required=True)
    analyze_final_parser = subparsers.add_parser(
        "analyze-paired-final",
        help="Analyze a complete paired-final artifact set and apply claim gates.",
    )
    analyze_final_parser.add_argument("--protocol", type=Path, required=True)
    analyze_final_parser.add_argument("--artifacts-root", type=Path, required=True)
    analyze_final_parser.add_argument("--output", type=Path, required=True)
    analyze_final_parser.add_argument("--markdown-output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-contract":
            result = validate_research_contract(args.contract)
        elif args.command == "validate-experiment-protocol":
            protocol = load_formal_experiment_protocol(args.protocol)
            result = {
                "protocol_id": protocol.protocol_id,
                "version": protocol.version,
                "status": protocol.status,
                "protocol_hash": protocol.protocol_hash,
                "live_calls_allowed": protocol.live_model_lock.live_calls_allowed,
                "stage_count": len(protocol.stages),
                "method_count": len(protocol.methods),
                "comparison_count": len(protocol.comparisons),
                "claim_gate_count": len(protocol.claim_gates),
            }
        elif args.command == "run-deepseek-structured-smoke":
            loaded = load_deepseek_structured_smoke(args.config)
            protocol = load_formal_experiment_protocol(
                loaded.config.protocol_path
            )
            if not protocol.live_model_lock.live_calls_allowed:
                raise ValueError("formal protocol has live calls disabled")
            if protocol.live_model_lock.provider != "deepseek":
                raise ValueError("formal protocol provider is not deepseek")
            if protocol.live_model_lock.model_snapshot != loaded.config.llm.model:
                raise ValueError("DeepSeek model does not match the protocol lock")
            scenario_payload = load_yaml(loaded.config.scenario_path)
            scenario_payload.update(
                loaded.config.scenario_overrides.model_dump(
                    mode="json", exclude_none=True
                )
            )
            from cover_opt.domain.models import ScenarioInstance

            scenario = ScenarioInstance.model_validate(scenario_payload)
            baseline = StructuredLLMPlanBaseline.from_template_file(
                llm=DeepSeekChatLLM.from_settings(loaded.config.llm),
                path=loaded.config.prompt_path,
            )
            baseline_result = baseline.run(scenario)
            response = (
                baseline_result.trajectory[0].response
                if baseline_result.trajectory
                else None
            )
            payload = {
                "experiment_id": loaded.config.experiment_id,
                "config_hash": sha256_json(loaded.raw),
                "protocol_hash": protocol.protocol_hash,
                "scenario_hash": scenario.stable_hash,
                "evidence_status": (
                    "single_live_smoke_not_pilot_or_performance_evidence"
                ),
                "llm_settings": loaded.config.llm.model_dump(mode="json"),
                "baseline_result": baseline_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "experiment_id": loaded.config.experiment_id,
                "status": baseline_result.status,
                "stop_reason": baseline_result.stop_reason,
                "model": response.model if response else loaded.config.llm.model,
                "cached": response.cached if response else False,
                "input_tokens": response.usage.input_tokens if response else 0,
                "output_tokens": response.usage.output_tokens if response else 0,
                "system_fingerprint": (
                    response.metadata.get("system_fingerprint")
                    if response
                    else None
                ),
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-deepseek-search-smoke":
            loaded = load_deepseek_search_smoke(args.config)
            protocol = load_formal_experiment_protocol(
                loaded.config.protocol_path
            )
            if not protocol.live_model_lock.live_calls_allowed:
                raise ValueError("formal protocol has live calls disabled")
            if protocol.live_model_lock.provider != "deepseek":
                raise ValueError("formal protocol provider is not deepseek")
            if protocol.live_model_lock.model_snapshot != loaded.config.llm.model:
                raise ValueError("DeepSeek model does not match the protocol lock")
            scenario_payload = load_yaml(loaded.config.scenario_path)
            scenario_payload.update(
                loaded.config.scenario_overrides.model_dump(
                    mode="json", exclude_none=True
                )
            )
            from cover_opt.domain.models import ScenarioInstance

            scenario = ScenarioInstance.model_validate(scenario_payload)
            programs = {
                "latency_first": latency_first,
                "capacity_first": capacity_first,
                "migration_aware": migration_aware,
                "latency_no_repair": latency_no_repair,
            }
            generator = LLMPatchGenerator.from_template_file(
                llm=DeepSeekChatLLM.from_settings(loaded.config.llm),
                path=loaded.config.prompt_path,
                prompt_version=loaded.config.prompt_version,
            )
            search_result = SearchController(features=loaded.config.features).run(
                scenario=scenario,
                initial_program=programs[loaded.config.initial_heuristic](),
                generator=generator,
                budgets=loaded.config.budgets,
            )
            response = (
                generator.events[0].response if generator.events else None
            )
            responses = [
                event.response
                for event in generator.events
                if event.response is not None
            ]
            payload = {
                "experiment_id": loaded.config.experiment_id,
                "config_hash": sha256_json(loaded.raw),
                "protocol_hash": protocol.protocol_hash,
                "scenario_hash": scenario.stable_hash,
                "evidence_status": (
                    "single_live_method_smoke_not_pilot_or_performance_evidence"
                ),
                "llm_settings": loaded.config.llm.model_dump(mode="json"),
                "generation_trace": [
                    event.model_dump(mode="json") for event in generator.events
                ],
                "search_result": search_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            initial_objective = search_result.records[0].objective
            best_record = next(
                (
                    item
                    for item in search_result.records
                    if item.candidate_id == search_result.best_candidate_id
                ),
                None,
            )
            best_objective = best_record.objective if best_record else None
            result = {
                "experiment_id": loaded.config.experiment_id,
                "stop_reason": search_result.stop_reason,
                "best_candidate_id": search_result.best_candidate_id,
                "patch_proposals": search_result.statistics.patch_proposals,
                "accepted_patches": search_result.statistics.accepted_patches,
                "numeric_probes": search_result.statistics.numeric_probes,
                "evaluator_calls": search_result.statistics.evaluator_calls,
                "llm_calls": len(generator.events),
                "model": response.model if response else loaded.config.llm.model,
                "cached": response.cached if response else False,
                "input_tokens": response.usage.input_tokens if response else 0,
                "output_tokens": response.usage.output_tokens if response else 0,
                "total_input_tokens": sum(
                    item.usage.input_tokens for item in responses if not item.cached
                ),
                "total_output_tokens": sum(
                    item.usage.output_tokens for item in responses if not item.cached
                ),
                "initial_weighted_objective": (
                    initial_objective.weighted_objective
                    if initial_objective
                    else None
                ),
                "best_weighted_objective": (
                    best_objective.weighted_objective if best_objective else None
                ),
                "objective_improvement": (
                    initial_objective.weighted_objective
                    - best_objective.weighted_objective
                    if initial_objective and best_objective
                    else None
                ),
                "system_fingerprint": (
                    response.metadata.get("system_fingerprint")
                    if response
                    else None
                ),
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-deepseek-live-pilot":
            loaded = load_deepseek_live_pilot(args.config)
            protocol = load_formal_experiment_protocol(
                loaded.config.protocol_path
            )
            pilot_result = DeepSeekLivePilotRunner().run(
                config=loaded.config,
                protocol=protocol,
            )
            payload = {
                "config_hash": sha256_json(loaded.raw),
                "pilot_result": pilot_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            summary = pilot_result.summary
            result = {
                "pilot_id": pilot_result.pilot_id,
                "case_count": summary.case_count,
                "feasible_count": summary.feasible_count,
                "feasible_rate": summary.feasible_rate,
                "schema_failures": summary.schema_failures,
                "backend_failures": summary.backend_failures,
                "semantic_patch_rejections": summary.semantic_patch_rejections,
                "duplicate_patch_rejections": summary.duplicate_patch_rejections,
                "total_llm_calls": summary.total_llm_calls,
                "total_evaluator_calls": summary.total_evaluator_calls,
                "total_billed_input_tokens": summary.total_billed_input_tokens,
                "total_billed_output_tokens": summary.total_billed_output_tokens,
                "total_estimated_cost_cny": summary.total_estimated_cost_cny,
                "prompt_hash": pilot_result.prompt_hash,
                "protocol_hash": pilot_result.protocol_hash,
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "preflight-paired-final":
            loaded = load_deepseek_paired_final(args.config)
            protocol = load_formal_experiment_protocol(loaded.config.protocol_path)
            preflight = PairedFinalRunner().preflight(
                config=loaded.config,
                protocol=protocol,
                config_hash=sha256_json(loaded.raw),
            )
            output = save_preflight(args.output, preflight)
            result = {
                "experiment_id": preflight.experiment_id,
                "passed": preflight.passed,
                "case_count": len(preflight.cases),
                "protocol_hash": preflight.protocol_hash,
                "scenario_set_hash": preflight.scenario_set_hash,
                "code_tree_hash": preflight.code_tree_hash,
                "worst_case_cost_cny": (
                    preflight.cost_forecast.worst_case_cost_cny
                ),
                "file_hash": artifact_hash(output),
                "output": str(output.resolve()),
            }
        elif args.command == "run-deepseek-paired-final":
            loaded = load_deepseek_paired_final(args.config)
            protocol = load_formal_experiment_protocol(loaded.config.protocol_path)
            preflight = load_preflight(args.preflight)
            manifest = PairedFinalRunner().run_live(
                config=loaded.config,
                protocol=protocol,
                preflight=preflight,
            )
            result = {
                "experiment_id": manifest.experiment_id,
                "complete": manifest.complete,
                "completed_run_count": manifest.completed_run_count,
                "expected_run_count": manifest.expected_run_count,
                "infrastructure_failure_count": (
                    manifest.infrastructure_failure_count
                ),
                "total_estimated_cost_cny": manifest.total_estimated_cost_cny,
                "manifest": str(
                    (loaded.config.artifacts_root.resolve() / "manifest.json")
                ),
            }
        elif args.command == "analyze-paired-final":
            protocol = load_formal_experiment_protocol(args.protocol)
            report = PairedFinalAnalyzer().analyze(
                artifacts_root=args.artifacts_root,
                protocol=protocol,
            )
            output = _write_json_atomic(
                args.output,
                report.model_dump(mode="json"),
            )
            markdown = args.markdown_output.resolve()
            markdown.parent.mkdir(parents=True, exist_ok=True)
            temporary = markdown.with_suffix(markdown.suffix + ".tmp")
            temporary.write_text(
                render_markdown(report),
                encoding="utf-8",
                newline="\n",
            )
            temporary.replace(markdown)
            result = {
                "experiment_id": report.experiment_id,
                "evidence_status": report.evidence_status,
                "supported_claims": report.supported_claims,
                "unsupported_claims": report.unsupported_claims,
                "quality_gates": report.quality_gates,
                "file_hash": sha256_file(output),
                "output": str(output),
                "markdown_output": str(markdown),
            }
        elif args.command == "run-offline":
            command = list(argv) if argv is not None else sys.argv[1:]
            run_dir, manifest = run_offline(
                config_path=args.config,
                backend=args.llm,
                replay_file=args.replay_file,
                artifacts_root=args.artifacts_root,
                command=command,
            )
            result = {
                "run_id": manifest.run_id,
                "run_dir": str(run_dir),
                "status": manifest.status,
                "config_hash": manifest.config_hash,
                "scenario_hashes": manifest.scenario_hashes,
            }
        elif args.command == "show-run":
            manifest_path = args.run_dir.resolve() / "manifest.json"
            with manifest_path.open("r", encoding="utf-8") as handle:
                result = json.load(handle)
        elif args.command == "generate-walker":
            if args.time_slot < 0:
                raise ValueError("time-slot must be non-negative")
            walker_config = load_walker_scenario_config(args.config)
            scenario = generate_walker_scenario(walker_config, args.time_slot)
            output = _write_json_atomic(
                args.output, scenario.model_dump(mode="json")
            )
            result = {
                "scenario_id": scenario.scenario_id,
                "scenario_hash": scenario.stable_hash,
                "file_hash": sha256_file(output),
                "node_count": len(scenario.nodes),
                "link_count": len(scenario.links),
                "output": str(output),
            }
        elif args.command == "simulate-static":
            scenario = load_scenario(args.scenario)
            placement_payload = load_yaml(args.placement.resolve())
            placement = placement_payload.get("placement")
            if not isinstance(placement, dict) or not placement:
                raise ValueError("placement file requires a non-empty placement mapping")
            simulation = StaticSimulator(scenario, k_paths=args.k_paths).run(
                placement,
                method=str(placement_payload.get("method", "fixed_placement")),
                candidate_id=str(placement_payload.get("candidate_id", "manual")),
                run_id="static_cli",
            )
            payload = {
                "scenario_id": scenario.scenario_id,
                "scenario_hash": scenario.stable_hash,
                "evidence_status": "deterministic_kernel_evidence_not_plan_verification",
                "simulation": simulation.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "scenario_id": scenario.scenario_id,
                "scenario_hash": scenario.stable_hash,
                "e2e_latency_ms": simulation.latency.e2e_latency_ms,
                "metric": simulation.latency.metric,
                "verification_status": simulation.verification_status,
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-scripted-search":
            loaded = load_scripted_search(args.config)
            scenario_payload = load_yaml(loaded.config.scenario_path)
            overrides = loaded.config.scenario_overrides.model_dump(
                mode="json", exclude_none=True
            )
            scenario_payload.update(overrides)
            from cover_opt.domain.models import ScenarioInstance

            scenario = ScenarioInstance.model_validate(scenario_payload)
            initial_programs = {
                "latency_first": latency_first,
                "capacity_first": capacity_first,
                "migration_aware": migration_aware,
                "latency_no_repair": latency_no_repair,
            }
            search_result = SearchController().run(
                scenario=scenario,
                initial_program=initial_programs[
                    loaded.config.initial_heuristic
                ](),
                generator=ScriptedPatchGenerator(loaded.config.patches),
                budgets=loaded.config.budgets,
            )
            payload = {
                "experiment_id": loaded.config.experiment_id,
                "config_hash": sha256_json(loaded.raw),
                "scenario_hash": scenario.stable_hash,
                "evidence_status": "scripted_control_flow_evidence_not_llm_performance",
                "search_result": search_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "experiment_id": loaded.config.experiment_id,
                "scenario_hash": scenario.stable_hash,
                "stop_reason": search_result.stop_reason,
                "best_candidate_id": search_result.best_candidate_id,
                "candidate_count": len(search_result.records),
                "patch_proposals": search_result.statistics.patch_proposals,
                "evaluator_calls": search_result.statistics.evaluator_calls,
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-replay-search":
            loaded = load_replay_search(args.config)
            scenario_payload = load_yaml(loaded.config.scenario_path)
            overrides = loaded.config.scenario_overrides.model_dump(
                mode="json", exclude_none=True
            )
            scenario_payload.update(overrides)
            from cover_opt.domain.models import ScenarioInstance

            scenario = ScenarioInstance.model_validate(scenario_payload)
            initial_programs = {
                "latency_first": latency_first,
                "capacity_first": capacity_first,
                "migration_aware": migration_aware,
                "latency_no_repair": latency_no_repair,
            }
            generator = LLMPatchGenerator.from_template_file(
                llm=ReplayLLM.from_file(loaded.config.replay_file),
                path=loaded.config.prompt_path,
            )
            search_result = SearchController().run(
                scenario=scenario,
                initial_program=initial_programs[
                    loaded.config.initial_heuristic
                ](),
                generator=generator,
                budgets=loaded.config.budgets,
            )
            payload = {
                "experiment_id": loaded.config.experiment_id,
                "config_hash": sha256_json(loaded.raw),
                "scenario_hash": scenario.stable_hash,
                "evidence_status": (
                    "replay_llm_control_flow_evidence_not_model_performance"
                ),
                "generation_trace": [
                    event.model_dump(mode="json") for event in generator.events
                ],
                "search_result": search_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "experiment_id": loaded.config.experiment_id,
                "scenario_hash": scenario.stable_hash,
                "stop_reason": search_result.stop_reason,
                "best_candidate_id": search_result.best_candidate_id,
                "candidate_count": len(search_result.records),
                "patch_proposals": search_result.statistics.patch_proposals,
                "evaluator_calls": search_result.statistics.evaluator_calls,
                "generation_events": len(generator.events),
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-regression-replay":
            loaded = load_replay_regression_suite(args.config)
            suite_result = RegressionReplayRunner().run(loaded.config)
            payload = {
                "suite_id": loaded.config.suite_id,
                "config_hash": sha256_json(loaded.raw),
                "evidence_status": (
                    "offline_regression_replay_evidence_not_live_llm_performance"
                ),
                "suite_result": suite_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "suite_id": loaded.config.suite_id,
                "passed": suite_result.passed,
                "case_count": suite_result.case_count,
                "passed_case_count": suite_result.passed_case_count,
                "violation_coverage": suite_result.violation_coverage,
                "counterexample_count": len(suite_result.counterexamples),
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-baseline-smoke":
            loaded = load_baseline_smoke(args.config)
            scenario_payload = load_yaml(loaded.config.scenario_path)
            scenario_payload.update(
                loaded.config.scenario_overrides.model_dump(
                    mode="json", exclude_none=True
                )
            )
            from cover_opt.domain.models import ScenarioInstance

            scenario = ScenarioInstance.model_validate(scenario_payload)
            solvers = [
                ExactEnumerationOracle(
                    k_paths=loaded.config.k_paths,
                    max_candidates=loaded.config.exact_max_candidates,
                    max_wall_time_seconds=(
                        loaded.config.exact_max_wall_time_seconds
                    ),
                ),
                HeuristicBaseline(
                    "latency_greedy",
                    latency_no_repair(),
                    k_paths=loaded.config.k_paths,
                ),
                HeuristicBaseline(
                    "capacity_greedy",
                    capacity_no_repair(),
                    k_paths=loaded.config.k_paths,
                ),
                RandomBaseline(
                    samples=loaded.config.random_samples,
                    seed=loaded.config.random_seed,
                    k_paths=loaded.config.k_paths,
                ),
            ]
            solver_results = [solver.solve(scenario) for solver in solvers]
            oracle = solver_results[0]
            oracle_value = (
                oracle.objective.weighted_objective if oracle.objective else None
            )
            comparisons = []
            for solver_result in solver_results[1:]:
                value = (
                    solver_result.objective.weighted_objective
                    if solver_result.objective
                    else None
                )
                gap_pct = (
                    (value - oracle_value) / oracle_value * 100.0
                    if value is not None
                    and oracle_value is not None
                    and oracle_value > 0
                    else None
                )
                comparisons.append(
                    {
                        "solver_name": solver_result.solver_name,
                        "feasible": solver_result.status == "feasible",
                        "weighted_objective": value,
                        "candidate_set_gap_pct": gap_pct,
                    }
                )
            payload = {
                "experiment_id": loaded.config.experiment_id,
                "config_hash": sha256_json(loaded.raw),
                "scenario_hash": scenario.stable_hash,
                "evidence_status": (
                    "small_fixture_baseline_interface_evidence_not_method_result"
                ),
                "oracle_scope": oracle.scope,
                "oracle_optimality_proven": oracle.optimality_proven,
                "solver_results": [
                    solver_result.model_dump(mode="json")
                    for solver_result in solver_results
                ],
                "comparisons": comparisons,
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "experiment_id": loaded.config.experiment_id,
                "scenario_hash": scenario.stable_hash,
                "oracle_status": oracle.status,
                "oracle_optimality_proven": oracle.optimality_proven,
                "solver_count": len(solver_results),
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-ablation-suite":
            loaded = load_ablation_suite(args.config)
            suite_result = AblationRunner().run(loaded.config)
            payload = {
                "suite_id": loaded.config.suite_id,
                "config_hash": sha256_json(loaded.raw),
                "evidence_status": (
                    "offline_control_ablation_evidence_not_llm_performance"
                ),
                "suite_result": suite_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "suite_id": loaded.config.suite_id,
                "passed": suite_result.passed,
                "variant_count": suite_result.variant_count,
                "passed_variant_count": suite_result.passed_variant_count,
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-counterexample-replay-campaign":
            loaded = load_replay_campaign(args.config)
            programs = {
                "latency_first": latency_first,
                "capacity_first": capacity_first,
                "migration_aware": migration_aware,
                "latency_no_repair": latency_no_repair,
            }
            seeds = []
            for seed in loaded.config.seeds:
                scenario_payload = load_yaml(seed.scenario_path)
                scenario_payload.update(
                    seed.scenario_overrides.model_dump(
                        mode="json", exclude_none=True
                    )
                )
                from cover_opt.domain.models import ScenarioInstance

                scenario = ScenarioInstance.model_validate(scenario_payload)
                seeds.append(
                    CampaignSeedRun(
                        run_id=seed.run_id,
                        scenario=scenario,
                        initial_program=programs[seed.initial_heuristic](),
                        generator=LLMPatchGenerator.from_template_file(
                            llm=ReplayLLM.from_file(seed.replay_file),
                            path=loaded.config.prompt_path,
                        ),
                        budgets=seed.budgets,
                    )
                )

            replay_files = loaded.config.replay.replay_files

            def replay_generator_factory(_entry, replay_index):
                return LLMPatchGenerator.from_template_file(
                    llm=ReplayLLM.from_file(replay_files[replay_index - 1]),
                    path=loaded.config.prompt_path,
                )

            campaign_result = CounterexampleReplayCampaignRunner().run(
                seeds=seeds,
                replay_generator_factory=replay_generator_factory,
                replay_budgets=loaded.config.replay.budgets,
                features=loaded.config.features,
                max_scenario_replays=(
                    loaded.config.replay.max_scenario_replays
                ),
                max_replays_per_counterexample=(
                    loaded.config.replay.max_replays_per_counterexample
                ),
            )
            expected = loaded.config.expectation
            checks = {
                "stop_reason": campaign_result.stop_reason == expected.stop_reason,
                "seed_runs": (
                    campaign_result.statistics.seed_runs == expected.seed_runs
                ),
                "scenario_replays": (
                    campaign_result.statistics.scenario_replays
                    == expected.scenario_replays
                ),
                "resolved_counterexamples": (
                    campaign_result.statistics.resolved_counterexamples
                    == expected.resolved_counterexamples
                ),
                "persisted_counterexamples": (
                    len(campaign_result.counterexample_store)
                    == expected.persisted_counterexamples
                ),
            }
            passed = all(checks.values())
            payload = {
                "campaign_id": loaded.config.campaign_id,
                "config_hash": sha256_json(loaded.raw),
                "evidence_status": (
                    "offline_cross_run_replay_control_evidence_not_llm_performance"
                ),
                "passed": passed,
                "checks": checks,
                "campaign_result": campaign_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "campaign_id": loaded.config.campaign_id,
                "passed": passed,
                "seed_runs": campaign_result.statistics.seed_runs,
                "scenario_replays": campaign_result.statistics.scenario_replays,
                "resolved_counterexamples": (
                    campaign_result.statistics.resolved_counterexamples
                ),
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-current-paper-replay":
            loaded = load_current_paper_replay(args.config)
            scenario_payload = load_yaml(loaded.config.scenario_path)
            scenario_payload.update(
                loaded.config.scenario_overrides.model_dump(
                    mode="json", exclude_none=True
                )
            )
            from cover_opt.domain.models import ScenarioInstance

            scenario = ScenarioInstance.model_validate(scenario_payload)
            baseline = CurrentPaperSolverGenBaseline(
                llm=ReplayLLM.from_file(loaded.config.llm_replay_file),
                runner=ReplaySolverCodeRunner.from_file(
                    loaded.config.runner_replay_file
                ),
                generation_template=loaded.config.generation_prompt_path.read_text(
                    encoding="utf-8"
                ),
                correction_template=loaded.config.correction_prompt_path.read_text(
                    encoding="utf-8"
                ),
            )
            baseline_result = baseline.run(
                scenario=scenario,
                budgets=loaded.config.budgets,
            )
            payload = {
                "experiment_id": loaded.config.experiment_id,
                "config_hash": sha256_json(loaded.raw),
                "scenario_hash": scenario.stable_hash,
                "evidence_status": (
                    "reconstructed_current_paper_control_flow_not_numeric_reproduction"
                ),
                "known_reconstruction_gaps": [
                    "original prompts and generated code are unavailable",
                    "original unit tests and iteration limit are unavailable",
                    "original random seeds and Gurobi configuration are unavailable",
                    "runner outcomes are replayed and generated code is not executed",
                ],
                "baseline_result": baseline_result.model_dump(mode="json"),
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "experiment_id": loaded.config.experiment_id,
                "status": baseline_result.status,
                "stop_reason": baseline_result.stop_reason,
                "llm_calls": baseline_result.statistics.llm_calls,
                "execution_attempts": (
                    baseline_result.statistics.execution_attempts
                ),
                "evaluator_calls": baseline_result.statistics.evaluator_calls,
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        elif args.command == "run-llm-plan-replay-suite":
            loaded = load_llm_plan_replay_suite(args.config)
            case_results = []
            passed_case_count = 0
            baseline_types = {
                "direct_llm_plan": DirectLLMPlanBaseline,
                "structured_llm_plan": StructuredLLMPlanBaseline,
            }
            from cover_opt.domain.models import ScenarioInstance

            for case in loaded.config.cases:
                scenario_payload = load_yaml(case.scenario_path)
                scenario_payload.update(
                    case.scenario_overrides.model_dump(
                        mode="json", exclude_none=True
                    )
                )
                scenario = ScenarioInstance.model_validate(scenario_payload)
                baseline_type = baseline_types[case.baseline]
                baseline = baseline_type.from_template_file(
                    llm=ReplayLLM.from_file(case.replay_file),
                    path=case.prompt_path,
                )
                baseline_result = baseline.run(scenario)
                actual_feasible = bool(
                    baseline_result.solver_result
                    and baseline_result.solver_result.verification
                    and baseline_result.solver_result.verification.feasible
                )
                passed = (
                    baseline_result.status == case.expectation.status
                    and baseline_result.stop_reason == case.expectation.stop_reason
                    and actual_feasible == case.expectation.final_feasible
                )
                passed_case_count += int(passed)
                case_results.append(
                    {
                        "case_id": case.case_id,
                        "expected": case.expectation.model_dump(mode="json"),
                        "passed": passed,
                        "result": baseline_result.model_dump(mode="json"),
                    }
                )
            payload = {
                "suite_id": loaded.config.suite_id,
                "config_hash": sha256_json(loaded.raw),
                "evidence_status": (
                    "one_shot_replay_baseline_control_evidence_not_live_llm_performance"
                ),
                "passed": passed_case_count == len(case_results),
                "case_count": len(case_results),
                "passed_case_count": passed_case_count,
                "cases": case_results,
            }
            output = _write_json_atomic(args.output, payload)
            result = {
                "suite_id": loaded.config.suite_id,
                "passed": payload["passed"],
                "case_count": payload["case_count"],
                "passed_case_count": passed_case_count,
                "file_hash": sha256_file(output),
                "output": str(output),
            }
        else:
            parser.error(f"unknown command: {args.command}")
            return 2
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
