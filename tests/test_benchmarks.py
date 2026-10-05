"""Tests for Mind 3.0 benchmark task specifications and transcript validation."""

import json
from pathlib import Path
import pytest

TASKS_FILE = Path(__file__).parent.parent / "benchmarks" / "tasks.jsonl"


def test_benchmark_tasks_file_exists_and_count() -> None:
    """Verify benchmarks/tasks.jsonl exists and contains exactly 50 tasks."""
    assert TASKS_FILE.exists(), f"Benchmark tasks file {TASKS_FILE} does not exist"
    lines = [line.strip() for line in TASKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 50, f"Expected 50 tasks, got {len(lines)}"


def test_benchmark_tasks_schema_and_categories() -> None:
    """Validate schema, category distribution, and SVA properties for each benchmark task."""
    lines = [line.strip() for line in TASKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    categories: dict[str, int] = {}
    task_ids: set[str] = set()

    for line in lines:
        task = json.loads(line)
        
        # Required keys
        for key in ["task_id", "category", "name", "natural_language_spec", "expected_ports", "sva_properties", "benchmark_origin"]:
            assert key in task, f"Task {task.get('task_id')} missing key '{key}'"

        # Unique task_id
        tid = task["task_id"]
        assert tid not in task_ids, f"Duplicate task_id '{tid}' found"
        task_ids.add(tid)

        # Honest origin attribution
        assert "inspired by" in task["benchmark_origin"].lower(), f"Task {tid} must state 'inspired by' to avoid unverified benchmark claims"

        # Category counting
        cat = task["category"]
        categories[cat] = categories.get(cat, 0) + 1

        # Port validation
        ports = task["expected_ports"]
        assert len(ports) >= 2, f"Task {tid} must have at least 2 ports"
        for p in ports:
            assert "name" in p and isinstance(p["name"], str) and len(p["name"]) > 0
            assert p["direction"] in ("input", "output", "inout")
            assert isinstance(p["width"], int) and p["width"] >= 1

        # SVA properties validation (2-5 properties per task specification)
        svas = task["sva_properties"]
        assert isinstance(svas, list), f"Task {tid} sva_properties must be a list"
        assert 2 <= len(svas) <= 5, f"Task {tid} expected 2-5 SVA properties, got {len(svas)}"
        for sva in svas:
            assert isinstance(sva, str) and len(sva) > 0
            assert "assert" in sva or "cover" in sva or "assume" in sva

    # Category breakdown assertions
    assert categories.get("FSM") == 15, f"Expected 15 FSM tasks, got {categories.get('FSM')}"
    assert categories.get("Arithmetic") == 15, f"Expected 15 Arithmetic tasks, got {categories.get('Arithmetic')}"
    assert categories.get("Bus Protocol") == 10, f"Expected 10 Bus Protocol tasks, got {categories.get('Bus Protocol')}"
    assert categories.get("Memory Controller") == 10, f"Expected 10 Memory Controller tasks, got {categories.get('Memory Controller')}"


def test_benchmark_runner_task_loading() -> None:
    """BenchmarkRunner must successfully load all 50 tasks with valid Pydantic models."""
    from mind3.benchmarks.runner import BenchmarkRunner

    runner = BenchmarkRunner()
    tasks = runner.load_tasks()
    assert len(tasks) == 50
    assert tasks[0].task_id.startswith("fsm_")
    prompt = runner.build_task_prompt(tasks[0])
    assert "Expected Interface Ports:" in prompt
    assert "Key Verification Properties to Satisfy:" in prompt


def test_benchmark_transcripts_fixtures_integrity_and_labeling() -> None:
    """All persisted benchmark transcripts must be valid BenchmarkTranscript schemas with truthful labels."""
    from mind3.benchmarks.runner import BenchmarkTranscript

    transcripts_dir = Path(__file__).parent.parent / "benchmarks" / "transcripts"
    assert transcripts_dir.exists(), "benchmarks/transcripts directory must exist"

    transcript_files = sorted(transcripts_dir.glob("*.json"))
    assert len(transcript_files) == 50, f"Expected 50 transcript fixtures, found {len(transcript_files)}"

    for tf in transcript_files:
        raw = json.loads(tf.read_text(encoding="utf-8"))
        transcript = BenchmarkTranscript.model_validate(raw)

        # Truth-in-labeling invariant: all 50 transcripts are uniform schema-validation fixtures
        assert transcript.is_schema_validation_fixture is True
        assert transcript.label == "schema-validation fixture, not real generation output"
        assert "[SCHEMA-VALIDATION FIXTURE - NOT REAL GENERATION OUTPUT]" in (transcript.generated_rtl or "")
        assert transcript.model == "mock-fixture-generator"
        assert transcript.provider == "mock"

        # Tuple structure verification:
        assert transcript.contract is not None
        assert "module_name" in transcript.contract
        assert "ports" in transcript.contract
        assert transcript.generated_rtl is not None
        assert isinstance(transcript.repair_attempts, list)
        assert isinstance(transcript.final_outcome, dict)
        assert "passed" in transcript.final_outcome


def test_benchmark_runner_persistence_roundtrip(tmp_path: Path) -> None:
    """BenchmarkRunner must persist transcripts and load them back identically."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTask

    runner = BenchmarkRunner(transcripts_dir=tmp_path)
    dummy_task = BenchmarkTask(
        task_id="test_mod_01",
        category="FSM",
        name="test_mod",
        natural_language_spec="Test spec for roundtrip verification.",
        expected_ports=[
            {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
            {"name": "out", "direction": "output", "width": 1, "description": "Out"},
        ],
        sva_properties=["assert property (@(posedge clk) out == 0);", "assert property (@(posedge clk) 1'b1);"],
        benchmark_origin="inspired by synthetic test specification",
    )

    fixture = runner.create_schema_validation_fixture(dummy_task, simulated_initial_pass=False, simulated_converged=True)
    saved_path = runner.persist_transcript(fixture)
    assert saved_path.exists()

    reloaded = json.loads(saved_path.read_text(encoding="utf-8"))
    assert reloaded["task_id"] == "test_mod_01"
    assert reloaded["gate_failure_category"] == "FORMAL_INVARIANT_BREACH"
    assert len(reloaded["repair_attempts"]) == 1
    assert reloaded["repair_attempts"][0]["turn"] == 1
    assert reloaded["final_outcome"]["passed"] is True
    assert reloaded["label"] == "schema-validation fixture, not real generation output"


def test_benchmark_runner_extract_transcript_tuple(tmp_path: Path) -> None:
    """BenchmarkRunner must extract the complete 5-tuple from PhaseDriver execution traces."""
    from unittest.mock import MagicMock
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTask
    from mind3.core.types import TraceRecord, TelemetryEvent, PhaseEnum

    runner = BenchmarkRunner(transcripts_dir=tmp_path)
    task = BenchmarkTask(
        task_id="fsm_tuple_test",
        category="FSM",
        name="tuple_test",
        natural_language_spec="Specification for tuple test",
        expected_ports=[
            {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
            {"name": "q", "direction": "output", "width": 1, "description": "Output"},
        ],
        sva_properties=["assert property (@(posedge clk) q == 0);", "assert property (@(posedge clk) 1'b1);"],
        benchmark_origin="inspired by synthetic test specification",
    )

    # Construct mock driver with trace records simulating contract, RTL, verify fail, repair, verify pass
    mock_driver = MagicMock()
    mock_driver.model = "qwen2.5-coder:7b"
    mock_driver.provider = "mock"
    mock_driver.max_repairs = 10

    records = [
        TraceRecord(
            step_index=0,
            phase=PhaseEnum.PARSE,
            prev_hash="0" * 64,
            current_hash="1" * 64,
            event=TelemetryEvent(
                session_id="s1",
                phase=PhaseEnum.PARSE,
                turn=0,
                payload={"role": "Lead Silicon Architect", "module_name": "fsm_tuple_test", "ports": 2},
            ),
        ),
        TraceRecord(
            step_index=1,
            phase=PhaseEnum.EXECUTE,
            prev_hash="1" * 64,
            current_hash="2" * 64,
            event=TelemetryEvent(
                session_id="s1",
                phase=PhaseEnum.EXECUTE,
                turn=0,
                payload={"role": "Principal RTL Design Engineer", "rtl_file": "module fsm_tuple_test; endmodule"},
            ),
        ),
        TraceRecord(
            step_index=2,
            phase=PhaseEnum.VERIFY,
            prev_hash="2" * 64,
            current_hash="3" * 64,
            event=TelemetryEvent(
                session_id="s1",
                phase=PhaseEnum.VERIFY,
                turn=0,
                payload={"passed": False, "error_category": "LATCH_INFERRED", "failure_reason": "Inferred latch in comb block"},
            ),
        ),
        TraceRecord(
            step_index=3,
            phase=PhaseEnum.MODEL_CALL,
            prev_hash="3" * 64,
            current_hash="4" * 64,
            event=TelemetryEvent(
                session_id="s1",
                phase=PhaseEnum.MODEL_CALL,
                turn=1,
                payload={"role": "Targeted RTL Repair Loop", "turn": 1, "guidance": "Fix latch"},
            ),
        ),
        TraceRecord(
            step_index=4,
            phase=PhaseEnum.EXECUTE,
            prev_hash="4" * 64,
            current_hash="5" * 64,
            event=TelemetryEvent(
                session_id="s1",
                phase=PhaseEnum.EXECUTE,
                turn=1,
                payload={"role": "Targeted RTL Repair Loop", "rtl_file": "module fsm_tuple_test; /* fixed */ endmodule"},
            ),
        ),
        TraceRecord(
            step_index=5,
            phase=PhaseEnum.VERIFY,
            prev_hash="5" * 64,
            current_hash="6" * 64,
            event=TelemetryEvent(
                session_id="s1",
                phase=PhaseEnum.VERIFY,
                turn=1,
                payload={"passed": True, "error_category": None, "failure_reason": None, "gate_reports": [{"gate": 1, "passed": True}]},
            ),
        ),
        TraceRecord(
            step_index=6,
            phase=PhaseEnum.REPAIR_OR_FINISH,
            prev_hash="6" * 64,
            current_hash="7" * 64,
            event=TelemetryEvent(
                session_id="s1",
                phase=PhaseEnum.REPAIR_OR_FINISH,
                turn=1,
                payload={"status": "SILICON_VERIFIED", "turns_taken": 2, "silicon_verified": True},
            ),
        ),
    ]
    mock_driver.transcript = records

    extracted = runner.extract_transcript_tuple(task, mock_driver, final_passed=True)
    assert extracted.task_id == "fsm_tuple_test"
    assert extracted.contract == {"role": "Lead Silicon Architect", "module_name": "fsm_tuple_test", "ports": 2}
    assert extracted.generated_rtl == "module fsm_tuple_test; endmodule"
    assert extracted.gate_failure_category == "LATCH_INFERRED"
    assert len(extracted.repair_attempts) == 1
    assert extracted.repair_attempts[0].turn == 1
    assert extracted.repair_attempts[0].guidance == "Fix latch"
    assert extracted.repair_attempts[0].repaired_rtl == "module fsm_tuple_test; /* fixed */ endmodule"
    assert extracted.repair_attempts[0].passed is True
    assert extracted.final_outcome["passed"] is True
    assert extracted.final_outcome["status"] == "SILICON_VERIFIED"
    assert extracted.final_outcome["turns_taken"] == 2




def test_benchmark_evaluator_excludes_fixtures_and_computes_confidence_intervals(tmp_path: Path) -> None:
    """Evaluation must ignore mock fixtures and report bounded uncertainty for real outputs."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner(transcripts_dir=tmp_path)
    fixtures = runner.load_transcripts(Path(__file__).parent.parent / "benchmarks" / "transcripts")[:2]
    real = [
        BenchmarkTranscript(
            task_id="real_01", category="FSM", name="real", natural_language_spec="spec", model="model-a", provider="openrouter",
            gate_failure_category=None,
            final_outcome={"passed": True, "silicon_verified": True, "turns_taken": 1, "gate_reports": [{"gate": "Gate 3", "passed": True}]},
            environment={"eda_versions": {"yosys": "0.69"}},
        ),
        BenchmarkTranscript(
            task_id="real_02", category="FSM", name="real2", natural_language_spec="spec", model="model-a", provider="openrouter",
            gate_failure_category="FORMAL_INVARIANT_BREACH",
            final_outcome={"passed": False, "silicon_verified": False, "turns_taken": 2, "gate_reports": [{"gate": "Gate 3", "passed": True}]},
            environment={"eda_versions": {"yosys": "0.69"}},
        ),
    ]
    summary = runner.evaluate_transcripts([*fixtures, *real])
    assert summary.transcript_count == 4
    assert summary.fixture_count == 2
    assert summary.real_transcript_count == 2
    assert summary.initial_pass_count == 1
    assert summary.functional_pass_count == 2
    assert summary.full_verified_pass_count == 1
    assert summary.initial_pass_ci95[0] < 0.5 < summary.initial_pass_ci95[1]
    assert summary.actual_real_transcripts == 2
    assert summary.live_provenance is True
    assert summary.evidence_tier == "diagnostic"
    assert summary.performance_claim_valid is False


def test_benchmark_report_writes_json_markdown_and_html(tmp_path: Path) -> None:
    from mind3.benchmarks.runner import BenchmarkRunner

    runner = BenchmarkRunner()
    summary = runner.evaluate_transcripts([])
    paths = runner.write_report(summary, tmp_path)
    assert len(paths) == 3
    assert all(p.exists() for p in paths)
    assert paths[2].suffix == ".html"
    assert "Mind 3.0 Benchmark Report" in paths[2].read_text(encoding="utf-8")


def test_benchmark_baselines_require_matching_task_set(tmp_path: Path) -> None:
    from mind3.benchmarks.runner import BenchmarkRunner

    runner = BenchmarkRunner()
    summary = runner.evaluate_transcripts([])
    valid = [{
        "name": "direct-prompting",
        "task_set_sha256": summary.task_set_sha256,
        "real_task_count": 100,
        "functional_pass_rate": 0.45,
        "full_verified_pass_rate": 0.20,
        "source": "example-only-no-score-claim",
    }]
    baseline_path = tmp_path / "baselines.json"
    baseline_path.write_text(json.dumps(valid), encoding="utf-8")
    baselines = runner.load_baselines(baseline_path, summary.task_set_sha256)
    attached = runner.attach_baselines(summary, baselines)
    assert attached.baseline_comparisons[0]["name"] == "direct-prompting"
    assert attached.baseline_comparisons[0]["functional_delta_vs_mind3"] == -0.45


def test_unit_dev20_run_labeled_diagnostic_and_not_release_eligible() -> None:
    """A 20-task development run must be labeled diagnostic and cannot be release-eligible."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    # 20 real transcripts with a non-mock model provider
    real_20 = [
        BenchmarkTranscript(
            task_id=f"fsm_{i:02d}",
            category="FSM",
            name=f"fsm_{i}",
            natural_language_spec="spec",
            is_schema_validation_fixture=False,
            model="qwen2.5-coder:7b",
            provider="ollama",
            final_outcome={"passed": False, "turns_taken": 1, "silicon_verified": False},
        )
        for i in range(20)
    ]
    # Even if required_min_tasks is default 100, evidence_tier MUST be diagnostic
    summary_default = runner.evaluate_transcripts(real_20)
    assert summary_default.evidence_tier == "diagnostic"
    assert summary_default.live_provenance is True
    assert summary_default.actual_real_transcripts == 20
    assert summary_default.required_min_tasks == 100
    assert summary_default.performance_claim_valid is False
    assert "not eligible for release claims" in summary_default.caveat.lower()
    assert "mandatory release threshold" in summary_default.caveat.lower()

    # Even if required_min_tasks is explicitly set to 20, tier MUST remain diagnostic
    summary_20 = runner.evaluate_transcripts(real_20, required_min_tasks=20)
    assert summary_20.evidence_tier == "diagnostic"
    assert summary_20.actual_real_transcripts == 20
    assert summary_20.required_min_tasks == 20
    assert summary_20.performance_claim_valid is False
    assert "mandatory release threshold of at least 100 real tasks" in summary_20.caveat.lower()

    # If 100 tasks are evaluated but required_min_tasks is configured below 100
    real_100 = [
        BenchmarkTranscript(
            task_id=f"fsm_{i:03d}",
            category="FSM",
            name=f"fsm_{i}",
            natural_language_spec="spec",
            is_schema_validation_fixture=False,
            model="qwen2.5-coder:7b",
            provider="ollama",
            final_outcome={"passed": False, "turns_taken": 1, "silicon_verified": False},
        )
        for i in range(100)
    ]
    summary_100_low_min = runner.evaluate_transcripts(real_100, required_min_tasks=50)
    assert summary_100_low_min.evidence_tier == "diagnostic"
    assert "below the mandatory 100-task release floor" in summary_100_low_min.caveat.lower()


def test_unit_dev_run_cannot_accidentally_become_release_eligible() -> None:
    """A dev run with n_total > 0 and non-mock provider cannot be release-eligible."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    # 5 tasks that all pass with a real provider
    passing_5 = [
        BenchmarkTranscript(
            task_id=f"task_{i}",
            category="Arithmetic",
            name=f"task_{i}",
            natural_language_spec="spec",
            is_schema_validation_fixture=False,
            model="qwen2.5-coder:7b",
            provider="openrouter",
            final_outcome={"passed": True, "turns_taken": 1, "silicon_verified": True},
        )
        for i in range(5)
    ]
    summary = runner.evaluate_transcripts(passing_5)
    assert summary.full_verified_pass_rate == 1.0
    assert summary.evidence_tier == "diagnostic"
    assert summary.performance_claim_valid is False
    assert summary.actual_real_transcripts == 5
    assert summary.live_provenance is True


def test_unit_live_provenance_strictly_distinguishes_mock_vs_real() -> None:
    """live_provenance is False for mock inference/fixtures, and True only for real inference."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    mock_transcripts = [
        BenchmarkTranscript(
            task_id="mock_01",
            category="FSM",
            name="mock_01",
            natural_language_spec="spec",
            is_schema_validation_fixture=True,
            model="mock",
            provider="mock",
            final_outcome={"passed": True, "silicon_verified": True},
        ),
        BenchmarkTranscript(
            task_id="mock_02",
            category="FSM",
            name="mock_02",
            natural_language_spec="spec",
            is_schema_validation_fixture=False,
            model="mock",
            provider="mock",
            final_outcome={"passed": False, "silicon_verified": False},
        ),
    ]
    summary_mock = runner.evaluate_transcripts(mock_transcripts)
    assert summary_mock.live_provenance is False
    assert summary_mock.actual_real_transcripts == 0
    assert summary_mock.evidence_tier == "diagnostic"
    assert summary_mock.performance_claim_valid is False
    assert "zero live model inferences" in summary_mock.caveat.lower()

    # Real non-mock inference
    real_transcript = BenchmarkTranscript(
        task_id="real_01",
        category="FSM",
        name="real_01",
        natural_language_spec="spec",
        is_schema_validation_fixture=False,
        model="qwen2.5-coder:7b",
        provider="ollama",
        final_outcome={"passed": False, "silicon_verified": False},
    )
    summary_real = runner.evaluate_transcripts([real_transcript])
    assert summary_real.live_provenance is True
    assert summary_real.actual_real_transcripts == 1


def test_unit_actual_real_transcripts_is_not_simply_task_count() -> None:
    """actual_real_transcripts counts only real non-mock transcripts, not task spec count or fixture rows."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    mixed = [
        BenchmarkTranscript(
            task_id="fix_01", category="FSM", name="f1", natural_language_spec="s",
            is_schema_validation_fixture=True, model="mock", provider="mock",
            final_outcome={"passed": True, "silicon_verified": True},
        ),
        BenchmarkTranscript(
            task_id="fix_02", category="FSM", name="f2", natural_language_spec="s",
            is_schema_validation_fixture=True, model="mock", provider="mock",
            final_outcome={"passed": True, "silicon_verified": True},
        ),
        BenchmarkTranscript(
            task_id="mock_run_01", category="FSM", name="m1", natural_language_spec="s",
            is_schema_validation_fixture=False, model="mock", provider="mock",
            final_outcome={"passed": True, "silicon_verified": True},
        ),
        BenchmarkTranscript(
            task_id="real_run_01", category="FSM", name="r1", natural_language_spec="s",
            is_schema_validation_fixture=False, model="real-model", provider="openrouter",
            final_outcome={"passed": True, "silicon_verified": True},
        ),
    ]
    summary = runner.evaluate_transcripts(mixed)
    assert summary.transcript_count == 4
    assert summary.fixture_count == 2
    assert summary.actual_real_transcripts == 1  # only real_run_01 is real non-mock
    assert summary.live_provenance is True


def test_unit_persisted_summary_contains_required_fields_and_caveat(tmp_path: Path) -> None:
    """summary.json must contain required_min_tasks, actual_real_transcripts, evidence_tier, caveat, live_provenance."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    transcripts = [
        BenchmarkTranscript(
            task_id="task_01", category="FSM", name="t1", natural_language_spec="s",
            is_schema_validation_fixture=False, model="qwen", provider="ollama",
            final_outcome={"passed": False, "silicon_verified": False},
        )
    ]
    summary = runner.evaluate_transcripts(transcripts, required_min_tasks=20, diagnostic=True)
    summary_path, md_path, html_path = runner.write_report(summary, tmp_path)

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "required_min_tasks" in data
    assert data["required_min_tasks"] == 20
    assert "actual_real_transcripts" in data
    assert data["actual_real_transcripts"] == 1
    assert "evidence_tier" in data
    assert data["evidence_tier"] == "diagnostic"
    assert "live_provenance" in data
    assert data["live_provenance"] is True
    assert "caveat" in data
    assert len(data["caveat"]) > 0
    assert "diagnostic mode" in data["caveat"].lower()

    # Check markdown and html output
    md_text = md_path.read_text(encoding="utf-8")
    assert "Evidence tier: **diagnostic**" in md_text
    assert "Live provenance: **True**" in md_text
    assert "Caveat:" in md_text

    html_text = html_path.read_text(encoding="utf-8")
    assert "Evidence tier: <b>diagnostic</b>" in html_text
    assert "Live provenance: <b>True</b>" in html_text


def test_unit_release_mode_cannot_silently_lower_100_task_minimum() -> None:
    """Release qualification strictly requires at least 100 real tasks; lowering min-tasks forces diagnostic tier."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    # 99 real tasks (one short of 100)
    real_99 = [
        BenchmarkTranscript(
            task_id=f"t_{i}", category="FSM", name=f"t_{i}", natural_language_spec="s",
            is_schema_validation_fixture=False, model="qwen", provider="ollama",
            final_outcome={"passed": True, "silicon_verified": True},
        )
        for i in range(99)
    ]
    # Even if someone attempts to pass required_min_tasks=99, tier MUST be diagnostic
    summary_99 = runner.evaluate_transcripts(real_99, required_min_tasks=99)
    assert summary_99.evidence_tier == "diagnostic"
    assert summary_99.performance_claim_valid is False

    # 100 real tasks with release threshold meets release-eligible
    real_100 = [
        BenchmarkTranscript(
            task_id=f"t_{i}", category="FSM", name=f"t_{i}", natural_language_spec="s",
            is_schema_validation_fixture=False, model="qwen", provider="ollama",
            final_outcome={"passed": True, "silicon_verified": True},
        )
        for i in range(100)
    ]
    summary_100 = runner.evaluate_transcripts(real_100, required_min_tasks=100, diagnostic=False)
    assert summary_100.evidence_tier == "release-eligible"
    assert summary_100.performance_claim_valid is True
    assert "Release-eligible evaluation" in summary_100.caveat


def test_unit_diagnostic_flag_changes_evidence_tier_rather_than_bypassing() -> None:
    """Passing diagnostic=True on a 100+ task run forces evidence_tier='diagnostic'."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    real_100 = [
        BenchmarkTranscript(
            task_id=f"t_{i}", category="FSM", name=f"t_{i}", natural_language_spec="s",
            is_schema_validation_fixture=False, model="qwen", provider="ollama",
            final_outcome={"passed": True, "silicon_verified": True},
        )
        for i in range(100)
    ]
    summary_diag = runner.evaluate_transcripts(real_100, required_min_tasks=100, diagnostic=True)
    assert summary_diag.evidence_tier == "diagnostic"
    assert summary_diag.performance_claim_valid is False
    assert "explicitly executed in diagnostic mode" in summary_diag.caveat.lower()


def test_benchmark_methodology_records_parser_mode() -> None:
    """Benchmark summaries must record parser_mode and never equate lenient with strict."""
    from mind3.benchmarks.runner import BenchmarkRunner, BenchmarkTranscript

    runner = BenchmarkRunner()
    real_5 = [
        BenchmarkTranscript(
            task_id=f"t_{i}", category="FSM", name=f"t_{i}", natural_language_spec="s",
            is_schema_validation_fixture=False, model="qwen", provider="ollama",
            final_outcome={"passed": True, "silicon_verified": True},
            environment={"parser_mode": "lenient"},
        )
        for i in range(5)
    ]
    # Default is strict.
    summary_default = runner.evaluate_transcripts(real_5)
    assert summary_default.methodology["parser_mode"] == "strict"
    # Explicit lenient is recorded and distinguished from strict.
    summary_lenient = runner.evaluate_transcripts(real_5, parser_mode="lenient")
    assert summary_lenient.methodology["parser_mode"] == "lenient"
    assert "not equivalent" in summary_lenient.methodology["parser_mode_note"]
    assert summary_lenient.methodology["observed_parser_modes"] == ["lenient"]
    # Invalid modes are rejected loudly.
    import pytest
    with pytest.raises(ValueError):
        runner.evaluate_transcripts(real_5, parser_mode="auto")
