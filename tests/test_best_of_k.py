"""Best-of-k sampler selection logic (mocked runner, no EDA/Ollama)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sample_best_of_k as sampler


def _task(task_id: str = "arbiter_02") -> SimpleNamespace:
    return SimpleNamespace(task_id=task_id)


def _transcript(passed: bool) -> SimpleNamespace:
    payload = {"task_id": "arbiter_02", "final_outcome": {"passed": passed}}
    return SimpleNamespace(model_dump_json=lambda: json.dumps(payload))


class _Runner:
    def __init__(self, outcomes: list[bool]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def run_live_task(self, task, **kwargs):
        self.calls.append({"task_id": task.task_id, **{k: kwargs[k] for k in ("decode_temperature", "decode_seed") if k in kwargs}})
        return _transcript(self.outcomes.pop(0))


def test_selects_first_passing_sample(tmp_path: Path) -> None:
    runner = _Runner([False, True, True])
    rec = sampler.sample_task(
        runner,
        _task(),
        k=3,
        temperature=0.7,
        seed_base=100,
        model="m",
        provider="ollama",
        liberty=None,
        transcripts_dir=tmp_path,
        work_root=tmp_path / "ws",
    )
    assert rec["verified"] is True
    assert rec["selected_index"] == 1
    assert [s["passed"] for s in rec["samples"]] == [False, True, True]
    assert [s["seed"] for s in rec["samples"]] == [100, 101, 102]
    assert len(runner.calls) == 3
    assert (tmp_path / "arbiter_02_s0.json").is_file()


def test_reports_unverified_when_all_fail(tmp_path: Path) -> None:
    runner = _Runner([False, False])
    rec = sampler.sample_task(
        runner,
        _task(),
        k=2,
        temperature=0.7,
        seed_base=7,
        model="m",
        provider="ollama",
        liberty=None,
        transcripts_dir=tmp_path,
        work_root=tmp_path / "ws",
    )
    assert rec["verified"] is False
    assert rec["selected_index"] is None


def test_resume_reuses_persisted_samples(tmp_path: Path) -> None:
    (tmp_path / "arbiter_02_s0.json").write_text(
        json.dumps({"task_id": "arbiter_02", "final_outcome": {"passed": False}}), encoding="utf-8"
    )
    (tmp_path / "arbiter_02_s1.json").write_text(
        json.dumps({"task_id": "arbiter_02", "final_outcome": {"passed": True}}), encoding="utf-8"
    )
    runner = _Runner([False])
    rec = sampler.sample_task(
        runner,
        _task(),
        k=3,
        temperature=0.7,
        seed_base=100,
        model="m",
        provider="ollama",
        liberty=None,
        transcripts_dir=tmp_path,
        work_root=tmp_path / "ws",
        existing={0: tmp_path / "arbiter_02_s0.json", 1: tmp_path / "arbiter_02_s1.json"},
    )
    assert rec["reused"] == 2
    assert rec["selected_index"] == 1
    assert rec["verified"] is True
    assert [s["passed"] for s in rec["samples"]] == [False, True, False]
    assert len(runner.calls) == 1
    assert runner.calls[0]["decode_seed"] == 102


def test_resume_rejects_foreign_transcript(tmp_path: Path) -> None:
    import pytest

    foreign = tmp_path / "foreign.json"
    foreign.write_text(json.dumps({"task_id": "other_task", "final_outcome": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        sampler.sample_task(
            _Runner([]),
            _task(),
            k=1,
            temperature=0.7,
            seed_base=0,
            model="m",
            provider="ollama",
            liberty=None,
            transcripts_dir=tmp_path,
            work_root=tmp_path / "ws",
            existing={0: foreign},
        )


def test_rejects_nonpositive_k(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError):
        sampler.sample_task(
            _Runner([]),
            _task(),
            k=0,
            temperature=0.7,
            seed_base=0,
            model="m",
            provider="ollama",
            liberty=None,
            transcripts_dir=tmp_path,
            work_root=tmp_path / "ws",
        )
