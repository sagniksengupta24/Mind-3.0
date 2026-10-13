"""R2: holdout seal tests (runner/CLI only; no verifier edits).

All fixtures are synthetic files under tmp_path. These tests MUST NOT read the
real heldout task files (leakage control); only synthetic stand-ins are used.
"""

import hashlib
import json
from pathlib import Path

import pytest

from mind3.benchmarks.runner import (
    HoldoutSealError,
    check_holdout_seal,
    is_holdout_path,
)


def _write_tasks(path: Path, n: int = 2) -> Path:
    lines = []
    for i in range(n):
        lines.append(json.dumps({
            "task_id": f"synth_{i:02d}",
            "category": "synthetic",
            "name": f"synth_{i:02d}",
            "natural_language_spec": "synthetic stand-in, not a real task",
            "expected_ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "q", "direction": "output", "width": 1},
            ],
            "sva_properties": ["assert property (@(posedge clk) q == 0);"] * 2,
            "benchmark_origin": "synthetic test stand-in",
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_non_holdout_path_never_requires_unseal(tmp_path: Path) -> None:
    suite = tmp_path / "development-20"
    suite.mkdir()
    _write_tasks(suite / "tasks.jsonl")
    for unseal in (False, True):
        record = check_holdout_seal(suite, unseal=unseal)
        assert record["holdout"] is False
        record = check_holdout_seal(suite / "tasks.jsonl", unseal=unseal)
        assert record["holdout"] is False
    assert check_holdout_seal(None, unseal=False)["holdout"] is False


def test_holdout_path_refused_without_unseal(tmp_path: Path) -> None:
    suite = tmp_path / "heldout-v2"
    suite.mkdir()
    tasks = _write_tasks(suite / "tasks.jsonl")
    (suite / "manifest.json").write_text(json.dumps({"tasks_sha256": _sha(tasks)}), encoding="utf-8")
    with pytest.raises(HoldoutSealError, match="without explicit --unseal"):
        check_holdout_seal(suite, unseal=False)
    with pytest.raises(HoldoutSealError, match="without explicit --unseal"):
        check_holdout_seal(tasks, unseal=False)


def test_holdout_unseal_requires_matching_manifest(tmp_path: Path) -> None:
    suite = tmp_path / "project" / "heldout"
    suite.mkdir(parents=True)
    tasks = _write_tasks(suite / "tasks.jsonl")
    # Missing manifest refuses.
    with pytest.raises(HoldoutSealError, match="manifest.json missing"):
        check_holdout_seal(suite, unseal=True)
    # Mismatched hash refuses.
    (suite / "manifest.json").write_text(json.dumps({"tasks_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(HoldoutSealError, match="hash mismatch"):
        check_holdout_seal(suite, unseal=True)
    # Matching hash (either accepted key spelling) allows.
    (suite / "manifest.json").write_text(json.dumps({"tasks_sha256": _sha(tasks)}), encoding="utf-8")
    record = check_holdout_seal(suite, unseal=True)
    assert record == {"holdout": True, "sealed": True, "unsealed": True, "task_set_sha256": _sha(tasks)}
    (suite / "manifest.json").write_text(json.dumps({"task_set_sha256": _sha(tasks)}), encoding="utf-8")
    assert check_holdout_seal(tasks, unseal=True)["unsealed"] is True
    # Unreadable manifest refuses.
    (suite / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(HoldoutSealError, match="unreadable manifest"):
        check_holdout_seal(suite, unseal=True)


def test_holdout_name_matching_is_case_insensitive(tmp_path: Path) -> None:
    assert is_holdout_path(tmp_path / "HeldOut" / "tasks.jsonl") is True
    assert is_holdout_path(tmp_path / "my_heldout_tasks.jsonl") is True
    assert is_holdout_path(tmp_path / "development-20" / "tasks.jsonl") is False


def test_cli_suite_default_is_not_a_holdout_name() -> None:
    """The CLI default suite must resolve to a non-holdout name (regression test
    for the nonexistent `heldout-v1` default)."""
    import argparse
    from unittest.mock import patch

    from mind3 import cli as cli_module

    captured: dict = {}

    def fake_benchmark(args: argparse.Namespace) -> int:
        captured["suite"] = args.suite
        captured["unseal"] = args.unseal
        return 0

    # main() builds its parser fresh, so patching the module global rebinds func.
    with patch.object(cli_module, "cmd_benchmark", side_effect=fake_benchmark):
        rc = cli_module.main(["benchmark"])
    assert rc == 0
    assert captured["suite"] == "development-20", (
        f"CLI default suite must exist and not be holdout, got {captured['suite']!r}"
    )
    assert "heldout" not in captured["suite"].lower()
    assert captured["unseal"] is False
    assert is_holdout_path(captured["suite"]) is False
