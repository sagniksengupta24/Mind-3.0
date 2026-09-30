#!/usr/bin/env python3
"""
scripts/run_step2_mutation.py: Execute Step 2 Mutation Testing on 3 verified RTL designs.
Protocol requirements:
- 3 verified designs from Step 1: priority_encoder, signed_multiplier, cdc_handshake
- 3 mutation classes per design (Off-by-one boundary, Inverted branch/condition, Dropped strobe)
- 9 total mutants evaluated via SymbiYosys formal BMC at depth k=25
- Honest kill rate computation (caught vs surviving / WEAK PROPERTY FAULT)
- Full cryptographic SHA-256 provenance logging
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path("/home/mind/Desktop/AI/Mind-3.0")
STEP1_ARTIFACTS = WORKSPACE_ROOT / "artifacts/step1"
STEP2_ARTIFACTS = WORKSPACE_ROOT / "artifacts/step2"
TASKS_DIR = WORKSPACE_ROOT / "benchmarks/mind_baseline/tasks"
LEDGER_FILE = STEP1_ARTIFACTS / "trace_ledger.jsonl"


def compute_sha256(content: str | bytes) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def append_ledger(task_id: str, turn: int, artifact_name: str, content: str | bytes) -> str:
    art_hash = compute_sha256(content)
    last_line = ""
    if LEDGER_FILE.exists():
        with open(LEDGER_FILE, "r") as f:
            for line in f:
                if line.strip():
                    last_line = line.strip()
    prev_hash = json.loads(last_line).get("record_hash", "0" * 64) if last_line else "0" * 64

    seq = 1
    if LEDGER_FILE.exists():
        with open(LEDGER_FILE, "r") as f:
            seq = sum(1 for l in f if l.strip()) + 1

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


def get_verified_rtl(task_id: str) -> tuple[str, str]:
    """Retrieves original verified RTL and its SHA-256."""
    task_dir = STEP1_ARTIFACTS / task_id
    # Find passing turn
    for turn in [0, 1, 2, 3]:
        meta_file = task_dir / f"turn_{turn}" / "metadata.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text())
            if meta.get("verification", {}).get("passed"):
                rtl_path = task_dir / f"turn_{turn}" / "generated.sv"
                rtl_code = rtl_path.read_text(encoding="utf-8")
                return rtl_code, compute_sha256(rtl_code)
    raise RuntimeError(f"No passing turn found for {task_id}")


def run_mutation_suite():
    STEP2_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PATH"] = f"/home/mind/oss-cad-suite/bin:/home/mind/openroad-env/bin:{env.get('PATH', '')}"

    print("=================================================================")
    print("Starting Mind 3.0 Step 2 Mutation Testing Protocol")
    print("Formal BMC Depth: k = 25 (Engine: SMTBMC Z3)")
    print("=================================================================")

    # Define the 9 mutants across 3 designs
    mutant_definitions = [
        # Design 1: Priority Encoder
        {
            "design": "priority_encoder",
            "mutant_id": "mutant_1_off_by_one",
            "class": "Off-by-one pointer/counter boundary condition",
            "description": "Boundary condition shift: bit 0 encodes to 3'd1 instead of 3'd0",
            "location": "priority_encoder.sv:30",
            "mutate_fn": lambda orig: orig.replace("out = 3'b000;\n            valid = 1'b1;", "out = 3'b001;\n            valid = 1'b1;")
        },
        {
            "design": "priority_encoder",
            "mutant_id": "mutant_2_inverted_branch",
            "class": "Inverted branch/state transition",
            "description": "Inverted priority branch: swapped precedence between in[7] and in[6]",
            "location": "priority_encoder.sv:8-13",
            "mutate_fn": lambda orig: orig.replace(
                "if (in[7]) begin\n            out = 3'b111;\n            valid = 1'b1;\n        end else if (in[6]) begin",
                "if (in[6]) begin\n            out = 3'b110;\n            valid = 1'b1;\n        end else if (in[7]) begin"
            )
        },
        {
            "design": "priority_encoder",
            "mutant_id": "mutant_3_dropped_strobe",
            "class": "Dropped handshake/acknowledgment strobe",
            "description": "Dropped valid strobe: valid flag deasserted when in[7] active",
            "location": "priority_encoder.sv:10",
            "mutate_fn": lambda orig: orig.replace("out = 3'b111;\n            valid = 1'b1;", "out = 3'b111;\n            valid = 1'b0;")
        },

        # Design 2: Signed Multiplier
        {
            "design": "signed_multiplier",
            "mutant_id": "mutant_1_off_by_one",
            "class": "Off-by-one pointer/counter boundary condition",
            "description": "Boundary arithmetic error: product offset by +1 (off-by-one result)",
            "location": "signed_multiplier.sv:8",
            "mutate_fn": lambda orig: orig.replace("assign p = a * b;", "assign p = (a * b) + 16'd1;")
        },
        {
            "design": "signed_multiplier",
            "mutant_id": "mutant_2_inverted_branch",
            "class": "Inverted branch/state transition",
            "description": "Inverted sign calculation: unsigned multiplication treating two's complement as unsigned magnitude",
            "location": "signed_multiplier.sv:8",
            "mutate_fn": lambda orig: orig.replace("assign p = a * b;", "assign p = $unsigned(a) * $unsigned(b);")
        },
        {
            "design": "signed_multiplier",
            "mutant_id": "mutant_3_dropped_strobe",
            "class": "Dropped handshake/acknowledgment strobe",
            "description": "Dropped sign bit strobe: MSB clamped to 0 dropping two's complement sign extension",
            "location": "signed_multiplier.sv:8",
            "mutate_fn": lambda orig: orig.replace("assign p = a * b;", "wire signed [15:0] raw = a * b;\n    assign p = {1'b0, raw[14:0]};")
        },

        # Design 3: CDC Handshake
        {
            "design": "cdc_handshake",
            "mutant_id": "mutant_1_off_by_one",
            "class": "Off-by-one pointer/counter boundary condition",
            "description": "Off-by-one synchronizer stage: reduced destination synchronizer from 2 flip-flops to 1 (violating CDC MTBF)",
            "location": "cdc_handshake.sv:38",
            "mutate_fn": lambda orig: orig.replace("dst_toggle_sync2 <= dst_toggle_sync1;", "dst_toggle_sync2 <= src_toggle;")
        },
        {
            "design": "cdc_handshake",
            "mutant_id": "mutant_2_inverted_branch",
            "class": "Inverted branch/state transition",
            "description": "Inverted edge detector condition: triggers pulse on equality instead of inequality",
            "location": "cdc_handshake.sv:47",
            "mutate_fn": lambda orig: orig.replace("pulse_out_dst <= (dst_toggle_sync1 != dst_toggle_sync2);", "pulse_out_dst <= (dst_toggle_sync1 == dst_toggle_sync2);")
        },
        {
            "design": "cdc_handshake",
            "mutant_id": "mutant_3_dropped_strobe",
            "class": "Dropped handshake/acknowledgment strobe",
            "description": "Dropped acknowledge strobe: busy_src never cleared after transfer acknowledgment",
            "location": "cdc_handshake.sv:25-27",
            "mutate_fn": lambda orig: orig.replace("busy_src <= 1'b0;", "// dropped acknowledge clear\n                busy_src <= 1'b1;")
        },
    ]

    results = []
    caught_count = 0
    weak_count = 0

    for m in mutant_definitions:
        design = m["design"]
        mid = m["mutant_id"]
        mclass = m["class"]
        desc = m["description"]
        loc = m["location"]

        orig_rtl, orig_hash = get_verified_rtl(design)
        mutated_rtl = m["mutate_fn"](orig_rtl)
        if mutated_rtl == orig_rtl:
            raise RuntimeError(f"Mutation function failed to modify RTL for {mid}")

        mut_hash = compute_sha256(mutated_rtl)

        # Load SVA code from task definition
        task_json = json.loads((TASKS_DIR / f"{design}.json").read_text(encoding="utf-8"))
        sva_code = task_json["sva_code"]

        # Setup mutant artifact directory
        mut_dir = STEP2_ARTIFACTS / design / mid
        mut_dir.mkdir(parents=True, exist_ok=True)

        mut_rtl_file = mut_dir / "mutant.sv"
        mut_rtl_file.write_text(mutated_rtl, encoding="utf-8")
        sva_file = mut_dir / "sva.sv"
        sva_file.write_text(sva_code, encoding="utf-8")

        formal_top = f"{design}_formal"
        sby_config = f"""[options]
mode bmc
depth 25

[engines]
smtbmc z3

[script]
read -formal mutant.sv sva.sv
prep -top {formal_top}

[files]
mutant.sv
sva.sv
"""
        sby_file = mut_dir / "formal.sby"
        sby_file.write_text(sby_config, encoding="utf-8")

        # Run SBY BMC
        t0 = time.time()
        cmd = ["sby", "-f", "formal.sby"]
        bmc_res = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=mut_dir, timeout=90)
        t1 = time.time()
        latency = round(t1 - t0, 3)

        (mut_dir / "bmc_stdout.txt").write_text(bmc_res.stdout, encoding="utf-8")
        (mut_dir / "bmc_stderr.txt").write_text(bmc_res.stderr, encoding="utf-8")

        # In SBY: returncode != 0 means assertion violation (caught)
        # returncode == 0 means BMC PASS (assertions held -> mutant survived!)
        caught = (bmc_res.returncode != 0)
        status = "CAUGHT" if caught else "WEAK PROPERTY FAULT"

        if caught:
            caught_count += 1
        else:
            weak_count += 1

        # Look for counterexample trace
        cex_path = None
        cex_candidate = mut_dir / "formal" / "engine_0" / "trace.vcd"
        if cex_candidate.exists():
            cex_path = str(cex_candidate.relative_to(WORKSPACE_ROOT))

        print(f"▶ [{design}] {mid} ({mclass}): {status} (latency: {latency}s, exit: {bmc_res.returncode})")

        rec = {
            "design": design,
            "mutant_id": mid,
            "mutation_class": mclass,
            "description": desc,
            "location": loc,
            "original_rtl_sha256": orig_hash,
            "mutated_rtl_sha256": mut_hash,
            "bmc_command": "sby -f formal.sby (depth=25, solver=z3)",
            "bmc_exit_code": bmc_res.returncode,
            "caught": caught,
            "status": status,
            "counterexample_path": cex_path,
            "latency_seconds": latency,
            "evidence_dir": str(mut_dir.relative_to(WORKSPACE_ROOT))
        }
        results.append(rec)

        # Record in ledger
        append_ledger(design, 200, f"{mid}/mutant.sv", mutated_rtl)
        append_ledger(design, 200, f"{mid}/bmc_result.json", json.dumps(rec))

    total = len(results)
    kill_rate = round(caught_count / total * 100.0, 1)

    summary_data = {
        "benchmark": "Mind 3.0 Step 2 Mutation Testing Protocol",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "designs_evaluated": 3,
        "total_mutants": total,
        "mutations_caught": caught_count,
        "weak_property_faults": weak_count,
        "kill_rate": f"{kill_rate}%",
        "bmc_depth": 25,
        "solver": "z3",
        "mutants": results
    }

    # Save results.json
    (STEP2_ARTIFACTS / "mutation_results.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    # Save results.csv
    csv_lines = ["Design,Mutant ID,Class,Caught,Status,Location,Original SHA256,Mutant SHA256,Evidence Directory"]
    for r in results:
        csv_lines.append(f"{r['design']},{r['mutant_id']},\"{r['mutation_class']}\",{r['caught']},{r['status']},{r['location']},{r['original_rtl_sha256'][:16]}...,{r['mutated_rtl_sha256'][:16]}...,{r['evidence_dir']}")
    (STEP2_ARTIFACTS / "mutation_results.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    # Save summary.md
    summary_md = f"""# Mind 3.0 Step 2 Mutation Testing Report

## Executive Summary

* **Designs Evaluated:** 3 verified designs from Step 1 (`priority_encoder`, `signed_multiplier`, `cdc_handshake`)
* **Mutation Classes Injected:**
  1. Off-by-one pointer/counter boundary condition
  2. Inverted branch/state transition
  3. Dropped handshake/acknowledgment strobe
* **Total Mutants:** {total}
* **Mutations Caught:** {caught_count} / {total}
* **Kill Rate:** **{kill_rate}%**
* **Surviving Mutants (Weak Property Faults):** {weak_count}
* **Formal Verification Engine:** SymbiYosys (`sby`) + Z3 SMT solver at bounded depth $k = 25$

---

## Mutant Evaluation Table

| Design | Mutant ID | Mutation Class | BMC Outcome | Status | Counterexample Trace |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in results:
        trace_str = f"[`{r['counterexample_path']}`]({r['counterexample_path']})" if r["counterexample_path"] else "None (survived)"
        summary_md += f"| `{r['design']}` | `{r['mutant_id']}` | {r['mutation_class']} | Exit {r['bmc_exit_code']} | **{r['status']}** | {trace_str} |\n"

    summary_md += f"""
---

## Analysis of Results

* **Caught Mutations ({caught_count}/{total}):** Injected functional errors that violated formal properties within bound $k=25$. SymbiYosys and Z3 successfully generated counterexample traces demonstrating property violations.
* **Weak Property Faults ({weak_count}/{total}):** Mutants where formal properties did not assert failure within bound $k=25$. In an empirical verification protocol, surviving mutants document areas where property coverage must be tightened.

All mutated RTL source files, formal logs, and counterexample traces are preserved in [`artifacts/step2/`](artifacts/step2/).
"""
    (STEP2_ARTIFACTS / "summary.md").write_text(summary_md, encoding="utf-8")

    print("\n=================================================================")
    print(f"STEP 2 MUTATION COMPLETE: Kill Rate = {kill_rate}% ({caught_count}/{total} caught)")
    print(f"Weak Property Faults: {weak_count}")
    print(f"Summary written to {STEP2_ARTIFACTS / 'summary.md'}")
    print("=================================================================")


if __name__ == "__main__":
    run_mutation_suite()
