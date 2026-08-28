from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cover_opt.domain.models import RouteAssignment
from cover_opt.hashing import sha256_json


class BaselineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FormulationArtifact(BaselineModel):
    parameters: list[str] = Field(min_length=1)
    variables: list[str] = Field(min_length=1)
    constraints: list[str] = Field(min_length=1)
    objective: str = Field(min_length=1)


class GeneratedSolverArtifact(BaselineModel):
    iteration: int = Field(ge=0)
    language: Literal["python"] = "python"
    solver_backend: Literal["gurobi_mip", "mip_template", "unknown"]
    formulation: FormulationArtifact
    code: str = Field(min_length=1)
    notes: str = ""

    @property
    def artifact_hash(self) -> str:
        return sha256_json(self)


class SolverExecutionOutcome(BaselineModel):
    attempt: int = Field(ge=0)
    status: Literal["execution_error", "modeling_error", "success"]
    error_type: Literal[
        "syntax",
        "runtime",
        "infeasible",
        "unbounded",
        "validation",
        "none",
    ]
    message: str = Field(min_length=1)
    solver_status: str = Field(min_length=1)
    placement: dict[str, str] = Field(default_factory=dict)
    routes: list[RouteAssignment] = Field(default_factory=list)
    expected_artifact_hash: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "SolverExecutionOutcome":
        if self.status == "success":
            if self.error_type != "none" or not self.placement:
                raise ValueError("successful execution requires a placement and no error")
        elif self.placement or self.routes:
            raise ValueError("failed execution cannot provide a deployment plan")
        return self
