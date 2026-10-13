"""R2: paired bootstrap tests (synthetic transcripts only; no model, no EDA)."""

import json
from pathlib import Path

import pytest

from mind3.benchmarks.paired import (
    MDE_DEV20,
    compare_dirs,
    format_human,
    load_scores,
    metric_of,
    paired_bootstrap,
)


def _write(path: Path, task_id: str, passed: bool, silicon: bool = False) -> None:
    path.write_text(json.dumps({
        "task_id": task_id,
        "final_outcome": {"passed": passed, "silicon_verified": silicon},
    }), encoding="utf-8")


def test_metric_definitions() -> None:
    assert metric_of({"final_outcome": {"passed": True, "silicon_verified": True}}, "full_verified") == 1.0
    assert metric_of({"final_outcome": {"passed": True, "silicon_verified": False}}, "full_verified") == 0.0
    assert metric_of({"final_outcome": {"passed": True}}, "passed") == 1.0
    assert metric_of({}, "passed") == 0.0
    with pytest.raises(ValueError, match="unsupported metric"):
        metric_of({}, "pass_at_k")


def test_identical_inputs_give_zero_effect(tmp_path: Path) -> None:
    base = tmp_path / "A"
    cont = tmp_path / "B"
    base.mkdir()
    cont.mkdir()
    for i in range(8):
        _write(base / f"t{i:02d}.json", f"t{i:02d}", passed=(i % 2 == 0), silicon=(i % 2 == 0))
        _write(cont / f"t{i:02d}.json", f"t{i:02d}", passed=(i % 2 == 0), silicon=(i % 2 == 0))
    result = compare_dirs(base, cont, resamples=1000, seed=7)
    assert result["effect"] == 0.0
    assert result["ci95"][0] <= 0.0 <= result["ci95"][1]
    assert result["ci_excludes_zero"] is False
    assert result["tasks_paired"] == 8
    assert "optimistic by construction" in format_human(result)


def test_known_shift_is_recovered(tmp_path: Path) -> None:
    base = tmp_path / "A"
    cont = tmp_path / "B"
    base.mkdir()
    cont.mkdir()
    # 20 tasks; contender fixes 6 of the baseline's 10 failures -> effect +0.30.
    for i in range(20):
        b = i < 10
        c = (i < 10) or (i < 16)
        _write(base / f"t{i:02d}.json", f"t{i:02d}", passed=b, silicon=b)
        _write(cont / f"t{i:02d}.json", f"t{i:02d}", passed=c, silicon=c)
    result = compare_dirs(base, cont, resamples=5000, seed=11)
    assert result["effect"] == pytest.approx(0.30)
    assert result["ci95"][0] > 0.0, f"expected CI above zero, got {result['ci95']}"
    assert result["ci_excludes_zero"] is True
    assert result["meets_mde"] is True


def test_repeats_averaged_within_task() -> None:
    base = {"t01": [1.0, 0.0], "t02": [0.0]}  # t01 mean 0.5
    cont = {"t01": [1.0], "t02": [1.0]}       # diffs: +0.5, +1.0 -> effect +0.75
    result = paired_bootstrap(base, cont, resamples=500, seed=3)
    assert result["effect"] == pytest.approx(0.75)
    assert result["tasks_paired"] == 2


def test_unpaired_tasks_excluded_and_reported() -> None:
    base = {"t01": 1.0, "t02": 0.0}
    cont = {"t01": 1.0, "t03": 1.0}
    result = paired_bootstrap(base, cont, resamples=500, seed=3)
    assert result["tasks_paired"] == 1
    assert result["tasks_baseline_only"] == ["t02"]
    assert result["tasks_contender_only"] == ["t03"]
    assert result["effect"] == pytest.approx(0.0)


def test_no_overlap_raises() -> None:
    with pytest.raises(ValueError, match="no tasks present in both"):
        paired_bootstrap({"a": 1.0}, {"b": 1.0}, resamples=500)


def test_mde_default_and_override() -> None:
    assert MDE_DEV20 == 0.25
    result = paired_bootstrap({"t01": 0.0}, {"t01": 1.0}, resamples=500, mde=1.5)
    assert result["effect"] == pytest.approx(1.0)
    assert result["meets_mde"] is False  # |1.0| < 1.5


def test_determinism_given_seed(tmp_path: Path) -> None:
    base = tmp_path / "A"
    cont = tmp_path / "B"
    base.mkdir()
    cont.mkdir()
    for i in range(10):
        _write(base / f"t{i:02d}.json", f"t{i:02d}", passed=(i % 3 == 0), silicon=(i % 3 == 0))
        _write(cont / f"t{i:02d}.json", f"t{i:02d}", passed=(i % 2 == 0), silicon=(i % 2 == 0))
    first = compare_dirs(base, cont, resamples=2000, seed=99)
    second = compare_dirs(base, cont, resamples=2000, seed=99)
    assert first == second


def test_load_scores_rejects_empty_and_unreadable(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no transcript JSON"):
        load_scores(empty, "passed")
    with pytest.raises(FileNotFoundError, match="not found"):
        load_scores(tmp_path / "missing", "passed")
