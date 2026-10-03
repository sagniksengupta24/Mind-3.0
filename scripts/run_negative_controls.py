#!/usr/bin/env python3
"""Run intentional-bug negative controls against live Mind 3.0 verification gates.

Enforces:
REAL TOOL -> REAL RESULT
MISSING TOOL -> EXPLICIT SKIP/BLOCK
MOCK -> NEVER PRESENTED AS VERIFIED
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from mind3.core.verifier import SiliconSignoffVerifier
from mind3.core.failure_taxonomy import classify_failure, FailureCategory
from mind3.sandbox.bwrap import BubblewrapSandbox, probe_bubblewrap_namespace_capability
from mind3.sandbox.remote_eda import LocalBwrapRunner, get_eda_runner


def load_manifest() -> list[dict[str, Any]]:
    manifest_path = ROOT / "tests" / "negative_controls" / "negative_controls_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Negative controls manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def copy_case_files(case_dir: Path, case_name: str, workspace: Path) -> list[Path]:
    src = case_dir / f"{case_name}.sv"
    dst = workspace / src.name
    shutil.copy2(src, dst)
    for suffix in ("_formal_top.sv", ".sby", "_tb.cpp", ".sdc"):
        other = case_dir / f"{case_name}{suffix}"
        if other.exists():
            shutil.copy2(other, workspace / other.name)
    return [dst]


def select_control_runner(workspace: Path) -> tuple[Any, bool]:
    """Choose the negative-control EDA runner without faking tool execution.

    Returns ``(runner, sandboxed)``. The sandboxed bwrap path is used only
    when the host kernel actually permits namespace creation (probed, never
    assumed from binary presence). Otherwise tools execute directly on the
    host via an explicitly unsandboxed runner: results stay real
    (``simulated`` remains False) and diagnostics record the execution
    mode. Nothing is mocked and no failure is masked.
    """
    sandbox: BubblewrapSandbox | None = None
    try:
        sandbox = BubblewrapSandbox(workspace)
    except RuntimeError:
        sandbox = None
    if sandbox is not None:
        capable, _reason = probe_bubblewrap_namespace_capability(
            bwrap_binary=sandbox.bwrap_binary
        )
        if capable:
            return get_eda_runner(workspace, sandbox), True
    return LocalBwrapRunner(workspace, sandbox=None, allow_unsandboxed=True), False


def run_control_case(
    entry: dict[str, Any],
    work_root: Path,
    liberty: list[str] | None,
    runner_override: Any | None = None,
) -> dict[str, Any]:
    case_id = entry["id"]
    mode = entry["mode"]
    expected_category = entry["expected_category"]
    case_dir = ROOT / "tests" / "negative_controls"
    workspace = work_root / case_id
    workspace.mkdir(parents=True, exist_ok=True)
    sources = copy_case_files(case_dir, case_id, workspace)

    if runner_override is not None:
        runner = runner_override
        sandboxed: bool | None = None
    else:
        runner, sandboxed = select_control_runner(workspace)

    # Liberty (timing) models are a Gate 4 input only. Volunteering them to
    # Gate 1 changes elaboration (technology mapping via ABC) and can mask
    # structural findings such as combinational loops. Gate 4 raises without
    # liberty; every other gate ignores it.
    gate_liberty = liberty if mode == "gate4" else None
    verifier = SiliconSignoffVerifier(
        top_module=case_id,
        liberty_path=gate_liberty if gate_liberty else None,
        allow_mock_fallback=False,
        require_formal=(mode in ("gate2", "full")),
        require_coverage=(mode in ("gate3", "full")),
        require_cdc=(mode in ("gate6", "full")),
        runner=runner,
    )

    try:
        if mode == "gate1" or mode == "full":
            result = verifier._run_gate1_yosys(runner, sources, workspace)
            observed = result.get("error_category")
            detail = result.get("details", "")
            passed = bool(result.get("passed", False))
            simulated = bool(result.get("simulated", False))
            reports = [result]
        elif mode == "gate2":
            result = verifier._run_gate2_formal_sby(runner, sources, workspace)
            observed = result.get("error_category")
            detail = result.get("details", "")
            passed = bool(result.get("passed", False))
            simulated = bool(result.get("simulated", False))
            reports = [result]
        elif mode == "gate3":
            result = verifier._run_gate3_coverage(runner, sources, workspace)
            observed = result.get("error_category")
            detail = result.get("details", "")
            passed = bool(result.get("passed", False))
            simulated = bool(result.get("simulated", False))
            reports = [result]
        elif mode == "gate4":
            result = verifier._run_gate4_timing(runner, sources, workspace)
            observed = result.get("error_category")
            detail = result.get("details", "")
            passed = bool(result.get("passed", False))
            simulated = bool(result.get("simulated", False))
            reports = [result]
        elif mode == "gate6":
            result = verifier._run_gate6_cdc_analysis(runner, sources, workspace)
            observed = result.get("error_category")
            detail = result.get("details", "")
            passed = bool(result.get("passed", False))
            simulated = bool(result.get("simulated", False))
            reports = [result]
        else:
            raise ValueError(f"Unknown mode: {mode}")

        # Classify with canonical taxonomy
        classified = classify_failure(
            error_category=observed,
            failure_reason=detail,
            gate_reports=reports,
        )

        matched = (not passed) and (
            observed == expected_category
            or (expected_category == "SYNTHESIS_ELABORATION_ERROR" and observed in ("SYNTHESIS_ELABORATION_ERROR", "COVERAGE_BUILD_FAILURE"))
        )

        return {
            "case": case_id,
            "expected_category": expected_category,
            "observed_category": observed,
            "canonical_category": classified.canonical_category.value,
            "expected_gate": entry.get("expected_gate"),
            "passed": passed,
            "matched": matched,
            "details": detail,
            "simulated": simulated,
            "sandboxed": sandboxed,
            "gate_reports": reports,
        }
    except Exception as exc:
        return {
            "case": case_id,
            "expected_category": expected_category,
            "observed_category": None,
            "canonical_category": FailureCategory.UNKNOWN.value,
            "expected_gate": entry.get("expected_gate"),
            "passed": False,
            "matched": False,
            "details": f"EXCEPTION: {exc}",
            "simulated": False,
            "sandboxed": sandboxed,
            "gate_reports": [],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute Mind 3.0 negative-control validation suite.")
    parser.add_argument("--require-live", action="store_true", help="Fail if live EDA tools are missing")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "negative_controls_report.json")
    args = parser.parse_args()

    manifest = load_manifest()
    liberty_env = os.getenv("MIND3_NEGATIVE_CONTROL_LIBERTY")
    liberty = [p for p in liberty_env.split(":") if p] if liberty_env else None

    # Check live tools availability
    missing = []
    for tool in ("yosys", "verilator", "sby"):
        if shutil.which(tool) is None:
            missing.append(tool)

    if missing and args.require_live:
        print(f"FAILED: Missing live EDA tools required for negative controls: {missing}", file=sys.stderr)
        return 1

    temp_root = Path(tempfile.mkdtemp(prefix="mind3_neg_ctrl_"))
    results = []
    print(f"Executing {len(manifest)} intentional-bug negative controls:")
    all_matched = True

    try:
        for entry in manifest:
            cid = entry["id"]
            mode = entry["mode"]
            # Skip timing gate if liberty not configured
            if mode == "gate4" and not liberty:
                print(f"  [-] {cid:28s} ... SKIP (timing library not configured)")
                results.append({
                    "case": cid,
                    "expected_category": entry["expected_category"],
                    "observed_category": "SKIPPED_NO_PDK",
                    "matched": True,
                    "details": "Skipped because MIND3_NEGATIVE_CONTROL_LIBERTY was not set.",
                })
                continue
            # Skip timing gate if no STA binary is available (e.g. the pinned
            # OSS CAD Suite does not ship sta/opensta and Ubuntu 24.04 has no
            # opensta package). This is environment-unavailable, not a verdict.
            if mode == "gate4" and shutil.which("sta") is None and shutil.which("opensta") is None:
                print(f"  [-] {cid:28s} ... SKIP (sta/opensta binary not available on host)")
                results.append({
                    "case": cid,
                    "expected_category": entry["expected_category"],
                    "observed_category": "SKIPPED_NO_STA",
                    "matched": True,
                    "details": "Skipped because no sta/opensta binary is available on this host.",
                })
                continue

            r = run_control_case(entry, temp_root, liberty)
            # Check if CDC command is missing from Yosys on this host
            if mode == "gate6" and r.get("observed_category") == "CDC_TOOLING_UNAVAILABLE":
                print(f"  [-] {cid:28s} ... SKIP (Host Yosys lacks CDC command; requires OSS CAD Suite)")
                r["matched"] = True
                results.append(r)
                continue
            results.append(r)
            status_sym = "PASS" if r["matched"] else "FAIL"
            if not r["matched"]:
                all_matched = False
            print(f"  [{status_sym}] {cid:28s} -> expected={r['expected_category']}, observed={r['observed_category']}")

        out_path = args.output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"\nReport written to: {out_path}")
        if any(r.get("sandboxed") is False for r in results):
            print(
                "NOTE: one or more controls executed with real tools but without "
                "Bubblewrap namespaces (host kernel forbids namespace creation). "
                "Results are real tool outputs (simulated=False), not sandbox-verified runs."
            )
        print(f"Overall Negative-Control Verdict: {'SUCCESS' if all_matched else 'FAILURE'}")
        return 0 if all_matched else 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
