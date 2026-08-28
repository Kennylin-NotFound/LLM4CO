from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelMetadata(ManifestModel):
    backend: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    version: str = Field(min_length=1)
    temperature: float = Field(ge=0)


class RunStatistics(ManifestModel):
    llm_calls: int = Field(ge=0, default=0)
    evaluator_calls: int = Field(ge=0, default=0)
    retries: int = Field(ge=0, default=0)
    failures: int = Field(ge=0, default=0)
    input_tokens: int = Field(ge=0, default=0)
    output_tokens: int = Field(ge=0, default=0)
    wall_time_ms: float = Field(ge=0, default=0.0)


class RunManifest(ManifestModel):
    manifest_version: str = "0.1.0"
    run_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime | None = None
    command: list[str]
    config_path: str
    config_hash: str = Field(min_length=64, max_length=64)
    code_tree_hash: str = Field(min_length=64, max_length=64)
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    seeds: dict[str, int]
    scenario_hashes: dict[str, str]
    model: ModelMetadata
    prompt_hash: str = Field(min_length=64, max_length=64)
    budgets: dict[str, Any]
    statistics: RunStatistics = Field(default_factory=RunStatistics)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    status: Literal["running", "completed", "failed"] = "running"
    error: str | None = None

