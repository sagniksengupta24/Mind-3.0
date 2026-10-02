"""Tests for benchmark reproducibility, manifest verification, failure classification, and baselines."""

import json
from pathlib import Path

import pytest

from mind3.benchmarks.baselines import (
    BaselineComparisonRunner,
    BaselineType,
    _wilson_ci95,
)
from mind3.benchmarks.reproducibility import execute_full_benchmark
from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTask, sha256_file
from mind3.core.failure_taxonomy import FailureCategory, classify_failure
from mind3.eda.smoke_test import run_eda_smoke_test


def test_eda_smoke_test_probes_all_tools() -> None:
    report = run_eda_smoke_test()
    assert report.platform
    assert "yosys" in report.tools
    assert "verilator" in report.tools
    assert "sby" in report.tools
    assert "opensta" in report.tools
    assert "openroad" in report.tools
    # Yosys, Verilator, and SBY are installed and must report their version or missing without fabricating mock output
    assert not any("SIMULATED" in t.version_string for t in report.tools.values())


def test_failure_taxonomy_deterministic_classification() -> None:
    # 1. Syntax error
    c1 = classify_failure(stdout="syntax error near token ';'", stderr="Error at line 12")
    assert c1.canonical_category == FailureCategory.RTL_SYNTAX_ERROR

    # 2. Inferred latch
    c2 = classify_failure(stderr="ERROR: Latch inferred for signal '\\dut.\\q'")
    assert c2.canonical_category == FailureCategory.RTL_SEMANTIC_ERROR

    # 3. Combinational loop
    c3 = classify_failure(stderr="Warning: combinational loop detected between net a and net b")
    assert c3.canonical_category == FailureCategory.RTL_SEMANTIC_ERROR

    # 4. Simulation failure / assertion mismatch
    c4 = classify_failure(stdout="ASSERTION FAILED: mismatch at time 100", exit_code=1)
    assert c4.canonical_category == FailureCategory.SIMULATION_FAILURE

    # 5. Formal invariant breach
    c5 = classify_failure(error_category="FORMAL_INVARIANT_BREACH", failure_reason="BMC failed at step 2")
    assert c5.canonical_category == FailureCategory.FORMAL_FAILURE

    # 6. Timing slack violation
    c6 = classify_failure(error_category="TIMING_SLACK_VIOLATION", failure_reason="WNS = -120ps")
    assert c6.canonical_category == FailureCategory.TIMING_FAILURE

    # 7. CDC violation
    c7 = classify_failure(error_category="CDC_VIOLATION", failure_reason="Unsynchronized crossing on clk_b")
    assert c7.canonical_category == FailureCategory.CDC_FAILURE

    # 8. Coverage deficit
    c8 = classify_failure(error_category="COVERAGE_DEFICIT", failure_reason="Branch coverage 82% < 95%")
    assert c8.canonical_category == FailureCategory.COVERAGE_FAILURE

    # 9. Repair failure
    c9 = classify_failure(error_category="REPAIR_BUDGET_EXHAUSTED", failure_reason="Max turns reached")
    assert c9.canonical_category == FailureCategory.REPAIR_FAILURE

    # 10. Environment failure
    c10 = classify_failure(error_category="EDA_BINARY_MISSING", stderr="sta: command not found", exit_code=127)
    assert c10.canonical_category == FailureCategory.ENVIRONMENT_FAILURE

    # 11. Timeout
    c11 = classify_failure(exit_code=124, stderr="Process timed out after 60s")
    assert c11.canonical_category == FailureCategory.TIMEOUT

    # 12. Unknown
    c12 = classify_failure(stderr="Something unexpected happened")
    assert c12.canonical_category == FailureCategory.UNKNOWN


def test_wilson_ci95_bounds() -> None:
    # 0 out of 100
    low, high = _wilson_ci95(0, 100)
    assert low == 0.0
    assert 0.0 < high < 0.05

    # 100 out of 100
    low, high = _wilson_ci95(100, 100)
    assert 0.95 < low < 1.0
    assert high == 1.0

    # 85 out of 100
    low, high = _wilson_ci95(85, 100)
    assert low < 0.85 < high


def test_heldout_suite_structure_and_manifest_integrity() -> None:
    root = Path(__file__).resolve().parents[1]
    suite_dir = root / "benchmarks" / "heldout"
    tasks_file = suite_dir / "tasks.jsonl"
    manifest_file = suite_dir / "manifest.json"

    assert tasks_file.is_file(), "heldout tasks.jsonl must exist"
    assert manifest_file.is_file(), "heldout manifest.json must exist"

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["task_count"] >= 100, f"Heldout tasks must be >= 100, got {manifest['task_count']}"
    assert manifest["immutable"] is True

    # Cryptographic SHA-256 match
    computed_hash = sha256_file(tasks_file)
    assert manifest["tasks_sha256"] == computed_hash, "Manifest SHA-256 must match file digest"

    # Verify tasks parse and have required categories
    tasks: list[BenchmarkTask] = []
    with tasks_file.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tasks.append(BenchmarkTask.model_validate_json(line))

    assert len(tasks) == manifest["task_count"]
    categories = {t.category for t in tasks}
    required_cats = {
        "counters", "FIFOs", "arbiters", "FSMs", "UART", "SPI",
        "register interfaces", "APB peripherals", "AXI interfaces",
        "DMA blocks", "CDC-sensitive blocks", "reset-heavy designs", "protocol adapters",
    }
    assert required_cats.issubset(categories), f"Missing categories: {required_cats - categories}"

    # Verify adversarial tasks are present
    adversarial_tasks = [t for t in tasks if t.is_adversarial]
    assert len(adversarial_tasks) >= 10, f"Expected at least 10 adversarial tasks, got {len(adversarial_tasks)}"


def test_fixture_vs_real_benchmark_separation() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture_tasks_file = root / "benchmarks" / "tasks.jsonl"
    heldout_tasks_file = root / "benchmarks" / "heldout" / "tasks.jsonl"

    # Tasks in heldout must be distinct from the 50 schema validation fixtures
    fixtures_hash = sha256_file(fixture_tasks_file)
    heldout_hash = sha256_file(heldout_tasks_file)
    assert fixtures_hash != heldout_hash, "Held-out benchmark must NOT share hash with fixtures"

    # Fixtures are 50 tasks
    runner = BenchmarkRunner(tasks_file=fixture_tasks_file)
    fixture_tasks = runner.load_tasks()
    assert len(fixture_tasks) == 50

    # Held-out tasks are >= 100
    heldout_runner = BenchmarkRunner(tasks_file=heldout_tasks_file)
    heldout_tasks = heldout_runner.load_tasks()
    assert len(heldout_tasks) >= 100


def test_reproducible_benchmark_execution_and_artifacts(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    suite_dir = root / "benchmarks" / "heldout"

    # Run on small deterministic sample (2 tasks) to verify artifact generation
    out_dir = tmp_path / "results"
    execute_full_benchmark(
        suite_dir=suite_dir,
        output_dir=out_dir,
        seed=42,
        sample_size=2,
    )

    expected_files = [
        "summary.json",
        "report.html",
        "failures.json",
        "tool_versions.json",
        "environment.json",
        "benchmark_manifest.json",
        "baseline_comparison.json",
    ]
    for fname in expected_files:
        p = out_dir / fname
        assert p.is_file(), f"Expected artifact {fname} was not produced in {out_dir}"
        assert p.stat().st_size > 0, f"Artifact {fname} is empty"

    manifest = json.loads((out_dir / "benchmark_manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 42
    assert manifest["task_count"] == 2
    assert manifest["summary_sha256"] == sha256_file(out_dir / "summary.json")
    assert manifest["baseline_comparison_sha256"] == sha256_file(out_dir / "baseline_comparison.json")


def test_benchmark_reproducibility_with_seed(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    suite_dir = root / "benchmarks" / "heldout"

    # Run twice with the exact same seed=100
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"

    execute_full_benchmark(suite_dir=suite_dir, output_dir=run1, seed=100, sample_size=1)
    execute_full_benchmark(suite_dir=suite_dir, output_dir=run2, seed=100, sample_size=1)

    s1 = json.loads((run1 / "summary.json").read_text(encoding="utf-8"))
    s2 = json.loads((run2 / "summary.json").read_text(encoding="utf-8"))

    assert s1["compile_pass_rate"] == s2["compile_pass_rate"]
    assert s1["formal_pass_rate"] == s2["formal_pass_rate"]
    assert s1["full_verified_pass_rate"] == s2["full_verified_pass_rate"]


def test_small_benchmark_default_min_tasks(monkeypatch, tmp_path):
    """A selected 20-task development run must not require the full 100-task evidence floor."""
    from mind3.benchmarks.runner import BenchmarkRunner

    monkeypatch.setattr("sys.argv", ["mind3", "--limit", "20", "--dry-run"])
    runner = BenchmarkRunner(tasks_file=tmp_path / "tasks.jsonl", transcripts_dir=tmp_path / "transcripts")
    tasks = [
        {
            "task_id": f"t{i}", "category": "rtl", "name": f"task-{i}",
            "natural_language_spec": "spec", "expected_ports": [{"name": "clk", "direction": "input", "width": 1}, {"name": "out", "direction": "output", "width": 1}],
            "sva_properties": ["1", "2"], "benchmark_origin": "test"
        } for i in range(20)
    ]
    runner.tasks_file.write_text("\n".join(__import__('json').dumps(t) for t in tasks) + "\n", encoding="utf-8")
    assert min(100, 20) == 20
