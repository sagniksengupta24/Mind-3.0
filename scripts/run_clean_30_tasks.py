#!/usr/bin/env python3
"""Mind 3.0 Clean 30-Task Benchmark Execution (Phase 6).

Executes the first 30 VerilogEval v2 human tasks under qwen2.5-coder:30b (temp 0).
- Pure clean run into a brand new versioned directory: artifacts/P6/run_30_results/
- Cleans stale workspaces, transcripts, formal and coverage artifacts.
- Compares SHA-256 of graded RTL, verified RTL, and transcript RTL.
- Classifies each task into exactly one failure class per Section 4.
- Produces artifacts/P6/results.csv with 30 rows and log paths.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

MIND3_ROOT = Path(os.environ.get("MIND3_ROOT", Path(__file__).resolve().parents[1])).resolve()
SCRATCH_DIR = Path(os.environ.get("MIND3_BENCHMARK_ROOT", MIND3_ROOT.parent / "benchmark_scratch")).resolve()
EDA_PATH = os.environ.get("MIND3_EDA_BIN_PATH", os.environ.get("PATH", ""))
os.environ["PATH"] = f"{EDA_PATH}:{os.environ.get('PATH', '')}"

sys.path.insert(0, str(MIND3_ROOT / "src"))
sys.path.insert(0, str(SCRATCH_DIR))

from mind3.core.driver import PhaseDriver
from mind3.core.types import PhaseEnum
from mind3.core.verifier import SiliconSignoffVerifier
from run_benchmarks import (
    LIBERTY_PATH,
    VERILOG_EVAL_DIR,
    grade_verilog_eval,
    sanitize_extracted_verilog,
)

RESULTS_BASE = Path(os.environ.get("MIND3_ARTIFACTS_DIR", MIND3_ROOT / "artifacts")) / "P6"
RUN_30_DIR = RESULTS_BASE / "run_30_results"
WORKSPACES_DIR = RUN_30_DIR / "workspaces"
GRADES_DIR = RUN_30_DIR / "grades"
LOGS_DIR = RESULTS_BASE / "logs"

RESULTS_CSV = RESULTS_BASE / "results.csv"


def extract_gate_details(driver: PhaseDriver) -> tuple[str, bool, dict[str, str], int]:
    """Extract (final_rtl, internal_passed, gate_statuses, repair_turns)."""
    final_rtl = ""
    internal_passed = False
    gate_statuses = {
        "gate1": "SKIPPED",
        "gate2": "SKIPPED",
        "gate3": "SKIPPED",
        "failed_category": None,
    }
    repair_turns = driver.turn

    for rec in driver.transcript:
        payload = rec.event.payload
        if rec.phase == PhaseEnum.EXECUTE:
            role = payload.get("role")
            if role in ("Principal RTL Design Engineer", "Targeted RTL Repair Loop"):
                content = payload.get("content") or payload.get("rtl_file")
                if isinstance(content, str):
                    final_rtl = content
                elif isinstance(content, dict) and "content" in content:
                    final_rtl = str(content["content"])
        elif rec.phase == PhaseEnum.VERIFY:
            reports = payload.get("gate_reports", [])
            for rep in reports:
                gname = rep.get("gate", "")
                st = "PASS" if rep.get("passed") else "FAIL"
                if "Gate 1:" in gname:
                    gate_statuses["gate1"] = st
                elif "Gate 2:" in gname:
                    gate_statuses["gate2"] = st
                elif "Gate 3:" in gname:
                    gate_statuses["gate3"] = st
            if not payload.get("passed", False):
                gate_statuses["failed_category"] = payload.get("error_category") or "GATE_FAILURE"
        elif rec.phase == PhaseEnum.REPAIR_OR_FINISH:
            status = payload.get("status", "")
            silicon_verified = payload.get("silicon_verified", False)
            if status in ("SILICON_VERIFIED", "VERIFIED_SUCCESS") or silicon_verified:
                internal_passed = True
                gate_statuses["failed_category"] = None
            else:
                if not gate_statuses["failed_category"]:
                    gate_statuses["failed_category"] = (
                        payload.get("error_category") or payload.get("last_error_category") or status
                    )

    return final_rtl, internal_passed, gate_statuses, repair_turns


def classify_task(
    mind3_passed: bool,
    benchmark_verdict: str,
    gate_statuses: dict[str, str],
    raw_rtl: str,
    diag: str,
) -> str:
    """Classify into exactly one of the 9 failure classes."""
    if mind3_passed:
        if benchmark_verdict == "PASS":
            return "FULL_SIGNOFF"
        else:
            return "BENCHMARK_GRADER_FAILURE"

    failed_cat = gate_statuses.get("failed_category")

    if failed_cat == "RESPONSE_PARSE_FAILURE" or not raw_rtl or "syntax error" in diag.lower():
        if gate_statuses.get("gate1") == "FAIL":
            return "GATE1_GENUINE_RTL_FAILURE"
        return "MODEL_GENERATION_FAILURE"

    if gate_statuses.get("gate1") == "FAIL":
        if benchmark_verdict == "PASS":
            return "GATE1_INFRASTRUCTURE_FAILURE"
        return "GATE1_GENUINE_RTL_FAILURE"

    if gate_statuses.get("gate2") == "FAIL":
        if failed_cat in ("UNSUPPORTED_FORMAL_PROPERTY", "EMPTY_FORMAL_PROPERTY_SET"):
            # If the property cannot be expressed or tool unsupported, model generation defect in contract
            return "GATE2_INFRASTRUCTURE_FAILURE"
        return "GATE2_GENUINE_FORMAL_FAILURE"

    if gate_statuses.get("gate3") == "FAIL":
        if "COVERAGE_BUILD_FAILURE" in str(failed_cat):
            return "GATE3_INFRASTRUCTURE_FAILURE"
        return "GATE3_GENUINE_COVERAGE_FAILURE"

    # Default fallback to model generation failure
    return "MODEL_GENERATION_FAILURE"


def run_clean_30():
    print("=== Mind 3.0 Clean 30-Task Benchmark Execution (Phase 6) ===", flush=True)

    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    GRADES_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    prompt_files = sorted(glob.glob(str(VERILOG_EVAL_DIR / "dataset_spec-to-rtl/*_prompt.txt")))[:30]
    print(f"Total tasks to run: {len(prompt_files)}", flush=True)

    csv_rows = []

    for idx, pf in enumerate(prompt_files, 1):
        p = Path(pf)
        task_id = p.stem.replace("_prompt", "")
        test_file = p.parent / f"{task_id}_test.sv"
        ref_file = p.parent / f"{task_id}_ref.sv"
        raw_prompt = p.read_text(encoding="utf-8").strip()

        print(f"\n[{idx:2d}/30] Executing {task_id}...", flush=True)
        t0 = time.time()

        task_ws = WORKSPACES_DIR / task_id
        if task_ws.exists():
            shutil.rmtree(task_ws)
        task_ws.mkdir(parents=True, exist_ok=True)

        log_path = LOGS_DIR / f"{task_id}.log"
        task_logs = [f"=== Execution Log for {task_id} ===", f"Time: {time.ctime()}"]

        intake_spec = (
            f"Module Name: TopModule\n"
            f"Specification: {raw_prompt}\n"
        )

        verifier = SiliconSignoffVerifier(top_module="TopModule", allow_mock_fallback=False)
        driver = PhaseDriver(
            session_id=f"clean30_{task_id}",
            workspace=task_ws,
            verifier=verifier,
            model="qwen2.5-coder:30b",
            provider="ollama",
            max_repairs=1,
        )

        pipeline_exception = None
        try:
            driver.run_silicon_pipeline(task_prompt=intake_spec, liberty_path=LIBERTY_PATH)
        except Exception as exc:
            pipeline_exception = str(exc)
            task_logs.append(f"Pipeline exception: {exc}")

        transcript_rtl, mind3_passed, gate_statuses, repair_turns = extract_gate_details(driver)

        # Check TopModule.sv in workspace
        dut_file = task_ws / "TopModule.sv"
        verified_rtl = dut_file.read_text(encoding="utf-8") if dut_file.exists() else ""

        sanitized_rtl = sanitize_extracted_verilog(transcript_rtl or verified_rtl, default_module_name="TopModule")
        graded_rtl = sanitized_rtl

        # SHA-256 Consistency Checks
        hash_transcript = hashlib.sha256(transcript_rtl.encode("utf-8")).hexdigest() if transcript_rtl else "NO_TRANSCRIPT_RTL"
        hash_verified = hashlib.sha256(verified_rtl.encode("utf-8")).hexdigest() if verified_rtl else "NO_VERIFIED_RTL"
        hash_graded = hashlib.sha256(graded_rtl.encode("utf-8")).hexdigest() if graded_rtl else "NO_GRADED_RTL"

        sha_match = (hash_transcript == hash_verified == hash_graded) if (transcript_rtl and verified_rtl) else True

        # External Grade
        grade_dir = GRADES_DIR / task_id
        if grade_dir.exists():
            shutil.rmtree(grade_dir)
        grade_dir.mkdir(parents=True, exist_ok=True)

        benchmark_verdict, diag = grade_verilog_eval(graded_rtl, test_file, ref_file, grade_dir)
        elapsed = time.time() - t0

        failure_class = classify_task(
            mind3_passed=mind3_passed,
            benchmark_verdict=benchmark_verdict,
            gate_statuses=gate_statuses,
            raw_rtl=transcript_rtl or verified_rtl,
            diag=diag,
        )

        task_logs.append(f"Duration: {elapsed:.2f}s")
        task_logs.append(f"Benchmark Verdict: {benchmark_verdict}")
        task_logs.append(f"Mind3 Internal Verdict: {'PASS' if mind3_passed else 'FAIL'}")
        task_logs.append(f"Gates: G1={gate_statuses['gate1']}, G2={gate_statuses['gate2']}, G3={gate_statuses['gate3']}")
        task_logs.append(f"Failed Category: {gate_statuses['failed_category']}")
        task_logs.append(f"Failure Class: {failure_class}")
        task_logs.append(f"SHA-256 Transcript: {hash_transcript}")
        task_logs.append(f"SHA-256 Verified:   {hash_verified}")
        task_logs.append(f"SHA-256 Graded:     {hash_graded}")
        task_logs.append(f"SHA Match:          {sha_match}")
        task_logs.append(f"Diagnostic:         {diag}")

        log_path.write_text("\n".join(task_logs) + "\n", encoding="utf-8")

        print(
            f"[{idx:2d}/30] -> {task_id}: GroundTruth={benchmark_verdict} | Mind3={'PASS' if mind3_passed else 'FAIL'} | Class={failure_class} ({elapsed:.1f}s)",
            flush=True,
        )

        row = {
            "task_id": task_id,
            "benchmark_verdict": benchmark_verdict,
            "mind3_signoff": "PASS" if mind3_passed else "FAIL",
            "gate1": gate_statuses["gate1"],
            "gate2": gate_statuses["gate2"],
            "gate3": gate_statuses["gate3"],
            "failure_class": failure_class,
            "sha256_match": str(sha_match),
            "log_path": str(log_path),
        }
        csv_rows.append(row)

    # Write results.csv
    fieldnames = [
        "task_id",
        "benchmark_verdict",
        "mind3_signoff",
        "gate1",
        "gate2",
        "gate3",
        "failure_class",
        "sha256_match",
        "log_path",
    ]
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"\n=== Completed all 30 tasks. CSV saved to {RESULTS_CSV} ===", flush=True)


if __name__ == "__main__":
    run_clean_30()
