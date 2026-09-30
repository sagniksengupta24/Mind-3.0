#!/usr/bin/env python3
"""Run the 7 targeted tasks for Phase 6 and record detailed Gate 1/2/3 breakdown."""

import json
import os
import sys
import time
from pathlib import Path

MIND3_ROOT = Path("/home/mind/Desktop/AI/Mind-3.0")
SCRATCH_DIR = Path("/home/mind/Desktop/AI/benchmark_scratch")
sys.path.insert(0, str(MIND3_ROOT / "src"))
sys.path.insert(0, str(SCRATCH_DIR))

from run_benchmarks import (
    run_single_rtllm_task,
    run_single_verilog_eval_task,
)

TARGETED_TASKS = [
    ("comparator_3bit", "rtllm", SCRATCH_DIR / "RTLLM/Arithmetic/Comparator/comparator_3bit"),
    ("multi_pipe_8bit", "rtllm", SCRATCH_DIR / "RTLLM/Arithmetic/Multiplier/multi_pipe_8bit"),
    ("JC_counter", "rtllm", SCRATCH_DIR / "RTLLM/Control/Counter/JC_counter"),
    ("right_shifter", "rtllm", SCRATCH_DIR / "RTLLM/Memory/Shifter/right_shifter"),
    ("pe", "rtllm", SCRATCH_DIR / "RTLLM/Miscellaneous/RISC-V/pe"),
    ("square_wave", "rtllm", SCRATCH_DIR / "RTLLM/Miscellaneous/Signal generation/square_wave"),
    ("Prob001_zero", "verilog_eval", SCRATCH_DIR / "verilog-eval/dataset_spec-to-rtl/Prob001_zero_prompt.txt"),
]

ARTIFACTS_P6 = Path("/home/mind/Desktop/AI/artifacts/P6")
ARTIFACTS_P6.mkdir(parents=True, exist_ok=True)


def main():
    print("=== Running 7 Targeted Tasks (qwen2.5-coder:30b) ===", flush=True)
    records = []

    for name, task_type, path in TARGETED_TASKS:
        t0 = time.time()
        print(f"\n--- Running {name} ({task_type}) ---", flush=True)
        if task_type == "rtllm":
            rec = run_single_rtllm_task(name, path, "qwen2.5-coder:30b")
        else:
            prompt_file = path
            test_file = prompt_file.parent / f"{name}_test.sv"
            ref_file = prompt_file.parent / f"{name}_ref.sv"
            rec = run_single_verilog_eval_task(name, prompt_file, test_file, ref_file, "qwen2.5-coder:30b")

        dur = time.time() - t0
        print(f"[{name}] Done in {dur:.1f}s | Internal Verdict: {rec['mind3_internal_verdict']} | Benchmark Verdict: {rec['benchmark_verdict']} | Gate: {rec.get('failed_internal_gate')}", flush=True)
        records.append(rec)

    # Write targeted_results.md
    md_lines = [
        "# Targeted Tasks Verification Results",
        "",
        "| Task ID | Type | Mind 3.0 Verdict | Benchmark Verdict | Failed Gate / Category | Duration (s) |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        md_lines.append(
            f"| {r['task_id']} | {r['benchmark']} | {r['mind3_internal_verdict']} | {r['benchmark_verdict']} | {r.get('failed_internal_gate') or 'None (ALL PASS)'} | {r['wall_clock_time']} |"
        )

    out_file = ARTIFACTS_P6 / "targeted_results.md"
    out_file.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"\nTargeted results saved to {out_file}", flush=True)


if __name__ == "__main__":
    main()
