"""Validates consistency between raw artifacts and benchmark reports for Step 1.
Implements Gate 16 strict programmatic verification.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(os.environ.get("MIND3_ROOT", Path(__file__).resolve().parents[1])).resolve()
ARTIFACTS_DIR = WORKSPACE_ROOT / "artifacts/step1"
RESULTS_JSON = ARTIFACTS_DIR / "results.json"
LEDGER_FILE = ARTIFACTS_DIR / "trace_ledger.jsonl"
TASKS_DIR = WORKSPACE_ROOT / "benchmarks/mind_baseline/tasks"
AUDIT_DIR = WORKSPACE_ROOT / "artifacts/audit"

EXPECTED_BMC_DEPTH = 25
EXPECTED_MODEL = "qwen2.5-coder:30b"


def compute_sha256(path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def validate():
    print("=================================================================")
    print("Validating Step 1 Audit Integrity, Consistency & Provenance")
    print("=================================================================")

    # 1. Audit Documents Check
    for audit_file in ["current_run_audit.md", "invalidated_claims.md", "determinism_test.json"]:
        p = AUDIT_DIR / audit_file
        if not p.exists():
            print(f"❌ FAIL: Required audit document {p} missing.")
            sys.exit(1)
    print("✔ Audit receipts & determinism trial: PRESENT")

    # 2. Results JSON Existence
    if not RESULTS_JSON.exists():
        print(f"❌ FAIL: {RESULTS_JSON} does not exist.")
        sys.exit(1)

    with open(RESULTS_JSON, "r") as f:
        results = json.load(f)

    # 3. Task Count
    tasks = results.get("tasks", [])
    if len(tasks) != 10:
        print(f"❌ FAIL: Expected 10 tasks in results.json, found {len(tasks)}")
        sys.exit(1)

    # 4. BMC Depth Configuration Check
    if results.get("configured_bmc_depth") != EXPECTED_BMC_DEPTH:
        print(f"❌ FAIL: Configured BMC depth in results.json ({results.get('configured_bmc_depth')}) != {EXPECTED_BMC_DEPTH}")
        sys.exit(1)

    calc_pass_at_1 = 0
    calc_repaired_pass = 0
    calc_unconverged = 0

    for t in tasks:
        tid = t["task_id"]
        tdir = ARTIFACTS_DIR / tid
        if not tdir.exists():
            print(f"❌ FAIL: Artifact directory missing for {tid}")
            sys.exit(1)

        # Check BMC depth on task record
        if t.get("bmc_depth") != EXPECTED_BMC_DEPTH:
            print(f"❌ FAIL: BMC depth mismatch for task {tid}: expected {EXPECTED_BMC_DEPTH}, got {t.get('bmc_depth')}")
            sys.exit(1)

        # Check turn_0
        turn0_dir = tdir / "turn_0"
        if not turn0_dir.exists():
            print(f"❌ FAIL: turn_0 directory missing for {tid}")
            sys.exit(1)

        # Check raw artifact files in turn_0
        for required_file in ["prompt.txt", "response.txt", "generated.sv", "verification_stdout.txt", "verification_stderr.txt", "verification.json", "metadata.json"]:
            rf = turn0_dir / required_file
            if not rf.exists():
                print(f"❌ FAIL: Required file {required_file} missing in {turn0_dir}")
                sys.exit(1)

        turn0_meta = json.loads((turn0_dir / "metadata.json").read_text())
        turn0_passed = turn0_meta["verification"]["passed"]

        # Check model provenance
        if turn0_meta.get("model") != EXPECTED_MODEL:
            print(f"❌ FAIL: Unexpected model in {tid}/turn_0 metadata: {turn0_meta.get('model')} != {EXPECTED_MODEL}")
            sys.exit(1)

        # Check Pass@1 consistency
        if t["pass_at_1"] != turn0_passed:
            print(f"❌ FAIL: Pass@1 mismatch for {tid}: reported {t['pass_at_1']}, raw {turn0_passed}")
            sys.exit(1)

        # Check repair semantics
        if turn0_passed:
            calc_pass_at_1 += 1
            if t["repair_attempts"] != 0 or t["converged_turn"] != 0 or t["final_status"] != "PASS":
                print(f"❌ FAIL: Turn 0 pass must have repair_attempts=0, converged_turn=0, final_status='PASS' for {tid}")
                sys.exit(1)
        else:
            conv_turn = t["converged_turn"]
            if conv_turn is not None:
                calc_repaired_pass += 1
                if t["repair_attempts"] != conv_turn or t["final_status"] != "PASS (Repaired)":
                    print(f"❌ FAIL: Repaired pass repair_attempts ({t['repair_attempts']}) != converged_turn ({conv_turn}) for {tid}")
                    sys.exit(1)
                conv_dir = tdir / f"turn_{conv_turn}"
                if not conv_dir.exists():
                    print(f"❌ FAIL: Convergence turn dir {conv_dir} missing for {tid}")
                    sys.exit(1)
                conv_meta = json.loads((conv_dir / "metadata.json").read_text())
                if not conv_meta["verification"]["passed"]:
                    print(f"❌ FAIL: Claimed convergence turn {conv_turn} failed in raw metadata for {tid}")
                    sys.exit(1)
            else:
                calc_unconverged += 1
                if t["repair_attempts"] != 3 or t["final_status"] != "FAIL (Unconverged)":
                    print(f"❌ FAIL: Unconverged task must have repair_attempts=3, final_status='FAIL (Unconverged)' for {tid}, got attempts={t['repair_attempts']}, status={t['final_status']}")
                    sys.exit(1)

    # 5. Aggregate consistency
    if calc_pass_at_1 != results["pass_at_1_count"]:
        print(f"❌ FAIL: Aggregated Pass@1 count ({results['pass_at_1_count']}) != calculated ({calc_pass_at_1})")
        sys.exit(1)

    if calc_repaired_pass != results["repair_converged_count"]:
        print(f"❌ FAIL: Aggregated repair-converged ({results['repair_converged_count']}) != calculated ({calc_repaired_pass})")
        sys.exit(1)

    if calc_unconverged != results["unconverged_count"]:
        print(f"❌ FAIL: Aggregated unconverged count ({results['unconverged_count']}) != calculated ({calc_unconverged})")
        sys.exit(1)

    print(f"✔ 10 Benchmark tasks: raw logs, metadata, BMC depth={EXPECTED_BMC_DEPTH}, repair counts 100% consistent.")

    # 6. Trace Ledger Hash Chain Integrity
    if not LEDGER_FILE.exists():
        print(f"❌ FAIL: Trace ledger {LEDGER_FILE} missing.")
        sys.exit(1)

    ledger_lines = [l.strip() for l in LEDGER_FILE.read_text().splitlines() if l.strip()]
    if not ledger_lines:
        print(f"❌ FAIL: Trace ledger is empty.")
        sys.exit(1)

    prev_hash = "0" * 64
    for idx, line in enumerate(ledger_lines):
        rec = json.loads(line)
        if rec["previous_record_hash"] != prev_hash:
            print(f"❌ FAIL: Hash chain broken at record {rec['sequence']}: expected prev {prev_hash}, got {rec['previous_record_hash']}")
            sys.exit(1)
        core = f"{rec['sequence']}:{rec['task_id']}:{rec['turn']}:{rec['artifact']}:{rec['sha256']}:{rec['previous_record_hash']}"
        expected_rec_hash = hashlib.sha256(core.encode("utf-8")).hexdigest()
        if rec["record_hash"] != expected_rec_hash:
            print(f"❌ FAIL: Record hash mismatch at record {rec['sequence']}")
            sys.exit(1)
        prev_hash = rec["record_hash"]

    print(f"✔ Trace ledger cryptographic integrity: INTACT ({len(ledger_lines)} unbroken SHA-256 records)")
    print("\n✅ STEP 1 AUDIT VALIDATION PASSED.")


if __name__ == "__main__":
    validate()
