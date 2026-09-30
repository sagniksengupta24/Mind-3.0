"""Collects Step 1 results and generates results.json, results.csv, and summary.md.
Adheres strictly to Gate 4 (BMC depth consistency) and Gate 5 (repair count semantics).
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

WORKSPACE_ROOT = Path("/home/mind/Desktop/AI/Mind-3.0")
ARTIFACTS_DIR = WORKSPACE_ROOT / "artifacts/step1"
TASKS_DIR = WORKSPACE_ROOT / "benchmarks/mind_baseline/tasks"

STEP1_BMC_DEPTH = 25

ORDERED_TASK_IDS = [
    "priority_encoder",
    "gray_counter",
    "signed_multiplier",
    "pipelined_adder",
    "traffic_light_controller",
    "packet_frame_parser",
    "sync_fifo",
    "spi_master",
    "two_phase_handshake",
    "cdc_handshake"
]


def collect_results():
    task_summaries = []
    pass_at_1_count = 0
    repair_converged_count = 0
    unconverged_count = 0
    repair_turns_list = []
    root_failures = {}

    for tid in ORDERED_TASK_IDS:
        task_dir = ARTIFACTS_DIR / tid
        task_def_file = TASKS_DIR / f"{tid}.json"
        with open(task_def_file, "r") as f:
            task_def = json.load(f)

        # Inspect turns in order
        turn_dirs = sorted([d for d in task_dir.glob("turn_*") if d.is_dir()], key=lambda p: int(p.name.split("_")[1]))
        if not turn_dirs:
            task_summaries.append({
                "task_id": tid,
                "task_name": task_def["task_name"],
                "category": task_def["category"],
                "pass_at_1": False,
                "repair_attempts": 0,
                "converged_turn": None,
                "final_status": "NOT_RUN",
                "root_failure": "Not Executed",
                "bmc_depth": STEP1_BMC_DEPTH,
                "evidence_path": str(task_dir.relative_to(WORKSPACE_ROOT))
            })
            continue

        turn_0_meta = json.loads((turn_dirs[0] / "metadata.json").read_text())
        turn_0_passed = turn_0_meta["verification"]["passed"]

        final_passed = False
        conv_turn = None
        repair_attempts = len(turn_dirs) - 1
        final_status = "FAIL (Unconverged)"
        root_failure = None

        if turn_0_passed:
            pass_at_1_count += 1
            final_passed = True
            repair_attempts = 0
            conv_turn = 0
            final_status = "PASS"
            repair_turns_list.append(0)
        else:
            root_failure = turn_0_meta["verification"]["failure_gate"] or "Functional"
            # check subsequent turns
            for tdir in turn_dirs[1:]:
                t_idx = int(tdir.name.split("_")[1])
                t_meta = json.loads((tdir / "metadata.json").read_text())
                if t_meta["verification"]["passed"]:
                    final_passed = True
                    conv_turn = t_idx
                    repair_attempts = t_idx
                    final_status = "PASS (Repaired)"
                    repair_converged_count += 1
                    repair_turns_list.append(t_idx)
                    break

            if not final_passed:
                unconverged_count += 1
                repair_attempts = 3
                root_failures[root_failure] = root_failures.get(root_failure, 0) + 1

        task_summaries.append({
            "task_id": tid,
            "task_name": task_def["task_name"],
            "category": task_def["category"],
            "pass_at_1": turn_0_passed,
            "repair_attempts": repair_attempts,
            "converged_turn": conv_turn,
            "final_status": final_status,
            "root_failure": root_failure if not final_passed else None,
            "bmc_depth": STEP1_BMC_DEPTH,
            "evidence_path": f"artifacts/step1/{tid}/"
        })

    # Summary metrics
    total_tasks = len(ORDERED_TASK_IDS)
    mean_repairs = round(statistics.mean(repair_turns_list), 2) if repair_turns_list else 0.0
    median_repairs = statistics.median(repair_turns_list) if repair_turns_list else 0

    results_data = {
        "benchmark": "Mind 3.0 Baseline Benchmark (Step 1)",
        "configured_bmc_depth": STEP1_BMC_DEPTH,
        "model_provider": "Ollama (local 127.0.0.1:11434)",
        "model_name": "qwen2.5-coder:30b",
        "total_tasks": total_tasks,
        "pass_at_1_count": pass_at_1_count,
        "pass_at_1_rate": f"{(pass_at_1_count / total_tasks) * 100:.1f}%",
        "repair_converged_count": repair_converged_count,
        "unconverged_count": unconverged_count,
        "final_pass_count": pass_at_1_count + repair_converged_count,
        "final_pass_rate": f"{((pass_at_1_count + repair_converged_count) / total_tasks) * 100:.1f}%",
        "mean_repair_turns_to_convergence": mean_repairs,
        "median_repair_turns_to_convergence": median_repairs,
        "root_failure_distribution": root_failures,
        "tasks": task_summaries
    }

    # 1. Write results.json
    results_json_path = ARTIFACTS_DIR / "results.json"
    with open(results_json_path, "w") as f:
        json.dump(results_data, f, indent=2)

    # 2. Write results.csv
    results_csv_path = ARTIFACTS_DIR / "results.csv"
    with open(results_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Task ID",
            "Task Name",
            "Category",
            "Pass@1",
            "Repair Attempts",
            "Converged Turn",
            "Final Status",
            "Root Failure",
            "BMC Depth",
            "Evidence Path"
        ])
        for t in task_summaries:
            writer.writerow([
                t["task_id"],
                t["task_name"],
                t["category"],
                "TRUE" if t["pass_at_1"] else "FALSE",
                t["repair_attempts"],
                str(t["converged_turn"]) if t["converged_turn"] is not None else "None",
                t["final_status"],
                t["root_failure"] or "None (Passed)",
                t["bmc_depth"],
                t["evidence_path"]
            ])

    # 3. Write summary.md
    summary_md_path = ARTIFACTS_DIR / "summary.md"
    with open(summary_md_path, "w") as f:
        f.write("# Mind 3.0 Baseline Benchmark Results (Step 1)\n\n")
        f.write("## Executive Summary Table\n\n")
        f.write("| Task | Category | Pass@1 | Repair Attempts | Converged Turn | Final Status | Root Failure | Evidence Path |\n")
        f.write("| :--- | :--- | :---: | :---: | :---: | :--- | :--- | :--- |\n")
        for t in task_summaries:
            p1_str = "TRUE" if t["pass_at_1"] else "FALSE"
            conv_str = str(t["converged_turn"]) if t["converged_turn"] is not None else "None"
            rf_str = t["root_failure"] or "-"
            f.write(f"| {t['task_name']} | {t['category']} | {p1_str} | {t['repair_attempts']} | {conv_str} | **{t['final_status']}** | {rf_str} | [`{t['evidence_path']}`]({t['evidence_path']}) |\n")

        f.write("\n## Aggregate Metrics\n\n")
        f.write(f"* **Total Tasks:** {total_tasks}\n")
        f.write(f"* **Configured BMC Depth:** {STEP1_BMC_DEPTH}\n")
        f.write(f"* **Pass@1 Aggregate:** {pass_at_1_count} / {total_tasks} ({results_data['pass_at_1_rate']})\n")
        f.write(f"* **Repair-Converged Aggregate:** {repair_converged_count} / {total_tasks}\n")
        f.write(f"* **Unconverged Count:** {unconverged_count} / {total_tasks}\n")
        f.write(f"* **Final Overall Passing Count:** {pass_at_1_count + repair_converged_count} / {total_tasks} ({results_data['final_pass_rate']})\n")
        f.write(f"* **Mean Repair Turns (converged designs):** {mean_repairs}\n")
        f.write(f"* **Median Repair Turns (converged designs):** {median_repairs}\n\n")

        f.write("## Root Failure Distribution (Unconverged Tasks)\n")
        f.write("```json\n" + json.dumps(root_failures, indent=2) + "\n```\n")

    print(f"Generated results.json, results.csv, and summary.md at {ARTIFACTS_DIR}")


if __name__ == "__main__":
    collect_results()
