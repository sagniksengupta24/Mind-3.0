"""Provenance/accounting audit tests (no EDA, no Ollama)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import audit_run_provenance as audit


def _payload(*, calls: int, parse_attempts: int, terminal: str | None = None, provenance: bool = True) -> dict:
    return {
        "task_id": "arbiter_02",
        "decode": {"calls_observed": calls, "parse_attempts": parse_attempts},
        "environment": {"code_provenance": {"git_commit": "a" * 40, "git_dirty": False}} if provenance else {},
        "final_outcome": {"failure_category": terminal, "passed": False},
    }


def test_flags_prefix_parse_accounting() -> None:
    row = audit.audit_transcript(_payload(calls=3, parse_attempts=3, terminal="RESPONSE_PARSE_FAILURE"))
    assert "PREFIX_PARSE_ACCOUNTING" in row["flags"]


def test_clean_run_has_no_accounting_flags() -> None:
    row = audit.audit_transcript(_payload(calls=4, parse_attempts=0, terminal="COVERAGE_BUILD_FAILURE"))
    assert "PREFIX_PARSE_ACCOUNTING" not in row["flags"]
    assert "IMPOSSIBLE_PARSE_ACCOUNTING" not in row["flags"]
    assert row["flags"] == []


def test_flags_parse_terminal_without_attempts() -> None:
    row = audit.audit_transcript(_payload(calls=4, parse_attempts=0, terminal="RESPONSE_PARSE_FAILURE"))
    assert "PARSE_TERMINAL_WITHOUT_PARSE_ATTEMPTS" in row["flags"]


def test_flags_missing_provenance() -> None:
    row = audit.audit_transcript(_payload(calls=1, parse_attempts=0, provenance=False))
    assert "NO_CODE_PROVENANCE" in row["flags"]


def test_audit_dir_reads_transcripts(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text(
        json.dumps(_payload(calls=3, parse_attempts=3, terminal="RESPONSE_PARSE_FAILURE")), encoding="utf-8"
    )
    (tmp_path / "b.json").write_text(
        json.dumps(_payload(calls=2, parse_attempts=0, terminal=None)), encoding="utf-8"
    )
    result = audit.audit_dir(tmp_path)
    assert result["transcripts"] == 2
    assert len(result["flagged"]) == 1
    assert result["flagged"][0]["task_id"] == "arbiter_02"
