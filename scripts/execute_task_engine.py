"""Empirical execution engine for Mind 3.0 Step 1 Baseline Benchmark.

Executes a single RTL benchmark task through Turn 0 and up to 3 repair turns,
running full verification gates:
1. Syntax & Compilation (iverilog + yosys prep)
2. Lint & Static Checks (yosys latch and combinational loop inspection)
3. Simulation (vvp with self-checking testbench and watchdog)
4. Formal BMC (SymbiYosys depth 25 with Z3 SMT solver)

Captures raw logs, model provenance metadata, SHA-256 hashes, and appends to trace ledger.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

WORKSPACE_ROOT = Path("/home/mind/Desktop/AI/Mind-3.0")
TASKS_DIR = WORKSPACE_ROOT / "benchmarks/mind_baseline/tasks"
ARTIFACTS_DIR = WORKSPACE_ROOT / "artifacts/step1"
LEDGER_FILE = ARTIFACTS_DIR / "trace_ledger.jsonl"
EDA_PATH = "/home/mind/oss-cad-suite/bin:/home/mind/openroad-env/bin:" + os.environ.get("PATH", "")

# ── Unified Protocol Configuration ──────────────────────────────────────────
STEP1_BMC_DEPTH = 25
OLLAMA_ENDPOINT = os.environ.get("MIND_OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("MIND_MODEL", "qwen2.5-coder:30b")
DEFAULT_PROVIDER = "Ollama (local)"
MODEL_TEMPERATURE = 0.0
MODEL_TOP_P = 1.0
MODEL_SEED = 42
MODEL_MAX_TOKENS = 2048

SYSTEM_PROMPT = (
    "You are an expert digital ASIC designer specializing in synthesizable SystemVerilog. "
    "Write correct, standard-compliant, synthesizable SystemVerilog RTL matching the exact port declarations. "
    "Do not infer latches. Ensure all branches are completely specified. "
    "Output ONLY synthesizable code enclosed in ```systemverilog ... ```."
)


def compute_sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def get_last_ledger_hash() -> str:
    if not LEDGER_FILE.exists():
        return "0" * 64
    last_line = ""
    with open(LEDGER_FILE, "r") as f:
        for line in f:
            if line.strip():
                last_line = line.strip()
    if not last_line:
        return "0" * 64
    try:
        data = json.loads(last_line)
        return data.get("record_hash", "0" * 64)
    except Exception:
        return "0" * 64


def append_ledger_record(task_id: str, turn: int, artifact_name: str, content: str | bytes) -> str:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    prev_hash = get_last_ledger_hash()
    art_hash = compute_sha256(content)

    seq = 1
    if LEDGER_FILE.exists():
        with open(LEDGER_FILE, "r") as f:
            seq = sum(1 for line in f if line.strip()) + 1

    record_core = f"{seq}:{task_id}:{turn}:{artifact_name}:{art_hash}:{prev_hash}"
    rec_hash = compute_sha256(record_core)

    record = {
        "sequence": seq,
        "task_id": task_id,
        "turn": turn,
        "artifact": artifact_name,
        "sha256": art_hash,
        "previous_record_hash": prev_hash,
        "record_hash": rec_hash,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
    return rec_hash


def extract_sv_code(response_text: str) -> str:
    """Extracts SystemVerilog code from markdown code blocks or raw response."""
    patterns = [
        r"```(?:systemverilog|verilog|sv)\s*([\s\S]*?)```",
        r"```\s*([\s\S]*?)```"
    ]
    for pattern in patterns:
        matches = re.findall(pattern, response_text, re.IGNORECASE)
        if matches:
            for m in matches:
                if "module" in m and "endmodule" in m:
                    return m.strip()
    mod_match = re.search(r"(module[\s\S]*?endmodule)", response_text)
    if mod_match:
        return mod_match.group(1).strip()
    return response_text.strip()


def query_model(prompt: str, system_prompt: str = SYSTEM_PROMPT) -> dict[str, Any]:
    """Queries Ollama chat completions API with exact provenance tracking."""
    req_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    t0 = time.time()
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "options": {
            "temperature": MODEL_TEMPERATURE,
            "top_p": MODEL_TOP_P,
            "seed": MODEL_SEED,
            "num_predict": MODEL_MAX_TOKENS
        },
        "stream": False
    }

    try:
        resp = httpx.post(f"{OLLAMA_ENDPOINT}/api/chat", json=payload, timeout=90.0)
        t1 = time.time()
        resp_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if resp.status_code != 200:
            raise RuntimeError(f"Ollama API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        raw_content = data.get("message", {}).get("content", "")
        latency = round(t1 - t0, 3)

        return {
            "provider": DEFAULT_PROVIDER,
            "model": DEFAULT_MODEL,
            "endpoint": OLLAMA_ENDPOINT,
            "temperature": MODEL_TEMPERATURE,
            "top_p": MODEL_TOP_P,
            "seed": MODEL_SEED,
            "max_tokens": MODEL_MAX_TOKENS,
            "system_prompt_hash": compute_sha256(system_prompt),
            "task_prompt_hash": compute_sha256(prompt),
            "request_timestamp": req_timestamp,
            "response_timestamp": resp_timestamp,
            "latency_seconds": latency,
            "raw_response": raw_content,
            "extracted_rtl": extract_sv_code(raw_content)
        }
    except Exception as e:
        raise RuntimeError(f"Failed to query Ollama model {DEFAULT_MODEL} at {OLLAMA_ENDPOINT}: {e}") from e


def run_verification_gates(
    work_dir: Path,
    module_name: str,
    rtl_code: str,
    testbench_code: str,
    sva_code: str | None = None
) -> dict[str, Any]:
    """Runs the 4-gate verification chain on candidate RTL with bounded BMC depth."""
    env = os.environ.copy()
    env["PATH"] = EDA_PATH

    rtl_file = work_dir / f"{module_name}.sv"
    rtl_file.write_text(rtl_code, encoding="utf-8")

    tb_file = work_dir / f"tb_{module_name}.sv"
    tb_file.write_text(testbench_code, encoding="utf-8")

    sim_out = work_dir / "sim.vvp"

    all_stdout = []
    all_stderr = []

    gate_results = {
        "syntax": "NOT_RUN",
        "lint": "NOT_RUN",
        "simulation": "NOT_RUN",
        "bmc": "NOT_RUN",
        "bmc_depth": STEP1_BMC_DEPTH,
        "passed": False,
        "failure_gate": None,
        "failure_reason": None,
        "details": {}
    }

    # ── Gate 1: Syntax & Compilation (iverilog + yosys check) ────────────────
    all_stdout.append("=== GATE 1: SYNTAX CHECK (iverilog compile) ===")
    compile_cmd = ["iverilog", "-g2012", "-o", str(sim_out), str(tb_file), str(rtl_file)]
    try:
        c_res = subprocess.run(compile_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work_dir, timeout=60)
        all_stdout.append(c_res.stdout)
        all_stderr.append(c_res.stderr)
    except subprocess.TimeoutExpired:
        gate_results["syntax"] = "FAIL"
        gate_results["failure_gate"] = "Syntax"
        gate_results["failure_reason"] = "iverilog compilation timed out after 60 seconds."
        all_stderr.append("ERROR: iverilog compilation timed out after 60 seconds.")
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    if c_res.returncode != 0:
        gate_results["syntax"] = "FAIL"
        gate_results["failure_gate"] = "Syntax"
        gate_results["failure_reason"] = f"iverilog compilation failed with exit code {c_res.returncode}:\n{c_res.stderr}"
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    gate_results["syntax"] = "PASS"

    # ── Gate 2: Lint & Static Latch/Loop Analysis (Yosys) ──────────────────────
    all_stdout.append("\n=== GATE 2: LINT CHECK (Yosys AST & latch trap) ===")
    yosys_script = f"read_verilog -sv {rtl_file.name}; prep -top {module_name}"
    y_cmd = ["yosys", "-p", yosys_script]
    try:
        y_res = subprocess.run(y_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work_dir, timeout=60)
        all_stdout.append(y_res.stdout)
        all_stderr.append(y_res.stderr)
    except subprocess.TimeoutExpired:
        gate_results["lint"] = "FAIL"
        gate_results["failure_gate"] = "Lint"
        gate_results["failure_reason"] = "Yosys elaboration timed out after 60 seconds."
        all_stderr.append("ERROR: Yosys elaboration timed out after 60 seconds.")
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    if y_res.returncode != 0:
        gate_results["lint"] = "FAIL"
        gate_results["failure_gate"] = "Lint"
        gate_results["failure_reason"] = f"Yosys elaboration failed with exit code {y_res.returncode}:\n{y_res.stderr or y_res.stdout[-500:]}"
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    y_out = y_res.stdout
    latch_match = re.search(r"\$(?:d|ad)?latch\b", y_out) or re.search(r"\b(?<!no\s)latch inferred\b", y_out, re.IGNORECASE)
    loop_match = "Warning: combinational loop" in y_out or "Warning: found logic loop" in y_out or "Found combinational loop" in y_out

    if latch_match:
        gate_results["lint"] = "FAIL"
        gate_results["failure_gate"] = "Lint"
        gate_results["failure_reason"] = f"Unapproved inferred latch cell detected by Yosys:\n{latch_match.group(0)}"
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    if loop_match:
        gate_results["lint"] = "FAIL"
        gate_results["failure_gate"] = "Lint"
        gate_results["failure_reason"] = "Combinational loop detected by Yosys."
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    gate_results["lint"] = "PASS"

    # ── Gate 3: Simulation (vvp execution) ──────────────────────────────────
    all_stdout.append("\n=== GATE 3: SIMULATION (vvp execution) ===")
    sim_cmd = ["vvp", str(sim_out)]
    try:
        s_res = subprocess.run(sim_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work_dir, timeout=30)
        all_stdout.append(s_res.stdout)
        all_stderr.append(s_res.stderr)
    except subprocess.TimeoutExpired:
        gate_results["simulation"] = "FAIL"
        gate_results["failure_gate"] = "Functional"
        gate_results["failure_reason"] = "Simulation timed out after 30 seconds (infinite loop, deadlock, or hang in DUT)."
        all_stderr.append("ERROR: Simulation timed out after 30 seconds.")
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    if s_res.returncode != 0 or "ALL_TESTS_PASSED" not in s_res.stdout:
        gate_results["simulation"] = "FAIL"
        gate_results["failure_gate"] = "Functional"
        gate_results["failure_reason"] = f"Testbench simulation failed (exit code {s_res.returncode}):\n{s_res.stdout[-1000:]}\n{s_res.stderr}"
        return _finish_gate_results(gate_results, all_stdout, all_stderr)

    gate_results["simulation"] = "PASS"

    # ── Gate 4: Formal BMC (SymbiYosys) ──────────────────────────────────────
    if sva_code:
        all_stdout.append(f"\n=== GATE 4: FORMAL BMC (SymbiYosys depth {STEP1_BMC_DEPTH}) ===")
        formal_top = f"{module_name}_formal"
        formal_wrapper = work_dir / "formal_top.sv"

        if f"module {formal_top}" in sva_code:
            formal_wrapper.write_text(sva_code, encoding="utf-8")
        else:
            formal_wrapper.write_text(f"""
module {formal_top};
    // Include both generated RTL and SVA
endmodule
{sva_code}
""", encoding="utf-8")

        sby_config = f"""[options]
mode bmc
depth {STEP1_BMC_DEPTH}

[engines]
smtbmc z3

[script]
read -formal {rtl_file.name} sva.sv
prep -top {formal_top}

[files]
{rtl_file.name}
sva.sv
"""
        sby_file = work_dir / "formal.sby"
        sby_file.write_text(sby_config, encoding="utf-8")

        sby_cmd = ["sby", "-f", str(sby_file)]
        try:
            f_res = subprocess.run(sby_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=work_dir, timeout=60)
            all_stdout.append(f_res.stdout)
            all_stderr.append(f_res.stderr)

            if f_res.returncode != 0:
                gate_results["bmc"] = "FAIL"
                gate_results["failure_gate"] = "Functional"
                gate_results["failure_reason"] = f"SymbiYosys formal BMC failed:\n{f_res.stdout[-1000:]}"
                return _finish_gate_results(gate_results, all_stdout, all_stderr)
            gate_results["bmc"] = "PASS"
        except subprocess.TimeoutExpired:
            gate_results["bmc"] = "TIMEOUT"
            gate_results["failure_gate"] = "BMC Timeout"
            gate_results["failure_reason"] = f"SymbiYosys BMC exceeded timeout of 60 seconds at depth {STEP1_BMC_DEPTH}."
            return _finish_gate_results(gate_results, all_stdout, all_stderr)
    else:
        gate_results["bmc"] = "NOT_APPLICABLE"

    gate_results["passed"] = True
    return _finish_gate_results(gate_results, all_stdout, all_stderr)


def _finish_gate_results(res: dict[str, Any], stdout_parts: list[str], stderr_parts: list[str]) -> dict[str, Any]:
    res["raw_stdout"] = "\n".join(stdout_parts)
    res["raw_stderr"] = "\n".join(stderr_parts)
    return res


def run_task(task_id: str) -> dict[str, Any]:
    """Runs a single task with Turn 0 and up to 3 repair turns."""
    task_file = TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        raise FileNotFoundError(f"Task definition {task_file} not found")

    with open(task_file, "r") as f:
        task_data = json.load(f)

    module_name = task_data["module_name"]
    initial_prompt = task_data["generation_prompt"]
    testbench_code = task_data["testbench_code"]
    sva_code = task_data.get("sva_code")

    task_dir = ARTIFACTS_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=================================================================")
    print(f"▶ EXECUTING TASK: {task_id} ({task_data['task_name']})")
    print(f"=================================================================")

    # Log task definition
    append_ledger_record(task_id, 0, "task_definition.json", json.dumps(task_data, indent=2))

    task_result: dict[str, Any] = {
        "task_id": task_id,
        "task_name": task_data["task_name"],
        "category": task_data["category"],
        "pass_at_1": False,
        "repair_attempts": 0,
        "converged_turn": None,
        "final_status": "FAIL (Unconverged)",
        "root_failure": None,
        "turns": [],
        "environment_failure": False,
        "bmc_depth": STEP1_BMC_DEPTH
    }

    current_prompt = initial_prompt
    last_rtl = ""

    for turn_idx in range(4):  # Turn 0, 1, 2, 3
        turn_dir = task_dir / f"turn_{turn_idx}"
        turn_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n--- Turn {turn_idx} for {task_id} ---")
        (turn_dir / "prompt.txt").write_text(current_prompt, encoding="utf-8")
        append_ledger_record(task_id, turn_idx, "prompt.txt", current_prompt)

        try:
            model_out = query_model(current_prompt)
        except Exception as exc:
            print(f"❌ Model query error: {exc}")
            task_result["environment_failure"] = True
            task_result["final_status"] = "FAIL (Environment Failure)"
            task_result["root_failure"] = "Environment Failure"
            task_result["repair_attempts"] = turn_idx
            break

        raw_response = model_out["raw_response"]
        generated_rtl = model_out["extracted_rtl"]
        last_rtl = generated_rtl

        (turn_dir / "response.txt").write_text(raw_response, encoding="utf-8")
        (turn_dir / "generated.sv").write_text(generated_rtl, encoding="utf-8")

        append_ledger_record(task_id, turn_idx, "response.txt", raw_response)
        append_ledger_record(task_id, turn_idx, "generated.sv", generated_rtl)

        # Run verification chain
        v_res = run_verification_gates(
            work_dir=turn_dir,
            module_name=module_name,
            rtl_code=generated_rtl,
            testbench_code=testbench_code,
            sva_code=sva_code
        )

        (turn_dir / "verification_stdout.txt").write_text(v_res["raw_stdout"], encoding="utf-8")
        (turn_dir / "verification_stderr.txt").write_text(v_res["raw_stderr"], encoding="utf-8")

        v_summary = {
            "syntax": v_res["syntax"],
            "lint": v_res["lint"],
            "simulation": v_res["simulation"],
            "bmc": v_res["bmc"],
            "bmc_depth": STEP1_BMC_DEPTH,
            "passed": v_res["passed"],
            "failure_gate": v_res["failure_gate"],
            "failure_reason": v_res["failure_reason"]
        }
        (turn_dir / "verification.json").write_text(json.dumps(v_summary, indent=2), encoding="utf-8")

        meta = {
            "task_id": task_id,
            "turn": turn_idx,
            "provider": model_out["provider"],
            "model": model_out["model"],
            "endpoint": model_out["endpoint"],
            "temperature": model_out["temperature"],
            "top_p": model_out["top_p"],
            "seed": model_out["seed"],
            "max_tokens": model_out["max_tokens"],
            "system_prompt_hash": model_out["system_prompt_hash"],
            "task_prompt_hash": model_out["task_prompt_hash"],
            "request_timestamp": model_out["request_timestamp"],
            "response_timestamp": model_out["response_timestamp"],
            "latency_seconds": model_out["latency_seconds"],
            "bmc_depth": STEP1_BMC_DEPTH,
            "verification": v_summary
        }
        (turn_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        append_ledger_record(task_id, turn_idx, "verification.json", json.dumps(v_summary, indent=2))
        append_ledger_record(task_id, turn_idx, "metadata.json", json.dumps(meta, indent=2))

        turn_record = {
            "turn": turn_idx,
            "latency": model_out["latency_seconds"],
            "verification": v_summary
        }
        task_result["turns"].append(turn_record)

        print(f"Gates: Syntax={v_res['syntax']} Lint={v_res['lint']} Sim={v_res['simulation']} BMC={v_res['bmc']}")

        if v_res["passed"]:
            print(f"✅ PASSED on Turn {turn_idx}!")
            if turn_idx == 0:
                task_result["pass_at_1"] = True
                task_result["repair_attempts"] = 0
                task_result["converged_turn"] = 0
                task_result["final_status"] = "PASS"
            else:
                task_result["pass_at_1"] = False
                task_result["repair_attempts"] = turn_idx
                task_result["converged_turn"] = turn_idx
                task_result["final_status"] = "PASS (Repaired)"
            task_result["root_failure"] = None
            break
        else:
            print(f"❌ FAILED on Turn {turn_idx}: {v_res['failure_gate']} - {v_res['failure_reason'][:120]}...")
            if turn_idx == 0:
                task_result["root_failure"] = v_res["failure_gate"]

            if turn_idx < 3:
                current_prompt = (
                    f"Your previously generated SystemVerilog implementation for module '{module_name}' FAILED verification at the {v_res['failure_gate']} gate.\n\n"
                    f"### Previous Implementation:\n```systemverilog\n{generated_rtl}\n```\n\n"
                    f"### Verification Diagnostic Feedback:\n{v_res['failure_reason']}\n\n"
                    f"Please analyze the failure reason carefully, correct the bug in the SystemVerilog logic, and return ONLY the complete corrected synthesizable module enclosed in ```systemverilog ... ```."
                )
            else:
                print(f"⚠️ Exhausted repair budget (3 turns) for {task_id}.")
                task_result["pass_at_1"] = False
                task_result["repair_attempts"] = 3
                task_result["converged_turn"] = None
                task_result["final_status"] = "FAIL (Unconverged)"

    return task_result


def main():
    parser = argparse.ArgumentParser(description="Run Mind 3.0 Step 1 Baseline Task(s)")
    parser.add_argument("--task", type=str, default="all", help="Task ID to execute, or 'all'")
    args = parser.parse_args()

    # Preflight tool check
    for tool in ["iverilog", "vvp", "yosys", "sby"]:
        if not shutil.which(tool, path=EDA_PATH):
            print(f"FATAL: Required EDA tool '{tool}' not found on PATH ({EDA_PATH})")
            sys.exit(1)

    # Check Ollama connectivity
    try:
        r = httpx.get(f"{OLLAMA_ENDPOINT}/api/tags", timeout=5.0)
        if r.status_code != 200:
            print(f"FATAL: Ollama returned HTTP {r.status_code} at {OLLAMA_ENDPOINT}")
            sys.exit(1)
    except Exception as e:
        print(f"FATAL: Cannot connect to Ollama endpoint at {OLLAMA_ENDPOINT}: {e}")
        sys.exit(1)

    task_ids = [
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

    if args.task != "all":
        if args.task not in task_ids:
            print(f"Error: Unknown task '{args.task}'. Must be one of: {task_ids}")
            sys.exit(1)
        tasks_to_run = [args.task]
    else:
        tasks_to_run = task_ids

    results = []
    for tid in tasks_to_run:
        res = run_task(tid)
        results.append(res)

    print("\n=================================================================")
    print("RUN COMPLETE. SUMMARY:")
    for r in results:
        status_str = r["final_status"]
        root_str = r["root_failure"] or "-"
        attempts_str = str(r["repair_attempts"])
        conv_str = str(r["converged_turn"]) if r["converged_turn"] is not None else "None"
        print(f"  {r['task_id']:<26} | Pass@1: {str(r['pass_at_1']):<5} | Repairs: {attempts_str:<2} | Conv Turn: {conv_str:<4} | Status: {status_str:<20} | Root: {root_str}")
    print("=================================================================\n")


if __name__ == "__main__":
    main()
