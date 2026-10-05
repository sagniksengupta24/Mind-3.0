"""Live EDA toolchain smoke test and version provenance probe.

Enforces:
REAL TOOL -> REAL RESULT
MISSING TOOL -> EXPLICIT SKIP/BLOCK
MOCK -> NEVER PRESENTED AS VERIFIED
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolStatus(BaseModel):
    """Detailed capability and version record for one EDA binary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    available: bool
    path: str | None = None
    version_string: str = "missing"
    functional_smoke_passed: bool = False
    details: str = ""


class EDASmokeReport(BaseModel):
    """Immutable aggregate smoke test report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    platform: str
    architecture: str
    python_version: str
    tools: dict[str, ToolStatus]
    all_required_available: bool
    all_smoke_tests_passed: bool
    summary_message: str


def run_command_safe(cmd: list[str], cwd: Path | None = None, timeout: int = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout after {timeout}s"
    except Exception as exc:
        return 127, "", str(exc)


def probe_yosys() -> ToolStatus:
    bin_path = shutil.which("yosys")
    if not bin_path:
        return ToolStatus(name="yosys", available=False, details="Binary not found on PATH")

    rc, out, err = run_command_safe(["yosys", "-V"])
    version_line = out.strip().splitlines()[0] if out.strip() else (err.strip().splitlines()[0] if err.strip() else "unknown")
    if rc != 0:
        return ToolStatus(name="yosys", available=False, path=bin_path, version_string="error", details=f"yosys -V returned {rc}: {err}")

    # Functional smoke: tiny synthesizable module
    passed = False
    details = ""
    with tempfile.TemporaryDirectory(prefix="mind3_yosys_smoke_") as td:
        ws = Path(td)
        sv = ws / "smoke.sv"
        sv.write_text("module smoke(input wire a, b, output wire y); assign y = a ^ b; endmodule\n", encoding="utf-8")
        src, sout, serr = run_command_safe(["yosys", "-p", f"read_verilog -sv {sv}; hierarchy -top smoke; proc; opt; check -assert"], cwd=ws)
        if src == 0:
            passed = True
            details = "Elaboration and netlist optimization verified"
        else:
            details = f"Elaboration failed: {serr}"

    return ToolStatus(
        name="yosys",
        available=True,
        path=bin_path,
        version_string=version_line,
        functional_smoke_passed=passed,
        details=details,
    )


def probe_verilator() -> ToolStatus:
    bin_path = shutil.which("verilator")
    if not bin_path:
        return ToolStatus(name="verilator", available=False, details="Binary not found on PATH")

    rc, out, err = run_command_safe(["verilator", "--version"])
    version_line = out.strip().splitlines()[0] if out.strip() else (err.strip().splitlines()[0] if err.strip() else "unknown")
    if rc != 0:
        return ToolStatus(name="verilator", available=False, path=bin_path, version_string="error", details=f"verilator --version returned {rc}: {err}")

    # Functional smoke: lint a small module
    passed = False
    details = ""
    with tempfile.TemporaryDirectory(prefix="mind3_verilator_smoke_") as td:
        ws = Path(td)
        sv = ws / "smoke.sv"
        sv.write_text("module smoke(input wire a, output wire y); assign y = ~a; endmodule\n", encoding="utf-8")
        src, sout, serr = run_command_safe(["verilator", "--lint-only", "-Wall", str(sv)], cwd=ws)
        if src == 0:
            passed = True
            details = "Lint and syntax check verified"
        else:
            details = f"Lint check failed: {serr}"

    return ToolStatus(
        name="verilator",
        available=True,
        path=bin_path,
        version_string=version_line,
        functional_smoke_passed=passed,
        details=details,
    )


def probe_sby() -> ToolStatus:
    bin_path = shutil.which("sby")
    if not bin_path:
        return ToolStatus(name="sby", available=False, details="Binary not found on PATH")

    rc, out, err = run_command_safe(["sby", "--version"])
    version_line = out.strip().splitlines()[0] if out.strip() else (err.strip().splitlines()[0] if err.strip() else "unknown")

    # Functional smoke: check if an SMT solver (z3/yices/cvc4/cvc5) is available and run 1-step BMC
    passed = False
    details = ""
    solver = None
    for s in ("z3", "yices", "cvc5", "cvc4"):
        if shutil.which(s):
            solver = s
            break

    if not solver:
        details = "SBY binary found, but no SMT solver (z3, yices, cvc5) found on PATH"
    else:
        with tempfile.TemporaryDirectory(prefix="mind3_sby_smoke_") as td:
            ws = Path(td)
            sv = ws / "smoke_formal.sv"
            sv.write_text(
                """module smoke_formal(input wire clk, input wire rst_n, output reg q);
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 1'b0;
    else q <= ~q;
end
`ifdef FORMAL
always @(posedge clk) begin
    if (!rst_n) assert(q == 1'b0);
end
`endif
endmodule
""",
                encoding="utf-8",
            )
            cfg = ws / "smoke.sby"
            cfg.write_text(
                f"""[options]
mode bmc
depth 2

[engines]
smtbmc {solver}

[script]
read -formal smoke_formal.sv
prep -top smoke_formal

[files]
{sv}
""",
                encoding="utf-8",
            )
            src, sout, serr = run_command_safe(["sby", "-f", str(cfg)], cwd=ws, timeout=20)
            if src == 0 and ("Status: PASSED" in sout or "DONE (PASS" in sout):
                passed = True
                details = f"BMC formal verification succeeded with solver {solver}"
            else:
                details = f"SBY test failed with returncode {src}: {serr or sout}"

    return ToolStatus(
        name="sby",
        available=True,
        path=bin_path,
        version_string=version_line,
        functional_smoke_passed=passed,
        details=details,
    )


def probe_sta() -> ToolStatus:
    bin_name = "sta" if shutil.which("sta") else ("opensta" if shutil.which("opensta") else None)
    if not bin_name:
        return ToolStatus(name="opensta", available=False, details="Neither 'sta' nor 'opensta' found on PATH")

    bin_path = shutil.which(bin_name)
    rc, out, err = run_command_safe([bin_name, "-version"])
    version_line = out.strip().splitlines()[0] if out.strip() else (err.strip().splitlines()[0] if err.strip() else "unknown")
    if rc != 0:
        # Some versions respond to -v or help
        rc2, out2, _ = run_command_safe([bin_name, "-help"])
        if rc2 == 0:
            version_line = "installed"

    # Functional smoke: run exit in TCL
    passed = False
    details = ""
    with tempfile.TemporaryDirectory(prefix="mind3_sta_smoke_") as td:
        ws = Path(td)
        tcl = ws / "test.tcl"
        tcl.write_text("exit 0\n", encoding="utf-8")
        src, _, serr = run_command_safe([bin_name, str(tcl)], cwd=ws)
        if src == 0:
            passed = True
            details = "TCL script execution verified"
        else:
            details = f"STA execution failed: {serr}"

    return ToolStatus(
        name="opensta",
        available=True,
        path=bin_path,
        version_string=version_line,
        functional_smoke_passed=passed,
        details=details,
    )


def probe_openroad() -> ToolStatus:
    bin_path = shutil.which("openroad")
    if not bin_path:
        return ToolStatus(name="openroad", available=False, details="Binary 'openroad' not found on PATH")

    rc, out, err = run_command_safe(["openroad", "-version"])
    version_line = out.strip().splitlines()[0] if out.strip() else (err.strip().splitlines()[0] if err.strip() else "unknown")

    passed = False
    details = ""
    with tempfile.TemporaryDirectory(prefix="mind3_openroad_smoke_") as td:
        ws = Path(td)
        tcl = ws / "test.tcl"
        tcl.write_text("exit 0\n", encoding="utf-8")
        src, _, serr = run_command_safe(["openroad", "-exit", str(tcl)], cwd=ws)
        if src == 0:
            passed = True
            details = "OpenROAD session initialization verified"
        else:
            details = f"OpenROAD run failed: {serr}"

    return ToolStatus(
        name="openroad",
        available=True,
        path=bin_path,
        version_string=version_line,
        functional_smoke_passed=passed,
        details=details,
    )


def run_eda_smoke_test(require_full_suite: bool = False) -> EDASmokeReport:
    """Run full probe across Yosys, Verilator, SBY, OpenSTA, and OpenROAD."""
    tools = {
        "yosys": probe_yosys(),
        "verilator": probe_verilator(),
        "sby": probe_sby(),
        "opensta": probe_sta(),
        "openroad": probe_openroad(),
    }

    # Core required for RTL logic & formal verification: yosys, verilator, sby
    core_names = ["yosys", "verilator", "sby"]
    if require_full_suite:
        core_names.extend(["opensta", "openroad"])

    all_req_avail = all(tools[k].available for k in core_names)
    all_smoke_pass = all(tools[k].functional_smoke_passed for k in core_names if tools[k].available) and all_req_avail

    avail_summary = [f"{k}: {'OK' if v.functional_smoke_passed else ('AVAILABLE' if v.available else 'MISSING')}" for k, v in tools.items()]
    summary_msg = "; ".join(avail_summary)

    return EDASmokeReport(
        platform=platform.system(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        tools=tools,
        all_required_available=all_req_avail,
        all_smoke_tests_passed=all_smoke_pass,
        summary_message=summary_msg,
    )


if __name__ == "__main__":
    report = run_eda_smoke_test()
    print("Mind 3.0 EDA Toolchain Smoke Test Report:")
    print(f"Platform: {report.platform} ({report.architecture})")
    print(f"Python: {report.python_version}")
    for name, status in report.tools.items():
        sym = "✓" if status.functional_smoke_passed else ("?" if status.available else "✗")
        print(f"  [{sym}] {name:10s} : version={status.version_string} | path={status.path or 'None'} | {status.details}")
    print(f"Summary: {report.summary_message}")
    print(f"All Core Tools Available & Smoke Passed: {report.all_smoke_tests_passed}")
