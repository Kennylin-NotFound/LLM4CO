from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from cover_opt.storage.manifest import RunManifest


class RunStore:
    def __init__(self, root: Path, experiment_id: str, config_hash: str) -> None:
        safe_experiment = re.sub(r"[^A-Za-z0-9_.-]+", "_", experiment_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.run_id = f"{timestamp}_{safe_experiment}_{config_hash[:8]}"
        self.root = root.resolve()
        self.run_dir = self.root / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)

    def _resolve_child(self, relative_path: str) -> Path:
        target = (self.run_dir / relative_path).resolve()
        try:
            target.relative_to(self.run_dir)
        except ValueError as exc:
            raise ValueError("artifact path escapes the run directory") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def write_json(self, relative_path: str, payload: Any) -> Path:
        target = self._resolve_child(relative_path)
        if isinstance(payload, BaseModel):
            serializable = payload.model_dump(mode="json")
        else:
            serializable = payload
        temporary = target.with_suffix(target.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                serializable,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
        temporary.replace(target)
        return target

    def write_text(self, relative_path: str, content: str) -> Path:
        target = self._resolve_child(relative_path)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(target)
        return target

    def write_manifest(self, manifest: RunManifest) -> Path:
        return self.write_json("manifest.json", manifest)

