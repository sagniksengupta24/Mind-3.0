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

        # Truth-in-labeling invariant
        if transcript.is_schema_validation_fixture:
            assert transcript.label == "schema-validation fixture, not real generation output"
            assert "[SCHEMA-VALIDATION FIXTURE - NOT REAL GENERATION OUTPUT]" in (transcript.generated_rtl or "")
        else:
            assert transcript.label == "real generation output"
            assert transcript.model != "mock-fixture-generator"
            assert transcript.provider != "mock"

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


