#!/usr/bin/env python3
"""Stage 5 environment evidence collector (R18).

Runs real toolchain probes plus the real behavioral evidence tests as
subprocesses, then writes a single auditable JSON report. Nothing is
fabricated: every behavioral field is "unknown" unless its test actually
executed in this session.

Usage:
    python scripts/collect_stage5_evidence.py --output artifacts/stage5_environment_report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from mind3.sandbox.linux_toolchain import collect_environment_report

# Behavioral evidence: (report_key, pytest node ids). Outcomes come from real
# execution return codes and per-test lines, never from configuration.
BEHAVIORAL_SUITES: list[tuple[str, list[str]]] = [
    ("cdc_execution_result", ["tests/test_linux_toolchain.py::test_gate6_cdc_fixture_environment_behavior"]),
    ("opensta_smoke_result", ["tests/test_linux_toolchain.py::test_opensta_smoke_version_and_workload"]),
    ("openroad_smoke_result", ["tests/test_linux_toolchain.py::test_openroad_smoke_version"]),
    ("bubblewrap_egress_result", ["tests/test_mind3.py::test_bubblewrap_sandbox_network_isolation_outbound_blocked"]),
    ("seatbelt_egress_result", ["tests/test_macos_sandbox.py::test_macos_seatbelt_egress_blocked_by_real_socket_attempt"]),
]


def run_pytest(nodes: list[str]) -> dict:
    """Execute pytest for the given nodes, return a JSON-safe outcome record."""
    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", *nodes]
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "detail": f"pytest invocation failed: {exc}"}
    output = (proc.stdout or "") + (proc.stderr or "")
    import platform as _platform

    record: dict = {
        "status": "unknown",
        "platform": _platform.system().lower(),
        "returncode": proc.returncode,
        "detail": "",
    }
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        stripped = line.strip()
        for node in nodes:
            short = node.split("::")[-1]
            if short in stripped and ("PASSED" in stripped or "FAILED" in stripped or "SKIPPED" in stripped or "ERROR" in stripped):
                if "PASSED" in stripped:
                    statuses[short] = "passed"
                elif "SKIPPED" in stripped:
                    statuses[short] = "skipped"
                else:
                    statuses[short] = "failed"
    record["tests"] = statuses
    if proc.returncode == 0:
        record["status"] = "passed" if statuses and all(v == "passed" for v in statuses.values()) else ("skipped" if statuses else "unknown")
    elif any(v == "failed" for v in statuses.values()):
        record["status"] = "failed"
    elif statuses:
        record["status"] = "skipped"
    else:
        record["status"] = "error"
    tail = "\n".join(output.splitlines()[-15:])
    record["detail"] = tail[-2000:]
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect Stage 5 Linux/EDA/sandbox evidence.")
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "artifacts" / "stage5_environment_report.json")
    args = ap.parse_args()

    evidence: dict[str, dict] = {}
    for key, nodes in BEHAVIORAL_SUITES:
        evidence[key] = run_pytest(nodes)
        print(f"{key}: {evidence[key]['status']}", flush=True)

    report = collect_environment_report(extra=evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Environment evidence written to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
