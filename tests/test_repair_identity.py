"""Regression tests for MIND-3.0 end-to-end RTL repair improvements (C1-C5).

Covers, with mocks only for control flow (never presented as real EDA passes):
1.  identical repair candidate detection (raw + normalized)
2.  distinct candidate handling (different hash is not a correctness signal)
3.  reproducible candidate hashing
4.  synchronous-reset sensitivity validation (arbiter_02 class defect)
5.  runner transcript captures Independent repair EXECUTE payloads
6.  stale repaired_rtl is not reused across turns
7.  repair prompt minimal-diff discipline keeps the output contract intact
8.  evidence with missing counterexample still builds a prompt (fail-closed)
9.  malformed model responses are rejected (strict parser)
10. missing-EDA-binary detection stays fail-closed
11. bounded retry exhaustion with unchanged candidates recorded
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from mind3.benchmarks.runner import BenchmarkTask, BenchmarkRunner
from mind3.core.contracts import (
    VerificationFailureEvidence,
    VerificationRepairer,
    contract_from_benchmark_record,
    validate_rtl_against_contract,
)
from mind3.core.driver import (
    ModelResponseParseError,
    PhaseDriver,
    _candidate_identity,
    _normalize_rtl_for_identity,
    _parse_model_code_response,
    _sha256_text,
)
from mind3.core.types import PhaseEnum
from mind3.core.verifier import _is_binary_missing


ARBITER_RTL = (
    "module arbiter_02 (\n"
    "  input  logic clk,\n"
    "  input  logic rst_n,\n"
    "  input  logic [3:0] req,\n"
    "  output logic [3:0] gnt\n"
    ");\n"
    "  always_ff @(posedge clk or negedge rst_n) begin\n"
    "    if (!rst_n) begin\n"
    "      gnt <= 4'b0;\n"
    "    end else begin\n"
    "      gnt[0] <= req[0];\n"
    "      gnt[1] <= ~req[0] & req[1];\n"
    "      gnt[2] <= ~req[0] & ~req[1] & req[2];\n"
    "      gnt[3] <= ~req[0] & ~req[1] & ~req[2] & req[3];\n"
    "    end\n"
    "  end\n"
    "endmodule\n"
)


def _arbiter_contract():
    return contract_from_benchmark_record(
        {
            "task_id": "arbiter_02",
            "natural_language_spec": "4-client fixed priority arbiter",
            "expected_ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "req", "direction": "input", "width": 4},
                {"name": "gnt", "direction": "output", "width": 4},
            ],
            "clock_reset_assumptions": "clk rising edge; active-low synchronous rst_n",
            "functional_requirements": ["4-client fixed priority arbiter"],
            "expected_properties": [
                "assert property (@(posedge clk) req[0] |-> gnt[0]);",
                "assert property (@(posedge clk) $onehot0(gnt));",
            ],
            "verification_requirements": [],
            "parameters": {},
        }
    )


# 1. identical candidate -----------------------------------------------------
def test_identical_candidate_detected_raw_and_normalized() -> None:
    identity = _candidate_identity(ARBITER_RTL, ARBITER_RTL)
    assert identity["identical_raw"] is True
    assert identity["identical_normalized"] is True
    assert identity["current_sha256"] == identity["candidate_sha256"]
    assert identity["current_normalized_sha256"] == identity["candidate_normalized_sha256"]
    # Original bytes preserved: helper never mutates its inputs.
    assert ARBITER_RTL.startswith("module arbiter_02")


def test_whitespace_comment_only_resubmission_detected_via_normalization() -> None:
    variant = "// tidy comment\n" + ARBITER_RTL.replace("  input", "   input ")
    identity = _candidate_identity(ARBITER_RTL, variant)
    assert identity["identical_raw"] is False
    assert identity["identical_normalized"] is True


# 2. distinct candidate ------------------------------------------------------
def test_distinct_candidate_not_flagged_and_hash_is_not_correctness() -> None:
    fixed = ARBITER_RTL.replace(
        "always_ff @(posedge clk or negedge rst_n)",
        "always_ff @(posedge clk)",
    )
    identity = _candidate_identity(ARBITER_RTL, fixed)
    assert identity["identical_raw"] is False
    assert identity["identical_normalized"] is False
    assert identity["candidate_sha256"] != identity["current_sha256"]
    # A different hash never implies the candidate passes verification.


# 3. hashing reproducibility -------------------------------------------------
def test_candidate_hashing_reproducible() -> None:
    assert _sha256_text(ARBITER_RTL) == _sha256_text(ARBITER_RTL)
    assert _sha256_text(ARBITER_RTL) != _sha256_text(ARBITER_RTL + " ")
    assert _normalize_rtl_for_identity(ARBITER_RTL) == _normalize_rtl_for_identity(ARBITER_RTL + "\n")


# 4. synchronous-reset sensitivity -------------------------------------------
def test_sync_reset_in_sensitivity_list_flagged() -> None:
    contract = _arbiter_contract()
    assert contract.reset is not None and contract.reset.synchronous is True
    violations = validate_rtl_against_contract(contract, ARBITER_RTL)
    assert any(
        v["category"] == "CLOCK_RESET_ERROR" and "sensitivity list" in v["message"]
        for v in violations
    ), f"expected CLOCK_RESET_ERROR, got {violations}"


def test_sync_reset_inside_block_passes_sensitivity_check() -> None:
    contract = _arbiter_contract()
    sync_rtl = ARBITER_RTL.replace(
        "always_ff @(posedge clk or negedge rst_n)",
        "always_ff @(posedge clk)",
    )
    violations = validate_rtl_against_contract(contract, sync_rtl)
    assert not any(
        v["category"] == "CLOCK_RESET_ERROR" and "sensitivity list" in v["message"]
        for v in violations
    )


# 5/6. runner transcript capture ---------------------------------------------
def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_id="arbiter_02",
        category="arbiters",
        name="x",
        natural_language_spec="spec",
        expected_ports=[
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst_n", "direction": "input", "width": 1},
        ],
        sva_properties=[
            "assert property (@(posedge clk) req[0] |-> gnt[0]);",
            "assert property (@(posedge clk) $onehot0(gnt));",
        ],
        benchmark_origin="development-20",
        functional_requirements=[],
        verification_requirements=[],
    )


def _fake_driver_with_traces(records: list) -> SimpleNamespace:
    return SimpleNamespace(
        transcript=records,
        verifier=SimpleNamespace(detected_versions={}),
        _raw_repair_responses=["raw-repair-bytes"],
        _raw_initial_responses=["raw-initial-bytes"],
        _decode_events=[],
        model="qwen2.5-coder:7b",
        provider="ollama",
        max_repairs=3,
        workspace=Path(tempfile.gettempdir()),
        transcript_file=Path(tempfile.gettempdir()) / "nope.jsonl",
        sandbox=SimpleNamespace(__class__=type("S", (), {})),
    )


def _trace(phase: PhaseEnum, payload: dict, turn: int = 1):
    from mind3.core.types import TelemetryEvent, TraceRecord

    event = TelemetryEvent(session_id="s", phase=phase, turn=turn, payload=payload, timestamp=0.0)
    return TraceRecord(step_index=0, phase=phase, prev_hash="0" * 64, current_hash="a" * 64, event=event)


def test_runner_captures_independent_repair_execute_payload() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = BenchmarkRunner(
            tasks_file=Path(tmpdir) / "tasks.jsonl",
            transcripts_dir=Path(tmpdir) / "t",
        )
        (Path(tmpdir) / "tasks.jsonl").write_text("{}\n", encoding="utf-8")
        task = _task()
        driver = _fake_driver_with_traces(
            [
                _trace(
                    PhaseEnum.MODEL_CALL,
                    {"role": "Independent RTL Verification Repair Engineer", "guidance": "g1"},
                    turn=1,
                ),
                _trace(
                    PhaseEnum.EXECUTE,
                    {"role": "Independent RTL Verification Repair Engineer", "content": ARBITER_RTL},
                    turn=1,
                ),
                _trace(
                    PhaseEnum.VERIFY,
                    {"passed": False, "error_category": "FORMAL_INVARIANT_BREACH",
                     "failure_reason": "breach", "gate_reports": []},
                    turn=1,
                ),
            ]
        )
        driver.decode_config = lambda: {}  # type: ignore[attr-defined]
        transcript = runner.extract_transcript_tuple(task, driver, False)  # type: ignore[arg-type]
        assert len(transcript.repair_attempts) == 1
        assert transcript.repair_attempts[0].repaired_rtl == ARBITER_RTL
        assert transcript.repair_attempts[0].raw_repair_response == "raw-repair-bytes"


def test_runner_does_not_reuse_stale_repaired_rtl() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = BenchmarkRunner(
            tasks_file=Path(tmpdir) / "tasks.jsonl",
            transcripts_dir=Path(tmpdir) / "t",
        )
        (Path(tmpdir) / "tasks.jsonl").write_text("{}\n", encoding="utf-8")
        task = _task()
        driver = _fake_driver_with_traces(
            [
                _trace(
                    PhaseEnum.EXECUTE,
                    {"role": "Independent RTL Verification Repair Engineer", "content": ARBITER_RTL},
                    turn=1,
                ),
                _trace(
                    PhaseEnum.VERIFY,
                    {"passed": False, "error_category": "FORMAL_INVARIANT_BREACH",
                     "failure_reason": "b1", "gate_reports": []},
                    turn=1,
                ),
                # Second VERIFY with no preceding EXECUTE (e.g. parse failure path).
                _trace(
                    PhaseEnum.VERIFY,
                    {"passed": False, "error_category": "RESPONSE_PARSE_FAILURE",
                     "failure_reason": "b2", "gate_reports": []},
                    turn=2,
                ),
            ]
        )
        driver.decode_config = lambda: {}  # type: ignore[attr-defined]
        transcript = runner.extract_transcript_tuple(task, driver, False)  # type: ignore[arg-type]
        assert len(transcript.repair_attempts) == 2
        assert transcript.repair_attempts[0].repaired_rtl == ARBITER_RTL
        assert transcript.repair_attempts[1].repaired_rtl is None


# 7. repair prompt discipline -------------------------------------------------
def test_repair_prompt_has_minimal_diff_discipline_and_output_contract() -> None:
    contract = _arbiter_contract()
    evidence = VerificationFailureEvidence(
        gate="Gate 2: SymbiYosys Formal Property Verification",
        category="FORMAL_INVARIANT_BREACH",
        stage="formal",
        tool="sby",
        error="Formal invariant violated at cycle step T=2.",
        failing_property="contract_property_1",
        failing_step="2",
        reset_state="rst_n active_low synchronous",
        clock_state="clk posedge",
        expected_behavior="contract_property_1: req[0] -> gnt[0]",
        observed_behavior="Property contract_property_1 failed at step 2",
        contract=contract.model_dump(mode="json"),
        attempt=1,
    )
    prompt = VerificationRepairer.build_prompt(contract, ARBITER_RTL, evidence)
    assert "smallest targeted correction" in prompt["system"]
    assert "Never resubmit the current RTL unchanged" in prompt["system"]
    assert "complete corrected SystemVerilog module" in prompt["system"]
    assert "rst_n active_low synchronous" in prompt["user"]
    assert "clk posedge" in prompt["user"]


# 8. missing counterexample ---------------------------------------------------
def test_repair_prompt_with_missing_counterexample_is_fail_closed() -> None:
    contract = _arbiter_contract()
    evidence = VerificationFailureEvidence(
        gate="Gate 2: SymbiYosys Formal Property Verification",
        category="FORMAL_INVARIANT_BREACH",
        stage="formal",
        tool="sby",
        error="Formal invariant violated.",
        contract=contract.model_dump(mode="json"),
        attempt=1,
    )
    prompt = VerificationRepairer.build_prompt(contract, ARBITER_RTL, evidence)
    assert "FORMAL_INVARIANT_BREACH" in prompt["user"]
    assert ARBITER_RTL in prompt["user"]


# 9. malformed responses -------------------------------------------------------
def test_strict_parser_rejects_prose_without_module() -> None:
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(
            "I fixed the arbiter by changing the grant logic slightly.",
            default_module_name="arbiter_02",
            parser_mode="strict",
        )


def test_strict_parser_accepts_exact_module() -> None:
    out = _parse_model_code_response(
        ARBITER_RTL, default_module_name="arbiter_02", parser_mode="strict"
    )
    assert "module arbiter_02" in out and "endmodule" in out


# 10. missing tool stays fail-closed -------------------------------------------
def test_binary_missing_detection_fail_closed() -> None:
    proc = SimpleNamespace(returncode=127, stdout="", stderr="sby: command not found")
    assert _is_binary_missing(proc, "sby") is True
    proc_ok = SimpleNamespace(returncode=0, stdout="SBY v0.69", stderr="")
    assert _is_binary_missing(proc_ok, "sby") is False


# 11. bounded exhaustion with unchanged tracking ---------------------------------
def test_repair_loop_records_unchanged_candidate_and_stays_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Uses the real SiliconSignoffVerifier Gate 1 structural path (deterministic,
    # no EDA binaries needed): ARBITER_RTL carries an async sensitivity list
    # against a synchronous contract, so Gate 1 fails CLOCK_RESET_ERROR before
    # any EDA stage. Every repair echoes the same RTL, exercising C1 tracking.
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        contract = _arbiter_contract()

        from mind3.core.verifier import SiliconSignoffVerifier

        verifier = SiliconSignoffVerifier(top_module="arbiter_02", contract=contract)
        driver = PhaseDriver(
            session_id="unchanged-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            model="qwen2.5-coder:7b",
            provider="ollama",
        )
        # Initial generation: valid module; every repair echoes it identically
        # (modulo the parser's trailing-newline strip, caught by normalization).
        monkeypatch.setattr(
            driver,
            "_query_model",
            lambda messages, **kwargs: ARBITER_RTL,
        )
        ok = driver.run_silicon_pipeline("build arbiter", contract_override=contract)
        assert ok is False
        assert driver._unchanged_repair_count >= 1
        assert driver._candidate_hashes, "candidate hashes must be recorded"
        first = driver._candidate_hashes[0]
        assert first["identical_normalized"] is True
        # Original bytes preserved alongside normalized hashes for auditability.
        assert "candidate_normalized_sha256" in first and "candidate_sha256" in first
        # Bounded: compile stage budget is 3 and the loop terminated honestly.
        assert driver._stage_repair_attempts["compile"] <= 3
        finishes = [r for r in driver.transcript if r.phase == PhaseEnum.REPAIR_OR_FINISH]
        assert finishes and finishes[-1].event.payload.get("status") == "ROLLED_BACK"
        # Failure category preserved across turns, never overwritten or
        # downgraded to pass: every VERIFY trace keeps CLOCK_RESET_ERROR.
        verify_payloads = [
            r.event.payload for r in driver.transcript if r.phase == PhaseEnum.VERIFY
        ]
        assert verify_payloads
        assert all(
            p.get("error_category") == "CLOCK_RESET_ERROR" for p in verify_payloads
        )
        # EXECUTE traces record the unchanged-candidate flag deterministically.
        execute_payloads = [
            r.event.payload
            for r in driver.transcript
            if r.phase == PhaseEnum.EXECUTE
            and r.event.payload.get("role") == "Independent RTL Verification Repair Engineer"
        ]
        assert execute_payloads and all(
            p.get("unchanged_candidate") is True for p in execute_payloads
        )
        driver.close()
