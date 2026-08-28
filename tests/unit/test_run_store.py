from pathlib import Path

import pytest

from cover_opt.storage.run_store import RunStore


def test_run_store_rejects_path_escape(tmp_path: Path) -> None:
    store = RunStore(tmp_path, "path_test", "a" * 64)

    with pytest.raises(ValueError, match="escapes the run directory"):
        store.write_json("../outside.json", {"unsafe": True})


def test_run_store_writes_sorted_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path, "json_test", "b" * 64)

    path = store.write_json("nested/result.json", {"z": 1, "a": 2})

    assert path.read_text(encoding="utf-8").index('"a"') < path.read_text(
        encoding="utf-8"
    ).index('"z"')

