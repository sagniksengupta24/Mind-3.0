import json
from pathlib import Path

import pytest

from mind3.core.release import load_release_approval, sha256_file, write_approval_template


def test_release_approval_binds_to_exact_summary(tmp_path: Path) -> None:
    summary = tmp_path / "benchmark_summary.json"
    summary.write_text(json.dumps({"real_transcript_count": 100}), encoding="utf-8")
    approval = tmp_path / "approval.json"
    write_approval_template(approval, summary, "release-evidence")
    loaded = json.loads(approval.read_text(encoding="utf-8"))
    assert loaded["benchmark_summary_sha256"] == sha256_file(summary)
    loaded.update({"reviewer": "Alice", "approval_id": "APR-001", "approved_at": "2026-09-30T10:00:00Z"})
    approval.write_text(json.dumps(loaded), encoding="utf-8")
    assert load_release_approval(approval, sha256_file(summary)).scope == "release-evidence"


def test_release_approval_rejects_template_placeholders(tmp_path: Path) -> None:
    summary = tmp_path / "benchmark_summary.json"
    summary.write_text("{}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    write_approval_template(approval, summary, "release-evidence")
    with pytest.raises(ValueError, match="template placeholders"):
        load_release_approval(approval, sha256_file(summary))


def test_release_approval_rejects_stale_summary_hash(tmp_path: Path) -> None:
    summary = tmp_path / "benchmark_summary.json"
    summary.write_text("{\"real_transcript_count\": 100}\n", encoding="utf-8")
    approval = tmp_path / "approval.json"
    write_approval_template(approval, summary, "release-evidence")
    loaded = json.loads(approval.read_text(encoding="utf-8"))
    loaded.update({"reviewer": "Alice", "approval_id": "APR-002", "approved_at": "2026-09-30T10:00:00Z"})
    approval.write_text(json.dumps(loaded), encoding="utf-8")
    summary.write_text("{\"real_transcript_count\": 101}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        load_release_approval(approval, sha256_file(summary))


def test_export_bundle_rejects_diagnostic_tier(tmp_path: Path, monkeypatch) -> None:
    import runpy
    source = tmp_path / "report"
    source.mkdir()
    summary = source / "benchmark_summary.json"
    summary.write_text(json.dumps({
        "evidence_tier": "diagnostic",
        "actual_real_transcripts": 20,
        "functional_pass_rate": 0.85,
        "full_verified_pass_rate": 0.50,
        "caveat": "Diagnostic evidence only",
    }), encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text("{}", encoding="utf-8")

    export_script = Path(__file__).resolve().parents[1] / "scripts" / "export_verified_bundle.py"
    monkeypatch.setattr("sys.argv", [
        "export_verified_bundle.py",
        "--source", str(source),
        "--approval", str(approval),
    ])
    with pytest.raises(SystemExit, match="RELEASE_BLOCKED: evidence tier is 'diagnostic'"):
        runpy.run_path(str(export_script), run_name="__main__")


def test_export_bundle_rejects_lowering_min_tasks_below_100(tmp_path: Path, monkeypatch) -> None:
    import runpy
    source = tmp_path / "report"
    source.mkdir()
    summary = source / "benchmark_summary.json"
    summary.write_text(json.dumps({
        "evidence_tier": "release-eligible",
        "actual_real_transcripts": 50,
        "functional_pass_rate": 0.85,
        "full_verified_pass_rate": 0.50,
    }), encoding="utf-8")
    approval = tmp_path / "approval.json"
    approval.write_text("{}", encoding="utf-8")

    export_script = Path(__file__).resolve().parents[1] / "scripts" / "export_verified_bundle.py"
    monkeypatch.setattr("sys.argv", [
        "export_verified_bundle.py",
        "--source", str(source),
        "--approval", str(approval),
        "--min-tasks", "50",
    ])
    with pytest.raises(SystemExit, match="release threshold cannot be lowered below 100"):
        runpy.run_path(str(export_script), run_name="__main__")

