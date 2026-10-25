"""Run-provenance recording tests (no EDA, no Ollama)."""

from __future__ import annotations

from pathlib import Path

from mind3.benchmarks.runner import _code_provenance


def test_non_git_directory_degrades_gracefully(tmp_path: Path) -> None:
    info = _code_provenance(tmp_path)
    assert info["git_commit"] is None
    assert info["git_dirty"] is None
    assert info["git_untracked_count"] is None
    assert info["file_sha256"] == {}
    assert info["repo_root"] == str(tmp_path.resolve())


def test_live_repo_records_commit_and_digests() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    info = _code_provenance(repo_root)
    assert isinstance(info["git_commit"], str)
    assert len(info["git_commit"]) == 40
    # The two decision-critical files must always be digested when present.
    assert "src/mind3/core/driver.py" in info["file_sha256"]
    assert "src/mind3/core/verifier.py" in info["file_sha256"]
