from __future__ import annotations

from pathlib import Path

from cover_opt.config import load_yaml
from cover_opt.domain.models import ScenarioInstance


def load_scenario(path: Path) -> ScenarioInstance:
    return ScenarioInstance.model_validate(load_yaml(path.resolve()))

