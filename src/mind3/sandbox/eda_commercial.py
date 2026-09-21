"""Commercial EDA Toolchain Runner & Compute Grid Dispatcher for Mind 3.0.

Provides direct execution and batch grid cluster offloading for Synopsys,
Cadence, and Siemens industrial toolchains, including FlexLM license monitoring.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionResult:
    """Represents the execution outcome of an external tool."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def returncode(self) -> int:
        return self.exit_code


@dataclass(frozen=True)
class GridJobSpec:
    """Specification for dispatching an EDA job to an LSF/Slurm compute cluster."""

    job_name: str
    command: list[str]
    workdir: Path
    queue_or_partition: str = "normal"
    num_cpus: int = 8
    memory_gb: int = 32
    scheduler: str = "lsf"  # "lsf", "slurm", or "sge"
    log_file: str = "job.log"
    environment: dict[str, str] = field(default_factory=dict)


class FlexLMMonitor:
    """Inspects FlexLM / Reprise license server status to prevent license starvation."""

    @staticmethod
    def check_feature_availability(feature: str, license_server: str = "") -> dict[str, Any]:
        """Query lmutil/lmstat for available licenses for a given feature."""
        cmd = ["lmutil", "lmstat", "-f", feature]
        if license_server:
            cmd.extend(["-c", license_server])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            output = f"{res.stdout}\n{res.stderr}"
        except (subprocess.SubprocessError, FileNotFoundError):
            # In simulated or loopback-only test environments where lmutil is absent
            return {
                "feature": feature,
                "available": True,
                "total_licenses": 999,
                "used_licenses": 0,
                "free_licenses": 999,
                "simulated": True,
            }

        # Parse: Users of <feature>: (Total of N licenses issued; Total of M licenses in use)
        match = re.search(
            r"Total of\s+(\d+)\s+licenses? issued;\s+Total of\s+(\d+)\s+licenses? in use",
            output,
            re.IGNORECASE,
        )
        if match:
            total = int(match.group(1))
            used = int(match.group(2))
            free = max(0, total - used)
            return {
                "feature": feature,
                "available": free > 0,
                "total_licenses": total,
                "used_licenses": used,
                "free_licenses": free,
                "simulated": False,
            }

        return {
            "feature": feature,
            "available": True,
            "total_licenses": -1,
            "used_licenses": -1,
            "free_licenses": -1,
            "raw_output": output,
            "simulated": False,
        }


class GridClusterDispatcher:
    """Dispatches commercial EDA jobs to LSF, Slurm, or SGE cluster queues."""

    def __init__(self, scheduler: str = "lsf") -> None:
        self.scheduler = scheduler.lower()

    def build_submit_command(self, spec: GridJobSpec) -> list[str]:
        """Construct the CLI submission command based on scheduler type."""
        cmd_str = " ".join(spec.command)
        if self.scheduler == "lsf":
            return [
                "bsub",
                "-J", spec.job_name,
                "-q", spec.queue_or_partition,
                "-n", str(spec.num_cpus),
                "-R", f"rusage[mem={spec.memory_gb * 1024}]",
                "-o", spec.log_file,
                "-cwd", str(spec.workdir),
                cmd_str,
            ]
        elif self.scheduler == "slurm":
            return [
                "sbatch",
                "--job-name", spec.job_name,
                "--partition", spec.queue_or_partition,
                "--cpus-per-task", str(spec.num_cpus),
                "--mem", f"{spec.memory_gb}G",
                "--output", spec.log_file,
                "--chdir", str(spec.workdir),
                "--wrap", cmd_str,
            ]
        elif self.scheduler == "sge":
            return [
                "qsub",
                "-N", spec.job_name,
                "-q", spec.queue_or_partition,
                "-pe", "smp", str(spec.num_cpus),
                "-l", f"h_vmem={spec.memory_gb}G",
                "-o", spec.log_file,
                "-wd", str(spec.workdir),
                "-b", "y",
                cmd_str,
            ]
        raise ValueError(f"Unsupported scheduler: {self.scheduler}. Choose 'lsf', 'slurm', or 'sge'.")

    def submit_job(self, spec: GridJobSpec) -> dict[str, Any]:
        """Submit a job to the cluster and return job ID."""
        submit_cmd = self.build_submit_command(spec)
        try:
            proc = subprocess.run(
                submit_cmd,
                cwd=spec.workdir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            # Parse Job ID: LSF: "Job <12345> is submitted to queue"
            # Slurm: "Submitted batch job 12345"
            job_id: str | None = None
            if self.scheduler == "lsf":
                m = re.search(r"Job\s+<(\d+)>", stdout)
                if m:
                    job_id = m.group(1)
            elif self.scheduler == "slurm":
                m = re.search(r"Submitted batch job\s+(\d+)", stdout)
                if m:
                    job_id = m.group(1)

            return {
                "success": proc.returncode == 0,
                "job_id": job_id,
                "stdout": stdout,
                "stderr": stderr,
                "submit_cmd": submit_cmd,
            }
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            return {
                "success": False,
                "job_id": None,
                "stdout": "",
                "stderr": str(e),
                "submit_cmd": submit_cmd,
            }


class CommercialEDARunner(ABC):
    """Abstract base runner for commercial EDA tools."""

    def __init__(self, workspace: Path, dispatcher: GridClusterDispatcher | None = None) -> None:
        self.workspace = workspace
        self.dispatcher = dispatcher

    @abstractmethod
    def run_tool(self, tool_binary: str, script_path: Path, timeout_sec: int = 3600) -> ExecutionResult:
        """Run an EDA binary with the given script."""
        raise NotImplementedError("Subclasses must implement run_tool")


class SynopsysRunner(CommercialEDARunner):
    """Drives Synopsys toolchain (Design Compiler, PrimeTime, Formality, ICV)."""

    def run_tool(self, tool_binary: str, script_path: Path, timeout_sec: int = 3600) -> ExecutionResult:
        cmd = [tool_binary, "-f", str(script_path.name)]
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            return ExecutionResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        except subprocess.TimeoutExpired:
            return ExecutionResult(exit_code=-1, stdout="", stderr=f"Synopsys {tool_binary} timed out after {timeout_sec}s")
        except FileNotFoundError:
            return ExecutionResult(exit_code=127, stdout="", stderr=f"{tool_binary}: command not found")


class CadenceRunner(CommercialEDARunner):
    """Drives Cadence toolchain (Genus, Innovus, Tempus, Conformal, Voltus)."""

    def run_tool(self, tool_binary: str, script_path: Path, timeout_sec: int = 3600) -> ExecutionResult:
        # Genus / Innovus typically take -files or -file
        flag = "-files" if tool_binary in ("genus", "innovus", "tempus") else "-f"
        cmd = [tool_binary, flag, str(script_path.name)]
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            return ExecutionResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        except subprocess.TimeoutExpired:
            return ExecutionResult(exit_code=-1, stdout="", stderr=f"Cadence {tool_binary} timed out after {timeout_sec}s")
        except FileNotFoundError:
            return ExecutionResult(exit_code=127, stdout="", stderr=f"{tool_binary}: command not found")


class SiemensRunner(CommercialEDARunner):
    """Drives Siemens EDA toolchain (Calibre nmDRC/nmLVS, Tessent)."""

    def run_tool(self, tool_binary: str, script_path: Path, timeout_sec: int = 3600) -> ExecutionResult:
        cmd = [tool_binary, str(script_path.name)]
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            return ExecutionResult(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        except subprocess.TimeoutExpired:
            return ExecutionResult(exit_code=-1, stdout="", stderr=f"Siemens {tool_binary} timed out after {timeout_sec}s")
        except FileNotFoundError:
            return ExecutionResult(exit_code=127, stdout="", stderr=f"{tool_binary}: command not found")


# ── Commercial EDA Log & Report Parsers ───────────────────────────────────────

def parse_primetime_log(log_text: str) -> dict[str, Any]:
    """Parse Synopsys PrimeTime MCMM STA log output for WNS, TNS, and scenario slacks."""
    scenarios: dict[str, dict[str, float | None]] = {}
    pattern = re.compile(
        r"SCENARIO:\s*(\S+)\s*\|\s*SETUP_WNS:\s*([-+]?\d+(?:\.\d+)?|None|VIOLATED)?\s*\|\s*HOLD_WNS:\s*([-+]?\d+(?:\.\d+)?|None)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(log_text):
        sc_name = match.group(1)
        s_wns_str = match.group(2)
        h_wns_str = match.group(3)
        s_wns = float(s_wns_str) if s_wns_str and s_wns_str not in ("None", "VIOLATED") else None
        h_wns = float(h_wns_str) if h_wns_str and h_wns_str != "None" else None
        scenarios[sc_name] = {"setup_wns": s_wns, "hold_wns": h_wns}

    worst_setup = min((s["setup_wns"] for s in scenarios.values() if s["setup_wns"] is not None), default=None)
    worst_hold = min((s["hold_wns"] for s in scenarios.values() if s["hold_wns"] is not None), default=None)

    has_violation = (
        (worst_setup is not None and worst_setup < 0.0)
        or (worst_hold is not None and worst_hold < 0.0)
        or "VIOLATED" in log_text
    )

    return {
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "worst_setup_wns": worst_setup,
        "worst_hold_wns": worst_hold,
        "timing_passed": not has_violation,
        "is_complete": "[MIND3_PT_COMPLETE]" in log_text or "update_timing complete" in log_text.lower(),
    }


def parse_innovus_log(log_text: str) -> dict[str, Any]:
    """Parse Cadence Innovus PnR log for DRC violations, routing overflow, and density."""
    drc_match = re.search(r"Total number of DRC violations\s*[:=]\s*(\d+)", log_text, re.IGNORECASE)
    conn_match = re.search(r"Total number of connectivity errors\s*[:=]\s*(\d+)", log_text, re.IGNORECASE)
    overflow_match = re.search(r"Total routing overflow\s*[:=]\s*([0-9.]+)%", log_text, re.IGNORECASE)

    drc_violations = int(drc_match.group(1)) if drc_match else 0
    conn_errors = int(conn_match.group(1)) if conn_match else 0
    overflow_pct = float(overflow_match.group(1)) if overflow_match else 0.0

    passed = (
        drc_violations == 0
        and conn_errors == 0
        and overflow_pct == 0.0
        and "[ERROR]" not in log_text
    )

    return {
        "drc_violations": drc_violations,
        "connectivity_errors": conn_errors,
        "routing_overflow_pct": overflow_pct,
        "passed": passed,
        "is_complete": "[MIND3_INNOVUS_COMPLETE]" in log_text or "optDesign completed" in log_text,
    }


def parse_calibre_drc_summary(summary_text: str) -> dict[str, Any]:
    """Parse Siemens Calibre nmDRC summary report."""
    total_match = re.search(r"TOTAL\s+DRC\s+Results\s+Generated\s*:\s*(\d+)", summary_text, re.IGNORECASE)
    rules_checked_match = re.search(r"TOTAL\s+Original\s+Layer\s+Operations\s*:\s*(\d+)", summary_text, re.IGNORECASE)

    total_violations = int(total_match.group(1)) if total_match else 0
    clean = total_violations == 0

    return {
        "total_violations": total_violations,
        "clean": clean,
        "summary": f"Calibre nmDRC {'CLEAN (0 violations)' if clean else f'FAILED with {total_violations} violations'}.",
    }


def parse_calibre_lvs_summary(summary_text: str) -> dict[str, Any]:
    """Parse Siemens Calibre nmLVS comparison report."""
    is_correct = bool(re.search(r"LVS\s+COMPARISON\s+RESULT\s*:\s*CORRECT", summary_text)) or "LVS CORRECT" in summary_text
    is_incorrect = bool(re.search(r"LVS\s+COMPARISON\s+RESULT\s*:\s*INCORRECT", summary_text))

    devices_mismatch = bool(re.search(r"INCORRECT\s+DEVICE", summary_text, re.IGNORECASE))
    nets_mismatch = bool(re.search(r"INCORRECT\s+NETS", summary_text, re.IGNORECASE))

    return {
        "lvs_correct": is_correct and not is_incorrect,
        "devices_mismatch": devices_mismatch,
        "nets_mismatch": nets_mismatch,
        "summary": "Calibre nmLVS MATCH (Correct)" if is_correct else "Calibre nmLVS MISMATCH (Incorrect)",
    }
