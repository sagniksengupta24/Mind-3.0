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
