"""R2: env-blocked / cdc_backend result-field tests (runner-side only)."""

from mind3.benchmarks.runner import (
    BenchmarkRunner,
    BenchmarkTranscript,
    cdc_backend_of,
    is_env_blocked_outcome,
)


def _transcript(task_id: str, **overrides) -> BenchmarkTranscript:
    base = dict(
        task_id=task_id,
        category="synthetic",
        name=task_id,
        natural_language_spec="synthetic",
        model="qwen2.5-coder:7b",
        provider="ollama",
        final_outcome={"passed": False, "silicon_verified": False},
    )
    base.update(overrides)
    return BenchmarkTranscript(**base)


def test_env_blocked_classification() -> None:
    assert is_env_blocked_outcome({"error_category": "ENVIRONMENT_FAILURE"}) is True
    assert is_env_blocked_outcome({"error_category": "RESPONSE_PARSE_FAILURE"}) is False
    assert is_env_blocked_outcome({}) is False
    assert is_env_blocked_outcome({"error_category": "SPECIFICATION_ERROR"}) is False


def test_cdc_backend_classification() -> None:
    assert cdc_backend_of({"eda_versions": {"cdc": "structural_cdc_checker 1.0"}}) == "structural-only"
    assert cdc_backend_of({"eda_versions": {"cdc": "crux 0.5"}}) == "external"
    assert cdc_backend_of({"eda_versions": {}}) is None
    assert cdc_backend_of({}) is None
    assert cdc_backend_of(None) is None


def test_evaluate_counts_env_blocked_separately(tmp_path: Path) -> None:
    runner = BenchmarkRunner(transcripts_dir=tmp_path)
    model_fail = _transcript(
        "model_fail",
        gate_failure_category="FORMAL_INVARIANT_BREACH",
        final_outcome={"passed": False, "error_category": "FORMAL_INVARIANT_BREACH"},
    )
    env_fail = _transcript(
        "env_fail",
        gate_failure_category=None,
        final_outcome={"passed": False, "status": "RUN_EXCEPTION", "error_category": "ENVIRONMENT_FAILURE"},
        environment={"exception_type": "RuntimeError"},
        env_blocked=True,
    )
    summary = runner.evaluate_transcripts([model_fail, env_fail])
    assert summary.real_transcript_count == 2
    assert summary.env_blocked_count == 1
    # Tool problems are not attributed to the model.
    assert summary.failure_categories.get("env-blocked") == 1
    assert summary.failure_categories.get("FORMAL_INVARIANT_BREACH") == 1
    assert "ENVIRONMENT_FAILURE" not in summary.failure_categories


def test_evaluate_counts_cdc_backends(tmp_path: Path) -> None:
    runner = BenchmarkRunner(transcripts_dir=tmp_path)
    t_struct = _transcript("a", cdc_backend="structural-only")
    t_none = _transcript("b")
    summary = runner.evaluate_transcripts([t_struct, t_none])
    assert summary.cdc_backend_counts.get("structural-only") == 1
    assert summary.cdc_backend_counts.get("not-recorded") == 1


def test_old_transcripts_load_with_field_defaults(tmp_path: Path) -> None:
    """Transcripts written before R2 (without the new keys) load with safe defaults."""
    import json

    legacy = {
        "task_id": "legacy_01",
        "category": "legacy",
        "name": "legacy_01",
        "natural_language_spec": "legacy",
        "model": "qwen2.5-coder:7b",
        "provider": "ollama",
        "final_outcome": {"passed": True, "silicon_verified": True},
    }
    path = tmp_path / "legacy_01.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    runner = BenchmarkRunner(transcripts_dir=tmp_path)
    loaded = runner.load_transcripts(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].env_blocked is False
    assert loaded[0].cdc_backend is None
    summary = runner.evaluate_transcripts(loaded)
    assert summary.env_blocked_count == 0
    assert summary.cdc_backend_counts.get("not-recorded") == 1
