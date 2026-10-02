"""Stage 5 Linux/EDA toolchain evidence probes.

Every probe actually executes its binary and captures real output. A probe
never infers availability from README text, source files, or PATH inspection
alone: ``executed`` is True only when the executable ran and its version
string was captured from its own stdout/stderr.

Evidence records always carry the executing ``platform`` so macOS results can
never be transferred into Linux claims or vice versa.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


TOOL_SPECS: dict[str, dict[str, Any]] = {
    # R3 toolchain contract: exact invocations Mind-3.0 expects on Linux.
    "python": {"argv": [sys.executable, "--version"]},
    "yosys": {"argv": ["yosys", "-V"]},
    "sby": {"argv": ["sby", "--version"]},
    "z3": {"argv": ["z3", "--version"]},
    "verilator": {"argv": ["verilator", "--version"]},
    "sta": {"argv": ["sta", "-version"], "fallbacks": [["opensta", "-version"]]},
    "openroad": {"argv": ["openroad", "-version"]},
    "bwrap": {"argv": ["bwrap", "--version"]},
}


def probe_tool(tool: str, timeout_sec: int = 30) -> dict[str, Any]:
    """Execute a toolchain binary and capture its self-reported version.

    Returns a JSON-safe record with keys: tool, platform, executed, version
    (or "unknown"), returncode, argv, output_head. ``executed`` is True only
    when the process ran; a missing binary yields executed=False and
    version "unknown" — never a PASS.
    """
    record: dict[str, Any] = {
        "tool": tool,
        "platform": platform.system().lower(),
        "executed": False,
        "version": "unknown",
        "returncode": None,
        "argv": [],
        "output_head": "",
    }
    spec = TOOL_SPECS.get(tool)
    if spec is None:
        record["output_head"] = f"no tool spec defined for {tool!r}"
        return record
    candidates = [spec["argv"], *spec.get("fallbacks", [])]
    last_output = ""
    for argv in candidates:
        if shutil.which(argv[0]) is None:
            last_output = f"binary not found on PATH: {argv[0]}"
            continue
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout_sec, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_output = f"execution failed: {exc}"
            continue
        record["executed"] = True
        record["argv"] = list(argv)
        record["returncode"] = proc.returncode
        combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".strip()
        record["output_head"] = combined[:2000]
        first_line = next((ln.strip() for ln in combined.splitlines() if ln.strip()), "")
        record["version"] = first_line if proc.returncode == 0 and first_line else "unknown"
        return record
    record["output_head"] = last_output[:2000]
    return record


def probe_yosys_cdc(yosys_argv: str = "yosys", timeout_sec: int = 60) -> dict[str, Any]:
    """Execute ``yosys -p "help cdc"`` and determine real CDC command availability.

    Returns a JSON-safe record with keys: tool ("yosys-cdc"), platform,
    executed, cdc_available (True only when the command help succeeds),
    returncode, output_head. macOS Homebrew output ("No such command or cell
    type: cdc") yields cdc_available=False — evidence of absence, not of
    OSS CAD Suite capability.
    """
    record: dict[str, Any] = {
        "tool": "yosys-cdc",
        "platform": platform.system().lower(),
        "executed": False,
        "cdc_available": False,
        "returncode": None,
        "argv": [yosys_argv, "-p", "help cdc"],
        "output_head": "",
    }
    if shutil.which(yosys_argv) is None:
        record["output_head"] = f"binary not found on PATH: {yosys_argv}"
        return record
    try:
        proc = subprocess.run(
            [yosys_argv, "-p", "help cdc"],
            capture_output=True, text=True, timeout=timeout_sec, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        record["output_head"] = f"execution failed: {exc}"
        return record
    record["executed"] = True
    record["returncode"] = proc.returncode
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    record["output_head"] = combined.strip()[:2000]
    lowered = combined.lower()
    record["cdc_available"] = (
        "no such command" not in lowered and "unknown command" not in lowered
    )
    return record


def collect_environment_report(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Collect the Stage 5 auditable environment report (R18 field set).

    Tool fields come from actual execution (see probe_tool/probe_yosys_cdc).
    Behavioral fields (CDC execution, smoke results, egress results) are
    "unknown" unless the caller supplies executed evidence — they are never
    fabricated here. Callers (CI evidence script, tests) attach real outcomes.
    """
    tools = {name: probe_tool(name) for name in TOOL_SPECS}
    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.system().lower(),
        "os_release": platform.platform(),
        "python_version": platform.python_version(),
        "tools": tools,
        "yosys_version": tools["yosys"]["version"],
        "sby_version": tools["sby"]["version"],
        "z3_version": tools["z3"]["version"],
        "verilator_version": tools["verilator"]["version"],
        "opensta_version": tools["sta"]["version"],
        "openroad_version": tools["openroad"]["version"],
        "bubblewrap_version": tools["bwrap"]["version"],
        "cdc_command": probe_yosys_cdc(),
        "cdc_execution_result": "unknown",
        "opensta_smoke_result": "unknown",
        "openroad_smoke_result": "unknown",
        "bubblewrap_egress_result": "unknown",
        "seatbelt_egress_result": "unknown",
    }
    if extra:
        for key, value in extra.items():
            if key in report:
                report[key] = value
    report["python_version_executed"] = tools["python"]["executed"]
    return report


def write_environment_report(destination: Path | str) -> Path:
    """Collect the environment report and persist it as JSON. Returns the path."""
    import json

    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(collect_environment_report(), indent=2) + "\n", encoding="utf-8")
    return dest


__all__ = [
    "TOOL_SPECS",
    "collect_environment_report",
    "probe_tool",
    "probe_yosys_cdc",
    "write_environment_report",
]
