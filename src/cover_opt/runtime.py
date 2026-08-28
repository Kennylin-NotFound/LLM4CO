from __future__ import annotations

import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cover_opt.config import LoadedExperiment, load_experiment, load_yaml
from cover_opt.domain.models import ScenarioInstance
from cover_opt.hashing import canonical_json, sha256_json, sha256_text, sha256_tree
from cover_opt.llm.mock import MockLLM
from cover_opt.llm.protocol import LLMProtocol, build_request
from cover_opt.llm.replay import ReplayLLM
from cover_opt.storage.manifest import ModelMetadata, RunManifest, RunStatistics
from cover_opt.storage.run_store import RunStore


def _scenario_summary(scenario: ScenarioInstance) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "time_slot": scenario.time_slot,
        "node_count": len(scenario.nodes),
        "link_count": len(scenario.links),
        "service_count": len(scenario.services),
        "dependency_count": len(scenario.service_edges),
        "qos_latency_ms": scenario.qos_latency_ms,
        "migration_budget": scenario.migration_budget,
        "objective": scenario.objective.model_dump(mode="json"),
    }


def _render_prompt(template: str, scenario: ScenarioInstance) -> str:
    marker = "{{scenario_json}}"
    if marker not in template:
        raise ValueError("prompt template is missing {{scenario_json}}")
    return template.replace(marker, canonical_json(_scenario_summary(scenario)))


def _build_llm(
    loaded: LoadedExperiment,
    backend: Literal["mock", "replay"],
    replay_file: Path | None,
) -> LLMProtocol:
    config = loaded.config
    if backend == "mock":
        return MockLLM(
            responses={"offline_candidate_stub": config.mock_candidate},
            provider=config.llm.provider,
            model=config.llm.model,
        )
    if replay_file is None:
        raise ValueError("--replay-file is required when --llm replay is selected")
    return ReplayLLM.from_file(replay_file)


def run_offline(
    *,
    config_path: Path,
    backend: Literal["mock", "replay"] | None = None,
    replay_file: Path | None = None,
    artifacts_root: Path = Path("artifacts/runs"),
    command: list[str] | None = None,
) -> tuple[Path, RunManifest]:
    loaded = load_experiment(config_path)
    config = loaded.config
    selected_backend = backend or config.llm.backend
    random.seed(config.seed)

    scenario = ScenarioInstance.model_validate(load_yaml(config.scenario_path))
    template = config.prompt_path.read_text(encoding="utf-8")
    prompt = _render_prompt(template, scenario)
    request = build_request(
        purpose="offline_candidate_stub",
        prompt=prompt,
        expected_output="heuristic_candidate_stub_json",
        metadata={
            "scenario_id": scenario.scenario_id,
            "scenario_hash": scenario.stable_hash,
            "phase": "phase_1_offline_boundary",
        },
    )

    config_hash = sha256_json(loaded.raw)
    source_root = Path(__file__).resolve().parent
    code_tree_hash = sha256_tree(source_root)
    store = RunStore(artifacts_root, config.experiment_id, config_hash)
    model_metadata = ModelMetadata(
        backend=selected_backend,
        provider=config.llm.provider,
        model=config.llm.model,
        version=config.llm.version,
        temperature=config.llm.temperature,
    )
    manifest = RunManifest(
        run_id=store.run_id,
        experiment_id=config.experiment_id,
        started_at=datetime.now(timezone.utc),
        command=command or [],
        config_path=str(loaded.path),
        config_hash=config_hash,
        code_tree_hash=code_tree_hash,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        seeds={"experiment": config.seed, "scenario": scenario.seed},
        scenario_hashes={scenario.scenario_id: scenario.stable_hash},
        model=model_metadata,
        prompt_hash=sha256_text(prompt),
        budgets=config.budgets.model_dump(mode="json"),
    )
    store.write_manifest(manifest)
    store.write_json("inputs/experiment_config.json", config.model_dump(mode="json"))
    store.write_json("inputs/scenario.json", scenario)
    store.write_text("inputs/rendered_prompt.txt", prompt)
    store.write_json("traces/0001_request.json", request)

    started = time.perf_counter()
    try:
        llm = _build_llm(loaded, selected_backend, replay_file)
        response = llm.generate(request)
        store.write_json("traces/0001_response.json", response)
        result = {
            "phase": "phase_1_offline_boundary",
            "candidate": response.parsed,
            "evidence_status": "not_optimization_evidence",
            "next_required_gate": "typed_dsl_static_verification_gate_b",
        }
        store.write_json("result.json", result)

        manifest.model.provider = response.provider
        manifest.model.model = response.model
        manifest.statistics = RunStatistics(
            llm_calls=1,
            evaluator_calls=0,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            wall_time_ms=(time.perf_counter() - started) * 1000.0,
        )
        manifest.artifact_paths = {
            "config": "inputs/experiment_config.json",
            "scenario": "inputs/scenario.json",
            "prompt": "inputs/rendered_prompt.txt",
            "request": "traces/0001_request.json",
            "response": "traces/0001_response.json",
            "result": "result.json",
        }
        manifest.status = "completed"
        manifest.finished_at = datetime.now(timezone.utc)
        store.write_manifest(manifest)
        return store.run_dir, manifest
    except Exception as exc:
        manifest.statistics.failures = 1
        manifest.statistics.wall_time_ms = (time.perf_counter() - started) * 1000.0
        manifest.status = "failed"
        manifest.error = f"{type(exc).__name__}: {exc}"
        manifest.finished_at = datetime.now(timezone.utc)
        store.write_json("error.json", {"error": manifest.error})
        manifest.artifact_paths["error"] = "error.json"
        store.write_manifest(manifest)
        raise

