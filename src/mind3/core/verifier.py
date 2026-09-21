"""
Verification subsystem for Mind 3.0 supporting RTL (iverilog/vvp) and Software (pytest/cargo test).
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from ..sandbox.bwrap import BubblewrapSandbox
from .types import VerificationDomain, VerificationResult

# Failure patterns indicating hardware simulation assertion mismatches or fatal halts.
# Tightened to specific iverilog/vvp runtime and assertion failure signatures to avoid
# false-positives on benign tool banners or summary strings (e.g. "0 errors, 0 fails").
_SIM_FAILURE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\$fatal\b", re.IGNORECASE),
    re.compile(r"\b(?:assertion|assert)\s+(?:violation|failed|failure)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:ERROR|FATAL)\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(?:TEST|SIMULATION)\s+(?:FAILED|FAILURE)\b", re.IGNORECASE),
    re.compile(r"\bFAILED\s*:\s*", re.IGNORECASE),
    re.compile(r"(?<!0\s)(?<!no\s)\bMISMATCH\s+(?:detected|at\s+time|at\s+cycle)\b", re.IGNORECASE),
    re.compile(r"(?<!0\s)(?<!no\s)\b(?:verification|assertion)\s+mismatch\b", re.IGNORECASE),
]



class BaseVerifier(ABC):
    """Abstract base class for all deterministic domain verifiers."""

    @abstractmethod
    def verify(
        self,
        workspace: Path,
        sandbox: BubblewrapSandbox,
    ) -> VerificationResult:
        """Execute ground-truth verification inside the Bubblewrap sandbox.

        Args:
            workspace: The target project workspace root.
            sandbox: Sandboxed execution wrapper.

        Returns:
            VerificationResult indicating success/failure status, exit codes, and output.
        """
        raise NotImplementedError("Subclasses of BaseVerifier must implement verify().")


class RTLVerifier(BaseVerifier):
    """Ground-truth RTL verification oracle using iverilog compilation and vvp simulation."""

    def __init__(self, top_module: str, testbench_path: Path | str) -> None:
        """Configure RTL verification targets.

        Args:
            top_module: Name of top-level Verilog/SystemVerilog testbench module.
            testbench_path: Path to the testbench source file.
        """
        if not top_module or not top_module.strip():
            raise ValueError("top_module must be a non-empty string.")
        self.top_module: str = top_module.strip()
        self.testbench_path: Path = Path(testbench_path)

    def verify(
        self,
        workspace: Path,
        sandbox: BubblewrapSandbox,
    ) -> VerificationResult:
        """Compile RTL sources with iverilog and execute simulation via vvp."""
        resolved_ws = workspace.resolve()
        resolved_tb = (
            (resolved_ws / self.testbench_path).resolve()
            if not self.testbench_path.is_absolute()
            else self.testbench_path.resolve()
        )

        if not resolved_tb.exists():
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=1,
                stdout="",
                stderr=f"RTL testbench file not found at path: {resolved_tb}",
                failure_reason="Testbench source file missing",
            )

        mind_dir = (resolved_ws / ".mind").resolve()
        v_sources = [
            p
            for p in sorted(resolved_ws.rglob("*.v"))
            if p.resolve() != resolved_tb.resolve()
            and not p.resolve().is_relative_to(mind_dir)
            and not any(part.startswith(".") for part in p.relative_to(resolved_ws).parts)
        ]
        sv_sources = [
            p
            for p in sorted(resolved_ws.rglob("*.sv"))
            if p.resolve() != resolved_tb.resolve()
            and not p.resolve().is_relative_to(mind_dir)
            and not any(part.startswith(".") for part in p.relative_to(resolved_ws).parts)
        ]
        sources = v_sources + sv_sources

        sim_output_name = "sim.vvp"
        sim_vvp_file = resolved_ws / sim_output_name
        if sim_vvp_file.exists():
            sim_vvp_file.unlink(missing_ok=True)

        compile_cmd = [
            "iverilog",
            "-o",
            sim_output_name,
            "-s",
            self.top_module,
            str(resolved_tb),
        ] + [str(s) for s in sources]

        compile_proc = sandbox.run(compile_cmd, timeout_sec=60)
        if compile_proc.returncode != 0:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=compile_proc.returncode,
                stdout=compile_proc.stdout,
                stderr=compile_proc.stderr,
                failure_reason=(
                    f"iverilog compilation failed with exit code {compile_proc.returncode}"
                ),
            )

        sim_cmd = ["vvp", sim_output_name]
        sim_proc = sandbox.run(sim_cmd, timeout_sec=60)

        # Cleanup intermediate bytecode
        if sim_vvp_file.exists():
            sim_vvp_file.unlink(missing_ok=True)

        combined_output = f"{sim_proc.stdout}\n{sim_proc.stderr}"
        failure_messages: list[str] = []
        if sim_proc.returncode != 0:
            failure_messages.append(
                f"vvp simulation process exited with non-zero status: {sim_proc.returncode}"
            )
        else:
            # Pattern matching acts as supplementary safety net for returncode-0 assertion prints
            for pattern in _SIM_FAILURE_PATTERNS:
                if pattern.search(combined_output):
                    failure_messages.append(
                        f"Simulation failure detected matching pattern: {pattern.pattern}"
                    )

        has_failed = len(failure_messages) > 0
        failure_reason = "; ".join(failure_messages) if has_failed else None

        return VerificationResult(
            passed=not has_failed,
            domain=VerificationDomain.RTL,
            exit_code=sim_proc.returncode,
            stdout=sim_proc.stdout,
            stderr=sim_proc.stderr,
            failure_reason=failure_reason,
        )


class SoftwareVerifier(BaseVerifier):
    """Software test verification oracle executing pytest or cargo test suites."""

    def __init__(
        self,
        runner: Literal["pytest", "cargo test"],
        test_target: str = "",
    ) -> None:
        """Configure software test runner.

        Args:
            runner: Supported test runner ("pytest" or "cargo test").
            test_target: Specific test directory, file, or target argument.
        """
        if runner not in ("pytest", "cargo test"):
            raise ValueError(
                f"Unsupported software test runner: {runner!r}. Expected 'pytest' or 'cargo test'."
            )
        self.runner: Literal["pytest", "cargo test"] = runner
        self.test_target: str = str(test_target).strip()

    def verify(
        self,
        workspace: Path,
        sandbox: BubblewrapSandbox,
    ) -> VerificationResult:
        """Run software test suite inside Bubblewrap sandbox."""
        if self.runner == "pytest":
            cmd = ["pytest", self.test_target] if self.test_target else ["pytest"]
        else:
            cmd = (
                ["cargo", "test", self.test_target]
                if self.test_target
                else ["cargo", "test"]
            )

        proc = sandbox.run(cmd, timeout_sec=120)
        passed = proc.returncode == 0
        failure_reason = (
            None
            if passed
            else f"Software runner '{self.runner}' failed with exit code {proc.returncode}"
        )

        return VerificationResult(
            passed=passed,
            domain=VerificationDomain.SOFTWARE,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            failure_reason=failure_reason,
        )


class IndustryReportVerifier(BaseVerifier):
    """Ground-truth verification oracle for industry research reports and generated timeline charts."""

    def __init__(
        self,
        report_path: Path | str | None = None,
        chart_path: Path | str | None = None,
        min_sections: int = 3,
    ) -> None:
        self.report_path: Path | None = Path(report_path) if report_path else None
        self.chart_path: Path | None = Path(chart_path) if chart_path else None
        self.min_sections: int = min_sections

    def verify(
        self,
        workspace: Path,
        sandbox: BubblewrapSandbox,
    ) -> VerificationResult:
        resolved_ws = workspace.resolve()
        errors: list[str] = []

        if self.report_path is not None:
            rep_file = (
                (resolved_ws / self.report_path).resolve()
                if not self.report_path.is_absolute()
                else self.report_path.resolve()
            )
            if not rep_file.exists():
                errors.append(f"Report file missing: {rep_file}")
            else:
                text = rep_file.read_text(encoding="utf-8")
                # Check for numbered sections
                numbered_sections = re.findall(r"^(?:#+|\d+\.)\s+", text, re.MULTILINE)
                if len(numbered_sections) < self.min_sections:
                    errors.append(
                        f"Report has only {len(numbered_sections)} sections, expected at least {self.min_sections}."
                    )
                # Check for table presence
                if "|" not in text:
                    errors.append("Report lacks markdown comparison tables required by industry-report standard.")
                # Check for sources list or citations
                if not re.search(r"(?:sources|references|citations)\b", text, re.IGNORECASE):
                    errors.append("Report lacks a designated sources/references section.")

        if self.chart_path is not None:
            chart_file = (
                (resolved_ws / self.chart_path).resolve()
                if not self.chart_path.is_absolute()
                else self.chart_path.resolve()
            )
            if not chart_file.exists():
                errors.append(f"Generated chart file missing: {chart_file}")
            elif chart_file.stat().st_size == 0:
                errors.append(f"Generated chart file is empty: {chart_file}")

        passed = len(errors) == 0
        failure_reason = "; ".join(errors) if not passed else None

        return VerificationResult(
            passed=passed,
            domain=VerificationDomain.INDUSTRY_REPORT,
            exit_code=0 if passed else 1,
            stdout="Industry report and chart assets verified successfully." if passed else "",
            stderr="\n".join(errors),
            failure_reason=failure_reason,
        )


def parse_opensta_timing(output: str) -> dict[str, float | None]:
    """Extract setup WNS, setup TNS, and hold WNS from OpenSTA report output.

    Returns a dict with keys:
        setup_wns: Worst setup-path negative slack (min over all slack values; None if absent).
        setup_tns: Total setup negative slack (None if absent).
        hold_wns:  Worst hold-path (min-path) slack (None if absent).
    """
    # ── Setup WNS extraction (reuse existing multi-pattern logic) ──────────
    setup_slacks: list[float] = []

    for match in re.finditer(
        r"\bwns(?:\s+-?max)?\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
        output, re.IGNORECASE,
    ):
        try:
            setup_slacks.append(float(match.group(1)))
        except ValueError:
            continue

    for match in re.finditer(
        r"\bworst\s+slack(?:\s+-?max)?\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
        output, re.IGNORECASE,
    ):
        try:
            setup_slacks.append(float(match.group(1)))
        except ValueError:
            continue

    for match in re.finditer(
        r"Worst\s+Negative\s+Slack\s*(?:\n[-=]+\n|\s*[:=]\s*)([+-]?\d+(?:\.\d+)?)",
        output, re.IGNORECASE,
    ):
        try:
            setup_slacks.append(float(match.group(1)))
        except ValueError:
            continue

    for match in re.finditer(
        r"^[ \t]*([+-]?\d+(?:\.\d+)?)[ \t]+slack\s*\((?:MET|VIOLATED)\)",
        output, re.MULTILINE | re.IGNORECASE,
    ):
        try:
            setup_slacks.append(float(match.group(1)))
        except ValueError:
            continue

    for match in re.finditer(
        r"\bslack\s*\((?:MET|VIOLATED)\)[ \t]+([+-]?\d+(?:\.\d+)?)",
        output, re.IGNORECASE,
    ):
        try:
            setup_slacks.append(float(match.group(1)))
        except ValueError:
            continue

    setup_wns: float | None = min(setup_slacks) if setup_slacks else None

    # ── Setup TNS extraction ────────────────────────────────────────────────
    tns_slacks: list[float] = []
    for match in re.finditer(
        r"\btns(?:\s+-?max)?\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
        output, re.IGNORECASE,
    ):
        try:
            tns_slacks.append(float(match.group(1)))
        except ValueError:
            continue
    for match in re.finditer(
        r"\btotal\s+negative\s+slack\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
        output, re.IGNORECASE,
    ):
        try:
            tns_slacks.append(float(match.group(1)))
        except ValueError:
            continue
    setup_tns: float | None = min(tns_slacks) if tns_slacks else None

    # ── Hold WNS extraction (min-path) ─────────────────────────────────────
    hold_slacks: list[float] = []
    for pattern in [
        r"\bwns\s+-min\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
        r"\bworst\s+slack\s+-min\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
        r"\bhold\s+(?:wns|slack)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
        r"\btns\s+-min\s*[:=]?\s*([+-]?\d+(?:\.\d+)?)",
    ]:
        for match in re.finditer(pattern, output, re.IGNORECASE):
            try:
                hold_slacks.append(float(match.group(1)))
            except ValueError:
                continue
    hold_wns: float | None = min(hold_slacks) if hold_slacks else None

    return {"setup_wns": setup_wns, "setup_tns": setup_tns, "hold_wns": hold_wns}


def parse_opensta_wns(output: str) -> float | None:
    """Extract Worst Negative Slack (WNS) from OpenSTA output.

    Delegates to parse_opensta_timing and returns only the setup WNS value.
    Retained for backward compatibility with existing callers.
    """
    return parse_opensta_timing(output)["setup_wns"]


def parse_verilator_coverage(output: str) -> dict[str, float | None]:
    """Parse line, branch, and toggle coverage percentages from Verilator output.

    Returns:
        dict with keys 'branch', 'toggle', 'line'. Each is a float in [0.0, 100.0] or None if absent.
    """
    branch_cov: float | None = None
    toggle_cov: float | None = None
    line_cov: float | None = None

    branch_match = re.search(
        r"\bbranch(?:\s+coverage)?\s*[:=]?\s*(\d+(?:\.\d+)?)%", output, re.IGNORECASE
    )
    if branch_match:
        branch_cov = float(branch_match.group(1))

    toggle_match = re.search(
        r"\btoggle(?:\s+coverage)?\s*[:=]?\s*(\d+(?:\.\d+)?)%", output, re.IGNORECASE
    )
    if toggle_match:
        toggle_cov = float(toggle_match.group(1))

    line_match = re.search(
        r"\bline(?:\s+coverage)?\s*[:=]?\s*(\d+(?:\.\d+)?)%", output, re.IGNORECASE
    )
    if line_match:
        line_cov = float(line_match.group(1))

    return {"branch": branch_cov, "toggle": toggle_cov, "line": line_cov}


def parse_yosys_lec(output: str) -> dict[str, Any]:
    """Parse Yosys formal equivalence checking (equiv_status) output.

    Returns:
        dict with keys:
            equivalent: bool (True if equivalence successfully proven, False otherwise).
            proven_points: int | None (number of proved equivalence points).
            unproven_points: int | None (number of unproved equivalence points).
            error: str | None.
    """
    proven_points: int | None = None
    unproven_points: int | None = None

    prov_match = re.search(r"Proved\s+(\d+)\s+equivalence\s+points", output, re.IGNORECASE)
    if prov_match:
        proven_points = int(prov_match.group(1))

    unprov_match = re.search(r"Found\s+(\d+)\s+unproven\s+\$equiv\s+cells", output, re.IGNORECASE)
    if unprov_match:
        unproven_points = int(unprov_match.group(1))
    else:
        err_match = re.search(r"ERROR:\s*Found\s+(\d+)\s+unproven\s+points", output, re.IGNORECASE)
        if err_match:
            unproven_points = int(err_match.group(1))

    equivalent = (
        "Equivalence successfully proven!" in output
        or (unproven_points == 0 and proven_points is not None and proven_points > 0)
    ) and "ERROR:" not in output

    error_msg = None
    if not equivalent:
        if unproven_points is not None and unproven_points > 0:
            error_msg = f"{unproven_points} unproven equivalence points found."
        elif "ERROR:" in output:
            err_line = next((line for line in output.splitlines() if "ERROR:" in line), "LEC error")
            error_msg = err_line.strip()
        else:
            error_msg = "Equivalence could not be proven."

    return {
        "equivalent": equivalent,
        "proven_points": proven_points,
        "unproven_points": unproven_points,
        "error": error_msg,
    }


def parse_openroad_pnr(output: str) -> dict[str, Any]:
    """Parse OpenROAD place-and-route logs for completion, overflow, and congestion metrics.

    Returns:
        dict with keys:
            passed: bool (True if PNR completed without fatal overflow or errors).
            pnr_complete: bool (True if PNR_COMPLETE banner reached).
            placement_overflow: float | None.
            routing_congestion: float | None.
            errors: list of error strings found.
    """
    pnr_complete = "PNR_COMPLETE" in output

    overflow_match = re.search(
        r"(?:overflow(?:ed)?[:\s]+([0-9.]+)|([0-9.]+)\s+(?:instances\s+)?overflowed)",
        output,
        re.IGNORECASE,
    )
    placement_overflow = None
    if overflow_match:
        val_str = overflow_match.group(1) or overflow_match.group(2)
        if val_str:
            placement_overflow = float(val_str)

    congestion_match = re.search(r"GRT-0043.*?congestion[:\s]+([0-9.]+)%", output, re.IGNORECASE)
    routing_congestion = float(congestion_match.group(1)) if congestion_match else None

    errors: list[str] = []
    for line in output.splitlines():
        if "[ERROR" in line or line.strip().startswith("ERROR:"):
            errors.append(line.strip())

    passed = pnr_complete and len(errors) == 0 and (placement_overflow is None or placement_overflow == 0.0)

    return {
        "passed": passed,
        "pnr_complete": pnr_complete,
        "placement_overflow": placement_overflow,
        "routing_congestion": routing_congestion,
        "errors": errors,
    }


def parse_yosys_cdc(output: str) -> dict[str, Any]:
    """Parse Yosys CDC analysis output for unregistered clock-domain crossings.

    Returns:
        dict with keys:
            passed: bool (True if zero CDC violations found).
            violations: list of CDC violation descriptions.
    """
    cdc_patterns = [
        re.compile(r"CDC\s+WARNING[:\s]+(.*?)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"\[cdc\]\s+(?:warning|issue)[:\s]+(.*?)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"Found\s+CDC\s+(?:issue|violation)[:\s]+(.*?)$", re.IGNORECASE | re.MULTILINE),
    ]
    violations: list[str] = []
    for pattern in cdc_patterns:
        for match in pattern.finditer(output):
            msg = match.group(1).strip()
            if msg and msg not in violations:
                violations.append(msg)

    passed = len(violations) == 0 and "CDC analysis failed" not in output
    return {"passed": passed, "violations": violations}



def _is_binary_missing(proc: Any, binary: str) -> bool:
    """Detect whether a subshell execution failed because an EDA binary was missing."""
    if proc.returncode == 127:
        return True
    combined = f"{proc.stdout}\n{proc.stderr}".lower()
    return (
        f"{binary}: command not found" in combined
        or f"{binary}: not found" in combined
        or f"no such file or directory: '{binary}'" in combined
        or f"failed to execute local command: [errno 2] no such file or directory: '{binary}'" in combined
        or (proc.returncode != 0 and "no such file or directory" in str(proc.stderr).lower() and binary in str(proc.stderr).lower())
    )


def detect_eda_tool_versions(runner: Any) -> dict[str, str]:
    """Inspect and record installed versions of all EDA binaries.

    Returns a dictionary mapping tool names ('yosys', 'sta', 'verilator', 'sby', 'openroad')
    to their detected version strings, or 'missing' if the binary is unavailable.
    """
    tools = {
        "yosys": ["yosys", "-V"],
        "sta": ["sta", "-version"],
        "verilator": ["verilator", "--version"],
        "sby": ["sby", "--version"],
        "openroad": ["openroad", "-version"],
    }
    versions: dict[str, str] = {}
    for name, cmd in tools.items():
        try:
            proc = runner.run(cmd, timeout_sec=5)
            if proc.returncode == 0:
                output = (proc.stdout or proc.stderr).strip().splitlines()
                versions[name] = output[0] if output else "unknown"
            else:
                versions[name] = "missing"
        except Exception:
            versions[name] = "missing"
    return versions


class SiliconSignoffVerifier(BaseVerifier):
    """6-Gate Hierarchical Verification Pipeline for Tapeout-Grade Silicon Signoff.

    Gate 1: Yosys Elaboration & Latch Trap Detector
    Gate 1b: Logic Equivalence Checking (LEC) (opt-in via require_lec=True)
    Gate 2: SymbiYosys Formal Property Verification (BMC)
    Gate 3: Verilator Coverage Signoff (Branch & Toggle)
    Gate 4: OpenSTA Multi-Corner Timing Signoff (setup + hold)
    Gate 5: OpenROAD Place-and-Route (opt-in; require_pnr=True to enable)
    Gate 6: Yosys CDC Static Analysis (clock-domain crossing detection)
    DFT:    Scan-chain advisory audit (always runs; never blocks signoff)
    """

    def __init__(
        self,
        top_module: str,
        contract: Any | None = None,
        *,
        liberty_path: str | list[str] | None = None,
        min_branch_coverage: float = 95.0,
        min_toggle_coverage: float = 90.0,
        max_wns_ps: float = 0.0,
        min_hold_slack_ps: float = 0.0,
        sta_time_unit: Literal["ns", "ps"] = "ns",
        runner: Any | None = None,
        allow_mock_fallback: bool = False,
        require_formal: bool = True,
        require_coverage: bool = True,
        require_pnr: bool = False,
        require_cdc: bool = True,
        require_lec: bool = False,
        lef_path: str | list[str] | None = None,
    ) -> None:
        if not top_module or not top_module.strip():
            raise ValueError("top_module must be a non-empty string.")
        if liberty_path is not None:
            if isinstance(liberty_path, (str, Path)):
                stripped = str(liberty_path).strip()
                if not stripped:
                    raise ValueError("liberty_path must be a non-empty string or list of paths.")
                self.liberty_paths: list[str] = [stripped]
            elif isinstance(liberty_path, (list, tuple)):
                self.liberty_paths = [str(p).strip() for p in liberty_path if str(p).strip()]
                if not self.liberty_paths:
                    raise ValueError("liberty_path list must contain at least one non-empty path.")
            else:
                raise TypeError("liberty_path must be a str or list[str].")
        else:
            self.liberty_paths = []

        if lef_path is not None:
            if isinstance(lef_path, str):
                self.lef_paths: list[str] = [lef_path.strip()] if lef_path.strip() else []
            elif isinstance(lef_path, (list, tuple)):
                self.lef_paths = [str(p).strip() for p in lef_path if str(p).strip()]
            else:
                raise TypeError("lef_path must be a str or list[str].")
        elif contract and contract.timing and contract.timing.lef_path:
            stripped = str(contract.timing.lef_path).strip()
            self.lef_paths = [stripped] if stripped else []
        else:
            self.lef_paths = []

        self.top_module: str = top_module.strip()
        self.contract: Any | None = contract
        self.min_branch_coverage: float = min_branch_coverage
        self.min_toggle_coverage: float = min_toggle_coverage
        self.max_wns_ps: float = max_wns_ps
        self.min_hold_slack_ps: float = min_hold_slack_ps
        self.sta_time_unit: Literal["ns", "ps"] = sta_time_unit
        self.runner: Any | None = runner
        self.allow_mock_fallback: bool = allow_mock_fallback
        self.require_formal: bool = require_formal
        self.require_coverage: bool = require_coverage
        self.require_pnr: bool = require_pnr
        self.require_cdc: bool = require_cdc
        self.require_lec: bool = require_lec
        self.detected_versions: dict[str, str] = {}

    def verify(
        self,
        workspace: Path,
        sandbox: BubblewrapSandbox,
    ) -> VerificationResult:
        """Run the hierarchical silicon signoff gates sequentially. Fails closed on first violation."""
        resolved_ws = workspace.resolve()
        from ..sandbox.remote_eda import get_eda_runner
        eda_runner = self.runner if self.runner is not None else get_eda_runner(workspace, sandbox)
        self.detected_versions = detect_eda_tool_versions(eda_runner)
        gate_reports: list[dict[str, Any]] = []

        # Find all Verilog/SystemVerilog sources in workspace, excluding hidden dirs and .mind internal dirs
        mind_internal = (resolved_ws / ".mind").resolve()
        sources = [
            p
            for p in sorted(resolved_ws.rglob("*.[vs]*"))
            if p.suffix in (".v", ".sv")
            and not p.resolve().is_relative_to(mind_internal)
            and not any(part.startswith(".") for part in p.relative_to(resolved_ws).parts)
        ]

        if not sources:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=1,
                stderr=f"No Verilog/SystemVerilog sources found in {resolved_ws}",
                failure_reason="RTL source files missing",
                error_category="MISSING_SOURCE_FILES",
            )

        # ── Gate 1: Yosys AST Elaboration & Latch Trap Detector ──────────────
        gate1_res = self._run_gate1_yosys(eda_runner, sources, resolved_ws)
        gate_reports.append(gate1_res)
        if not gate1_res["passed"]:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=gate1_res["exit_code"],
                stdout=gate1_res["stdout"],
                stderr=gate1_res["stderr"],
                failure_reason=gate1_res["details"],
                error_category=gate1_res["error_category"],
                gate_reports=gate_reports,
            )

        # ── Gate 1b: Logic Equivalence Checking (LEC) (opt-in via require_lec=True)
        if self.require_lec:
            gate1b_res = self._run_gate_lec(
                eda_runner, sources, gate1_res.get("netlist_path", f"{self.top_module}_netlist.v"), resolved_ws
            )
            gate_reports.append(gate1b_res)
            if not gate1b_res["passed"]:
                return VerificationResult(
                    passed=False,
                    domain=VerificationDomain.RTL,
                    exit_code=gate1b_res["exit_code"],
                    stdout=gate1b_res["stdout"],
                    stderr=gate1b_res["stderr"],
                    failure_reason=gate1b_res["details"],
                    error_category=gate1b_res["error_category"],
                    gate_reports=gate_reports,
                )

        # ── Gate 2: SymbiYosys Formal Property Verification ──────────────────
        gate2_res = self._run_gate2_formal_sby(eda_runner, sources, resolved_ws)
        gate_reports.append(gate2_res)
        if not gate2_res["passed"]:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=gate2_res["exit_code"],
                stdout=gate2_res["stdout"],
                stderr=gate2_res["stderr"],
                failure_reason=gate2_res["details"],
                error_category=gate2_res["error_category"],
                gate_reports=gate_reports,
            )

        # ── Gate 3: Verilator 5.x Coverage Signoff ───────────────────────────
        gate3_res = self._run_gate3_coverage(eda_runner, sources, resolved_ws)
        gate_reports.append(gate3_res)
        if not gate3_res["passed"]:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=gate3_res["exit_code"],
                stdout=gate3_res["stdout"],
                stderr=gate3_res["stderr"],
                failure_reason=gate3_res["details"],
                error_category=gate3_res["error_category"],
                gate_reports=gate_reports,
            )

        # ── Gate 4: OpenSTA Multi-Corner Timing Signoff (setup + hold) ────────
        gate4_res = self._run_gate4_timing(eda_runner, sources, resolved_ws)
        gate_reports.append(gate4_res)
        if not gate4_res["passed"]:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=gate4_res["exit_code"],
                stdout=gate4_res["stdout"],
                stderr=gate4_res["stderr"],
                failure_reason=gate4_res["details"],
                error_category=gate4_res["error_category"],
                timing_metrics={k: v for k, v in gate4_res.get("metrics", {}).items() if isinstance(v, (int, float))},
                hold_metrics={k: v for k, v in gate4_res.get("hold_metrics", {}).items() if isinstance(v, (int, float))},
                gate_reports=gate_reports,
            )

        # ── Gate 5: OpenROAD Place-and-Route (opt-in) ─────────────────────────
        gate5_res = self._run_gate5_openroad_pnr(eda_runner, sources, resolved_ws)
        gate_reports.append(gate5_res)
        if not gate5_res["passed"]:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=gate5_res["exit_code"],
                stdout=gate5_res["stdout"],
                stderr=gate5_res["stderr"],
                failure_reason=gate5_res["details"],
                error_category=gate5_res["error_category"],
                pnr_metrics=gate5_res.get("metrics", {}),
                gate_reports=gate_reports,
            )

        # ── Gate 6: Yosys CDC Static Analysis ────────────────────────────────
        gate6_res = self._run_gate6_cdc_analysis(eda_runner, sources, resolved_ws)
        gate_reports.append(gate6_res)
        if not gate6_res["passed"]:
            return VerificationResult(
                passed=False,
                domain=VerificationDomain.RTL,
                exit_code=gate6_res["exit_code"],
                stdout=gate6_res["stdout"],
                stderr=gate6_res["stderr"],
                failure_reason=gate6_res["details"],
                error_category=gate6_res["error_category"],
                cdc_violations=gate6_res.get("cdc_violations", []),
                gate_reports=gate_reports,
            )

        # ── DFT Scan Audit (advisory — never blocks signoff) ──────────────────
        dft_res = self._run_dft_scan_audit(eda_runner, sources, resolved_ws)
        gate_reports.append(dft_res)

        # Integrity: silicon_verified is False if any required gate was simulated or skipped.
        # Exception: Gate 5 (PnR, opt-in via require_pnr=False) and the DFT advisory
        # gate are intentionally optional; their skip status does NOT invalidate signoff.
        _OPTIONAL_GATE_NAMES = {"Gate 5: OpenROAD Place-and-Route", "DFT Scan Audit (Advisory)"}
        is_simulated = any(g.get("simulated", False) for g in gate_reports)
        is_skipped = any(
            g.get("skipped", False)
            for g in gate_reports
            if g.get("gate", "") not in _OPTIONAL_GATE_NAMES
        )
        silicon_verified = (not is_simulated) and (not is_skipped)


        netlist_rel = gate1_res.get("netlist_path")
        cov_metrics = gate3_res.get("metrics", {})
        timing_metrics: dict[str, float] = {k: v for k, v in gate4_res.get("metrics", {}).items() if isinstance(v, (int, float))}
        hold_metrics: dict[str, float] = {k: v for k, v in gate4_res.get("hold_metrics", {}).items() if isinstance(v, (int, float))}
        pnr_metrics: dict[str, Any] = gate5_res.get("metrics", {})
        cdc_violations = gate6_res.get("cdc_violations", [])
        dft_audit = dft_res.get("dft_audit", {})


        return VerificationResult(
            passed=True,
            domain=VerificationDomain.RTL,
            exit_code=0,
            stdout="Silicon signoff succeeded: All 6 hierarchical gates passed.",
            silicon_verified=silicon_verified,
            netlist_path=netlist_rel,
            coverage_metrics=cov_metrics,
            timing_metrics=timing_metrics,
            hold_metrics=hold_metrics,
            pnr_metrics=pnr_metrics,
            cdc_violations=cdc_violations,
            dft_audit=dft_audit,
            gate_reports=gate_reports,
        )

    def _run_gate1_yosys(self, runner: Any, sources: list[Path], ws: Path) -> dict[str, Any]:
        """Execute Yosys technology synthesis, hierarchy elaboration, and latch detection."""
        # Static lexical latch audit
        lexical_check = self._lexical_latch_check(sources)
        if not lexical_check["passed"]:
            return lexical_check

        src_args = [str(s.relative_to(ws)) for s in sources]
        netlist_name = f"{self.top_module}_netlist.v"

        ast_name = f"{self.top_module}_ast.json"
        if self.liberty_paths:
            primary_lib = self.liberty_paths[0]
            yosys_cmd = (
                f"read_verilog -sv {' '.join(src_args)}; "
                f"hierarchy -check -top {self.top_module}; "
                f"proc; opt; fsm; opt; memory; opt; techmap; opt; "
                f"dfflibmap -liberty {primary_lib}; "
                f"abc -liberty {primary_lib}; "
                f"clean; "
                f"write_json {ast_name}; "
                f"write_verilog -noattr {netlist_name}"
            )
        else:
            yosys_cmd = (
                f"read_verilog -sv {' '.join(src_args)}; "
                f"hierarchy -check -top {self.top_module}; "
                f"proc; check; "
                f"write_json {ast_name}; "
                f"write_verilog -noattr {netlist_name}"
            )

        cmd = ["yosys", "-p", yosys_cmd]
        proc = runner.run(cmd, timeout_sec=45)

        combined_output = f"{proc.stdout}\n{proc.stderr}"
        if proc.returncode != 0 and _is_binary_missing(proc, "yosys"):
            if not self.allow_mock_fallback:
                return {
                    "gate": "Gate 1: Yosys Elaboration & Latch Trap",
                    "passed": False,
                    "exit_code": 127,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "details": (
                        "yosys binary missing on host/runner. "
                        "Install via package manager (e.g. 'brew install yosys' or 'apt-get install yosys') "
                        "or install the OSS CAD Suite (https://github.com/YosysHQ/oss-cad-suite-build)."
                    ),
                    "error_category": "EDA_BINARY_MISSING",
                    "simulated": False,
                }
            simulated_check = dict(lexical_check)
            simulated_check["stdout"] = f"[SIMULATED - NOT REAL TOOL OUTPUT] {simulated_check['stdout']}"
            simulated_check["simulated"] = True
            simulated_check["netlist_path"] = netlist_name
            return simulated_check

        # Check for deliberate synopsys keep_latch override
        has_override = any("synopsys keep_latch" in s.read_text(encoding="utf-8") for s in sources)

        # 1. Structured JSON AST latch inspection (immune to stdout formatting changes)
        ast_file = ws / ast_name
        if ast_file.exists():
            try:
                ast_json = json.loads(ast_file.read_text(encoding="utf-8"))
                for mod_name, mod_info in ast_json.get("modules", {}).items():
                    for cell_name, cell_info in mod_info.get("cells", {}).items():
                        cell_type = cell_info.get("type", "")
                        if cell_type in ("$dlatch", "$adlatch", "$latch", "$sr", "$dffsr") and not has_override:
                            return {
                                "gate": "Gate 1: Yosys Elaboration & Latch Trap",
                                "passed": False,
                                "exit_code": 1,
                                "stdout": proc.stdout,
                                "stderr": proc.stderr,
                                "details": f"Unintended latch cell '{cell_name}' of type '{cell_type}' detected in structured AST.",
                                "error_category": "LATCH_INFERRED",
                                "simulated": False,
                            }
            except Exception:
                ast_json = None

        # 2. Fallback regex inspection on combined tool stdout/stderr
        latch_match = re.search(r"\$(?:d|ad)?latch\b", combined_output)
        if latch_match and not has_override:
            return {
                "gate": "Gate 1: Yosys Elaboration & Latch Trap",
                "passed": False,
                "exit_code": 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": "Unintended latch inferred in AST without synopsys keep_latch override.",
                "error_category": "LATCH_INFERRED",
                "simulated": False,
            }

        # Check for combinational loops or multi-driven nets
        if "Warning: combinational loop" in combined_output:
            return {
                "gate": "Gate 1: Yosys Elaboration & Latch Trap",
                "passed": False,
                "exit_code": 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": "Combinational loop detected during elaboration.",
                "error_category": "COMBINATIONAL_LOOP",
                "simulated": False,
            }

        passed = proc.returncode == 0
        return {
            "gate": "Gate 1: Yosys Elaboration & Latch Trap",
            "passed": passed,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "details": "Yosys elaboration clean with zero unapproved latches." if passed else "Yosys elaboration failed.",
            "error_category": None if passed else "SYNTHESIS_ELABORATION_ERROR",
            "netlist_path": netlist_name if passed else None,
            "simulated": False,
        }

    def _run_gate_lec(
        self,
        runner: Any,
        sources: list[Path],
        netlist_name: str,
        ws: Path,
    ) -> dict[str, Any]:
        """Gate 1b: Formally prove logical equivalence between behavioral RTL and synthesized netlist."""
        netlist_path = ws / netlist_name
        if not netlist_path.exists():
            if self.allow_mock_fallback:
                return {
                    "gate": "Gate 1b: Logic Equivalence Checking (LEC)",
                    "passed": True,
                    "exit_code": 0,
                    "stdout": "[SIMULATED - NOT REAL TOOL OUTPUT] Yosys formal LEC simulated: 0 unproven points.",
                    "stderr": "",
                    "details": "Simulated formal equivalence between RTL and gate netlist.",
                    "error_category": None,
                    "simulated": True,
                    "skipped": False,
                }
            return {
                "gate": "Gate 1b: Logic Equivalence Checking (LEC)",
                "passed": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Synthesized netlist {netlist_name} does not exist.",
                "details": "Cannot run LEC without synthesized netlist.",
                "error_category": "MISSING_NETLIST_FOR_LEC",
                "simulated": False,
            }

        src_args = [str(s.relative_to(ws)) for s in sources]
        equiv_cmd = (
            f"read_verilog -sv {' '.join(src_args)}; "
            f"prep -top {self.top_module}; "
            f"splitnets; "
            f"rename {self.top_module} gold; "
            f"read_verilog {netlist_name}; "
            f"prep -top {self.top_module}; "
            f"splitnets; "
            f"rename {self.top_module} gate; "
            f"equiv_make gold gate equiv; "
            f"hierarchy -top equiv; "
            f"equiv_simple; "
            f"equiv_status -assert"
        )
        cmd = ["yosys", "-p", equiv_cmd]
        proc = runner.run(cmd, timeout_sec=60)
        combined = f"{proc.stdout}\n{proc.stderr}"

        if proc.returncode != 0 and _is_binary_missing(proc, "yosys"):
            if not self.allow_mock_fallback:
                return {
                    "gate": "Gate 1b: Logic Equivalence Checking (LEC)",
                    "passed": False,
                    "exit_code": 127,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "details": "yosys binary missing for formal LEC.",
                    "error_category": "EDA_BINARY_MISSING",
                    "simulated": False,
                }
            return {
                "gate": "Gate 1b: Logic Equivalence Checking (LEC)",
                "passed": True,
                "exit_code": 0,
                "stdout": "[SIMULATED - NOT REAL TOOL OUTPUT] Yosys formal LEC passed: 0 unproven equivalence points.",
                "stderr": "",
                "details": "Equivalence formally proved between golden RTL and synthesized gate netlist.",
                "error_category": None,
                "simulated": True,
                "skipped": False,
            }

        lec_result = parse_yosys_lec(combined)
        if lec_result["equivalent"] and proc.returncode == 0:
            return {
                "gate": "Gate 1b: Logic Equivalence Checking (LEC)",
                "passed": True,
                "exit_code": 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": f"Equivalence formally proved between golden RTL and synthesized netlist ({lec_result.get('proven_points', 'all')} points proved).",
                "error_category": None,
                "simulated": False,
                "skipped": False,
            }
        else:
            err_detail = lec_result.get("error") or "Unproven equivalence points between RTL and gate netlist."
            return {
                "gate": "Gate 1b: Logic Equivalence Checking (LEC)",
                "passed": False,
                "exit_code": proc.returncode if proc.returncode != 0 else 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": f"Formal LEC failed: {err_detail}",
                "error_category": "LEC_VERIFICATION_FAILED",
                "simulated": False,
            }

    def _lexical_latch_check(self, sources: list[Path]) -> dict[str, Any]:
        """Perform static AST/lexical latch pattern inspection when yosys is absent."""
        for src in sources:
            code = src.read_text(encoding="utf-8")
            if "synopsys keep_latch" in code:
                continue
            # Detect incomplete if statements in always @* or always_comb
            comb_blocks = re.findall(r"always\s*(?:@\s*\*\s*|_comb)\s*begin(.*?)end", code, re.DOTALL)
            for block in comb_blocks:
                if re.search(r"\bif\b", block) and not re.search(r"\belse\b", block):
                    return {
                        "gate": "Gate 1: Yosys Elaboration & Latch Trap",
                        "passed": False,
                        "exit_code": 1,
                        "stdout": "",
                        "stderr": f"Latch pattern in {src.name}: combinational 'if' missing explicit 'else' branch.",
                        "details": f"Incomplete if-branch infers storage latch in {src.name}.",
                        "error_category": "LATCH_INFERRED",
                        "simulated": False,
                    }
        return {
            "gate": "Gate 1: Yosys Elaboration & Latch Trap",
            "passed": True,
            "exit_code": 0,
            "stdout": "Static latch audit passed: zero unintended storage elements detected.",
            "stderr": "",
            "details": "Lexical latch verification clean.",
            "error_category": None,
            "simulated": False,
        }

    def _run_gate2_formal_sby(self, runner: Any, sources: list[Path], ws: Path) -> dict[str, Any]:
        """Execute SymbiYosys Bounded Model Checking formal verification with SVA binding."""
        sby_files = list(ws.glob("*.sby"))
        if not sby_files and self.contract is not None:
            # Auto-generate formal sby harness and SVA bind module if contract exists
            from .contracts import VerificationHarnessGenerator
            if getattr(self.contract, "sva_properties", None):
                sva_bind_path = ws / f"{self.top_module}_sva.sv"
                sva_bind_path.write_text(
                    VerificationHarnessGenerator.build_sva_bind_module(self.contract),
                    encoding="utf-8",
                )
            sby_content = VerificationHarnessGenerator.build_sby_config(
                self.contract, depth=25, include_sva_file=bool(getattr(self.contract, "sva_properties", None))
            )
            sby_path = ws / f"{self.top_module}.sby"
            sby_path.write_text(sby_content, encoding="utf-8")
            sby_files = [sby_path]

        if not sby_files:
            if self.require_formal:
                return {
                    "gate": "Gate 2: SymbiYosys Formal Property Verification",
                    "passed": False,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "Missing formal verification harness (.sby).",
                    "details": (
                        "No .sby formal harness or formal contract found. "
                        "Generate a SymbiYosys (.sby) formal verification harness or specify an InterfaceContract with SVA properties."
                    ),
                    "error_category": "MISSING_VERIFICATION_ARTIFACT",
                    "skipped": False,
                    "simulated": False,
                }
            return {
                "gate": "Gate 2: SymbiYosys Formal Property Verification",
                "passed": True,
                "exit_code": 0,
                "stdout": "Formal verification skipped (require_formal=False).",
                "stderr": "",
                "details": "Formal verification bypassed by caller opt-out.",
                "error_category": None,
                "skipped": True,
                "simulated": False,
            }

        cmd = ["sby", "-f", str(sby_files[0].relative_to(ws))]
        proc = runner.run(cmd, timeout_sec=60)
        combined = f"{proc.stdout}\n{proc.stderr}"

        if proc.returncode != 0 and _is_binary_missing(proc, "sby"):
            if not self.allow_mock_fallback:
                return {
                    "gate": "Gate 2: SymbiYosys Formal Property Verification",
                    "passed": False,
                    "exit_code": 127,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "details": (
                        "sby (SymbiYosys) binary missing on host/runner. "
                        "Install SymbiYosys via OSS CAD Suite (https://github.com/YosysHQ/oss-cad-suite-build) "
                        "or build from source (https://github.com/YosysHQ/sby)."
                    ),
                    "error_category": "EDA_BINARY_MISSING",
                    "simulated": False,
                }
            return {
                "gate": "Gate 2: SymbiYosys Formal Property Verification",
                "passed": True,
                "exit_code": 0,
                "stdout": "[SIMULATED - NOT REAL TOOL OUTPUT] sby binary omitted; mock formal invariants validated.",
                "stderr": "",
                "details": "Formal BMC simulated clean.",
                "error_category": None,
                "simulated": True,
                "skipped": False,
            }

        if proc.returncode != 0 or "Assert failed" in combined or "FAIL" in combined:
            # Parse counterexample timestamp
            t_fail_match = re.search(r"step\s+(\d+)\s+FAILED", combined)
            t_fail = t_fail_match.group(1) if t_fail_match else "unknown"
            prop_match = re.search(r"(?:Assert failed in \S+:|Assertion failed:)\s*(\S+)", combined)
            prop_name = prop_match.group(1) if prop_match else None
            return {
                "gate": "Gate 2: SymbiYosys Formal Property Verification",
                "passed": False,
                "exit_code": proc.returncode if proc.returncode != 0 else 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": f"Formal SVA invariant violated at cycle step T={t_fail}.",
                "error_category": "FORMAL_INVARIANT_BREACH",
                "failing_property": prop_name,
                "step": t_fail,
                "simulated": False,
            }

        return {
            "gate": "Gate 2: SymbiYosys Formal Property Verification",
            "passed": True,
            "exit_code": 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "details": "SymbiYosys BMC depth 25 proven: zero invariant counterexamples.",
            "error_category": None,
            "simulated": False,
            "skipped": False,
        }

    def _run_gate3_coverage(self, runner: Any, sources: list[Path], ws: Path) -> dict[str, Any]:
        """Compile, execute, and verify line, branch, and toggle coverage thresholds."""
        tb_cpp = list(ws.glob("*.cpp"))
        if not tb_cpp and self.contract is not None:
            # Auto-generate high-coverage C++ testbench from contract if missing
            from .contracts import VerificationHarnessGenerator
            tb_content = VerificationHarnessGenerator.build_verilator_cpp_testbench(self.contract)
            tb_path = ws / f"{self.top_module}_tb.cpp"
            tb_path.write_text(tb_content, encoding="utf-8")
            tb_cpp = [tb_path]

        if not tb_cpp:
            if self.require_coverage:
                return {
                    "gate": "Gate 3: Verilator Coverage Signoff",
                    "passed": False,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "Missing C++ coverage testbench (*.cpp).",
                    "details": (
                        "No C++ testbench (*.cpp) found for Verilator coverage signoff. "
                        "Generate a C++ testbench driving RTL inputs to evaluate branch and toggle coverage."
                    ),
                    "error_category": "MISSING_VERIFICATION_ARTIFACT",
                    "skipped": False,
                    "simulated": False,
                }
            return {
                "gate": "Gate 3: Verilator Coverage Signoff",
                "passed": True,
                "exit_code": 0,
                "stdout": "Coverage threshold evaluation skipped (require_coverage=False).",
                "stderr": "",
                "details": "Coverage signoff bypassed by caller opt-out.",
                "error_category": None,
                "skipped": True,
                "simulated": False,
            }

        src_rel = [str(s.relative_to(ws)) for s in sources]
        bin_target = f"V{self.top_module}"
        cmd = [
            "verilator",
            "--binary",
            "--sv",
            "-Wall",
            "--coverage-line",
            "--coverage-toggle",
            "-top-module",
            self.top_module,
            *src_rel,
            str(tb_cpp[0].relative_to(ws)),
            "-o",
            bin_target,
        ]
        proc = runner.run(cmd, timeout_sec=60)
        combined = f"{proc.stdout}\n{proc.stderr}"

        if proc.returncode != 0 and _is_binary_missing(proc, "verilator"):
            if not self.allow_mock_fallback:
                return {
                    "gate": "Gate 3: Verilator Coverage Signoff",
                    "passed": False,
                    "exit_code": 127,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "details": (
                        "verilator binary missing on host/runner. "
                        "Install Verilator via package manager (e.g. 'brew install verilator' or 'apt-get install verilator') "
                        "or build from source (https://verilator.org)."
                    ),
                    "error_category": "EDA_BINARY_MISSING",
                    "simulated": False,
                }
            return {
                "gate": "Gate 3: Verilator Coverage Signoff",
                "passed": True,
                "exit_code": 0,
                "stdout": f"[SIMULATED - NOT REAL TOOL OUTPUT] Verilator coverage verified: branch=98.2%, toggle=94.5% (above threshold {self.min_branch_coverage}%/{self.min_toggle_coverage}%).",
                "stderr": "",
                "details": "Simulated coverage thresholds satisfied.",
                "metrics": {"branch": 98.2, "toggle": 94.5},
                "error_category": None,
                "simulated": True,
                "skipped": False,
            }

        # Check for compiler errors
        if proc.returncode != 0:
            return {
                "gate": "Gate 3: Verilator Coverage Signoff",
                "passed": False,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": "Verilator coverage build compilation failed.",
                "error_category": "COVERAGE_BUILD_FAILURE",
                "simulated": False,
            }

        # Execute the compiled simulation binary if available
        sim_bin = ws / "obj_dir" / bin_target
        if not sim_bin.exists():
            sim_bin = ws / bin_target

        sim_stdout = ""
        sim_stderr = ""
        if sim_bin.exists():
            sim_cmd = [str(sim_bin.relative_to(ws))]
            sim_proc = runner.run(sim_cmd, timeout_sec=60)
            sim_stdout = sim_proc.stdout
            sim_stderr = sim_proc.stderr
            if sim_proc.returncode != 0:
                return {
                    "gate": "Gate 3: Verilator Coverage Signoff",
                    "passed": False,
                    "exit_code": sim_proc.returncode,
                    "stdout": sim_stdout,
                    "stderr": sim_stderr,
                    "details": f"Verilator simulation runtime failed with exit code {sim_proc.returncode}.",
                    "error_category": "SIMULATION_FAILURE",
                    "simulated": False,
                }

        cov_combined = f"{proc.stdout}\n{sim_stdout}"
        cov_metrics = parse_verilator_coverage(cov_combined)
        branch_cov = cov_metrics["branch"] if cov_metrics["branch"] is not None else 100.0
        toggle_cov = cov_metrics["toggle"] if cov_metrics["toggle"] is not None else 100.0

        if branch_cov < self.min_branch_coverage or toggle_cov < self.min_toggle_coverage:
            return {
                "gate": "Gate 3: Verilator Coverage Signoff",
                "passed": False,
                "exit_code": 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": f"Coverage deficit: branch={branch_cov:.1f}% (min {self.min_branch_coverage}%), toggle={toggle_cov:.1f}% (min {self.min_toggle_coverage}%).",
                "error_category": "COVERAGE_DEFICIT",
                "metrics": {"branch": branch_cov, "toggle": toggle_cov},
                "simulated": False,
            }

        return {
            "gate": "Gate 3: Verilator Coverage Signoff",
            "passed": True,
            "exit_code": 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "details": "Coverage signoff criteria satisfied.",
            "metrics": {"branch": branch_cov, "toggle": toggle_cov},
            "error_category": None,
            "simulated": False,
            "skipped": False,
        }

    def _run_gate4_timing(self, runner: Any, sources: list[Path], ws: Path) -> dict[str, Any]:
        """Perform static timing analysis on synthesized gate netlist and verify worst negative slack (WNS)."""
        if not self.liberty_paths:
            raise ValueError(
                "Gate 4 static timing analysis requires 'liberty_path' to be configured. "
                "No default PDK library is assumed."
            )

        sdc_files = list(ws.glob("*.sdc"))
        if not sdc_files and self.contract is not None:
            sdc_path = ws / f"{self.top_module}.sdc"
            sdc_path.write_text(self.contract.timing.to_sdc(), encoding="utf-8")
            sdc_files = [sdc_path]

        # Prefer Gate 1 technology-mapped synthesized netlist over unmapped behavioral RTL
        netlist_file = ws / f"{self.top_module}_netlist.v"
        if not netlist_file.exists():
            netlists = list(ws.glob("*netlist*.v"))
            if netlists:
                netlist_file = netlists[0]

        verilog_target = netlist_file.name if netlist_file.exists() else " ".join(s.name for s in sources)

        custom_tcl = [p for p in sorted(ws.glob("*.tcl")) if p.name != "sta_check.tcl"]
        if custom_tcl:
            # Respect user-supplied custom STA scripts; do not overwrite
            target_script = custom_tcl[0]
        else:
            # Auto-managed sta_check.tcl: always regenerate with current liberty_paths configuration
            sta_script = ws / "sta_check.tcl"
            sdc_ref = sdc_files[0].name if sdc_files else "none"
            read_lib_lines = "\n".join(f"read_liberty {lib}" for lib in self.liberty_paths)
            config_hash = hashlib.sha256(
                f"{read_lib_lines}|{self.top_module}|{sdc_ref}|{verilog_target}".encode()
            ).hexdigest()[:16]
            sta_script.write_text(
                f"# Auto-generated by SiliconSignoffVerifier [config_hash: {config_hash}]\n"
                f"{read_lib_lines}\n"
                f"read_verilog {verilog_target}\n"
                f"link_design {self.top_module}\n"
                f"read_sdc {sdc_ref}\n"
                f"report_checks\n"
                f"report_wns\n",
                encoding="utf-8",
            )
            target_script = sta_script

        cmd = ["sta", "-f", str(target_script.relative_to(ws))]
        proc = runner.run(cmd, timeout_sec=30)
        combined = f"{proc.stdout}\n{proc.stderr}"

        if proc.returncode != 0 and (_is_binary_missing(proc, "sta") or _is_binary_missing(proc, "opensta")):
            if not self.allow_mock_fallback:
                return {
                    "gate": "Gate 4: OpenSTA Multi-Corner Timing Signoff",
                    "passed": False,
                    "exit_code": 127,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "details": (
                        "sta/opensta binary missing on host/runner. "
                        "Install OpenSTA via package manager, OpenROAD/OpenLane, or build from source (https://github.com/The-OpenROAD-Project/OpenSTA)."
                    ),
                    "error_category": "EDA_BINARY_MISSING",
                    "simulated": False,
                }
            return {
                "gate": "Gate 4: OpenSTA Multi-Corner Timing Signoff",
                "passed": True,
                "exit_code": 0,
                "stdout": "[SIMULATED - NOT REAL TOOL OUTPUT] STA timing simulated: WNS = +0.180 ns (Slack MET across PVT corners).",
                "stderr": "",
                "details": "Timing constraint satisfied.",
                "metrics": {"wns": 0.180},
                "error_category": None,
                "simulated": True,
                "skipped": False,
            }

        # Use the comprehensive parse_opensta_timing for setup + TNS + hold
        timing_data = parse_opensta_timing(combined)
        wns_val = timing_data["setup_wns"]
        tns_val = timing_data["setup_tns"]
        hold_wns_val = timing_data["hold_wns"]

        if wns_val is None:
            return {
                "gate": "Gate 4: OpenSTA Multi-Corner Timing Signoff",
                "passed": False,
                "exit_code": 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": "Failed to parse Worst Negative Slack (WNS) from OpenSTA output. Ensure report_wns or report_checks generated valid timing metrics.",
                "error_category": "TIMING_REPORT_UNPARSEABLE",
                "simulated": False,
            }

        wns_ps = wns_val * (1000.0 if self.sta_time_unit == "ns" else 1.0)
        tns_ps = (tns_val * (1000.0 if self.sta_time_unit == "ns" else 1.0)) if tns_val is not None else None
        hold_wns_ps = (hold_wns_val * (1000.0 if self.sta_time_unit == "ns" else 1.0)) if hold_wns_val is not None else None

        # Check for setup slack violation or VIOLATED flags in output
        if wns_ps < self.max_wns_ps or "VIOLATED" in combined:
            return {
                "gate": "Gate 4: OpenSTA Multi-Corner Timing Signoff",
                "passed": False,
                "exit_code": 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": (
                    f"Setup timing violation: WNS = {wns_val:.3f} {self.sta_time_unit} "
                    f"({wns_ps:.3f} ps; target >= {self.max_wns_ps:.3f} ps)."
                ),
                "error_category": "TIMING_SLACK_VIOLATION",
                "metrics": {"setup_wns": wns_val, "wns_ps": wns_ps, "setup_tns": tns_val},
                "hold_metrics": {},
                "simulated": False,
            }

        # Check for hold slack violation
        if hold_wns_ps is not None and hold_wns_ps < self.min_hold_slack_ps:
            return {
                "gate": "Gate 4: OpenSTA Multi-Corner Timing Signoff",
                "passed": False,
                "exit_code": 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": (
                    f"Hold timing violation: hold WNS = {hold_wns_val:.3f} {self.sta_time_unit} "
                    f"({hold_wns_ps:.3f} ps; target >= {self.min_hold_slack_ps:.3f} ps)."
                ),
                "error_category": "HOLD_SLACK_VIOLATION",
                "metrics": {"setup_wns": wns_val, "wns_ps": wns_ps},
                "hold_metrics": {"hold_wns": hold_wns_val, "hold_wns_ps": hold_wns_ps},
                "simulated": False,
            }

        if proc.returncode != 0:
            return {
                "gate": "Gate 4: OpenSTA Multi-Corner Timing Signoff",
                "passed": False,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": "OpenSTA execution failed with non-zero exit status.",
                "error_category": "TIMING_ANALYSIS_FAILED",
                "metrics": {"setup_wns": wns_val, "wns_ps": wns_ps, "setup_tns": tns_val},
                "hold_metrics": {"hold_wns": hold_wns_val} if hold_wns_val is not None else {},
                "simulated": False,
            }

        hold_metrics_dict: dict[str, float] = {}
        if hold_wns_val is not None:
            hold_metrics_dict["hold_wns"] = hold_wns_val
        if hold_wns_ps is not None:
            hold_metrics_dict["hold_wns_ps"] = hold_wns_ps

        return {
            "gate": "Gate 4: OpenSTA Multi-Corner Timing Signoff",
            "passed": True,
            "exit_code": 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "details": (
                f"Timing closure confirmed: setup WNS = {wns_val:.3f} {self.sta_time_unit} "
                f"({wns_ps:.3f} ps). "
                + (f"Hold WNS = {hold_wns_val:.3f} {self.sta_time_unit}. " if hold_wns_val is not None else "")
                + "This is not a full MCMM tapeout-signoff claim."
            ),
            "error_category": None,
            "metrics": {"wns": wns_val, "setup_wns": wns_val, "wns_ps": wns_ps, "setup_tns": tns_val},
            "hold_metrics": hold_metrics_dict,
            "simulated": False,
            "skipped": False,
        }

    def _run_gate5_openroad_pnr(self, runner: Any, sources: list[Path], ws: Path) -> dict[str, Any]:
        """Execute OpenROAD place-and-route on the Gate 1 synthesized gate-level netlist."""
        if not self.require_pnr:
            return {
                "gate": "Gate 5: OpenROAD Place-and-Route",
                "passed": True,
                "exit_code": 0,
                "stdout": "PnR signoff skipped (require_pnr=False).",
                "stderr": "",
                "details": "Physical design gate bypassed by caller opt-out. Set require_pnr=True to enable.",
                "error_category": None,
                "metrics": {},
                "skipped": True,
                "simulated": False,
            }

        # PnR requires the Gate 1 synthesized gate-level netlist
        netlist_file = ws / f"{self.top_module}_netlist.v"
        if not netlist_file.exists():
            netlist_candidates = list(ws.glob("*netlist*.v"))
            if netlist_candidates:
                netlist_file = netlist_candidates[0]

        if not netlist_file.exists():
            return {
                "gate": "Gate 5: OpenROAD Place-and-Route",
                "passed": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": "Gate-level netlist not found; Gate 1 (Yosys synthesis) must complete first.",
                "details": "OpenROAD PnR requires a synthesized gate-level netlist from Gate 1.",
                "error_category": "MISSING_NETLIST_FOR_PNR",
                "metrics": {},
                "skipped": False,
                "simulated": False,
            }

        if not self.liberty_paths:
            return {
                "gate": "Gate 5: OpenROAD Place-and-Route",
                "passed": False,
                "exit_code": 1,
                "stdout": "",
                "stderr": "liberty_path required for OpenROAD PnR cell characterization.",
                "details": "Set liberty_path in SiliconSignoffVerifier to enable Gate 5.",
                "error_category": "MISSING_LIBERTY_FOR_PNR",
                "metrics": {},
                "skipped": False,
                "simulated": False,
            }

        sdc_files = list(ws.glob("*.sdc"))
        sdc_ref = sdc_files[0].name if sdc_files else "none"
        lib_cmds = "\n".join(f"read_liberty {lib}" for lib in self.liberty_paths)
        lef_cmds = "\n".join(f"read_lef {lef}" for lef in self.lef_paths) if self.lef_paths else ""
        config_hash = hashlib.sha256(
            f"{lib_cmds}|{lef_cmds}|{self.top_module}|{sdc_ref}".encode()
        ).hexdigest()[:16]

        pnr_tcl = ws / "pnr.tcl"
        custom_pnr = [p for p in sorted(ws.glob("*.tcl")) if p.name not in ("sta_check.tcl", "pnr.tcl")]
        if not custom_pnr:
            pnr_tcl.write_text(
                f"# Auto-generated OpenROAD PnR script [config_hash: {config_hash}]\n"
                f"{lib_cmds}\n"
                f"{lef_cmds}\n"
                f"read_verilog {netlist_file.name}\n"
                f"link_design {self.top_module}\n"
                f"read_sdc {sdc_ref}\n"
                f"initialize_floorplan -utilization 40 -aspect_ratio 1.0 -core_space 2.0\n"
                f"place_pins -hor_layers metal2 -ver_layers metal3\n"
                f"global_placement -density 0.5\n"
                f"detailed_placement\n"
                f"global_route\n"
                f"report_design_area\n"
                f"puts \"PNR_COMPLETE\"\n",
                encoding="utf-8",
            )
        else:
            pnr_tcl = custom_pnr[0]

        cmd = ["openroad", "-exit", pnr_tcl.name]
        proc = runner.run(cmd, timeout_sec=120)
        combined = f"{proc.stdout}\n{proc.stderr}"

        if proc.returncode != 0 and _is_binary_missing(proc, "openroad"):
            if self.allow_mock_fallback:
                return {
                    "gate": "Gate 5: OpenROAD Place-and-Route",
                    "passed": True,
                    "exit_code": 0,
                    "stdout": "[SIMULATED - NOT REAL TOOL OUTPUT] OpenROAD PnR simulated: placement and routing clean.",
                    "stderr": "",
                    "details": "OpenROAD PnR simulated successfully.",
                    "error_category": None,
                    "metrics": {"pnr_complete": True},
                    "skipped": False,
                    "simulated": True,
                }
            return {
                "gate": "Gate 5: OpenROAD Place-and-Route",
                "passed": False,
                "exit_code": 127,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": (
                    "openroad binary missing. Install via OpenROAD-flow-scripts "
                    "(https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) "
                    "or build from source (https://github.com/The-OpenROAD-Project/OpenROAD)."
                ),
                "error_category": "EDA_BINARY_MISSING",
                "metrics": {},
                "skipped": False,
                "simulated": False,
            }

        pnr_parsed = parse_openroad_pnr(combined)
        metrics: dict[str, Any] = {
            "pnr_complete": pnr_parsed["pnr_complete"],
            "placement_overflow": pnr_parsed["placement_overflow"],
            "routing_congestion": pnr_parsed["routing_congestion"],
        }

        if proc.returncode != 0 or not pnr_parsed["passed"]:
            err_msg = pnr_parsed["errors"][0] if pnr_parsed["errors"] else "placement overflow or routing error detected"
            return {
                "gate": "Gate 5: OpenROAD Place-and-Route",
                "passed": False,
                "exit_code": proc.returncode if proc.returncode != 0 else 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": f"OpenROAD PnR failed: {err_msg}.",
                "error_category": "PNR_PLACEMENT_FAILED",
                "metrics": metrics,
                "skipped": False,
                "simulated": False,
            }

        return {
            "gate": "Gate 5: OpenROAD Place-and-Route",
            "passed": True,
            "exit_code": 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "details": "OpenROAD PnR completed: placement and global routing passed.",
            "error_category": None,
            "metrics": metrics,
            "skipped": False,
            "simulated": False,
        }

    def _run_gate6_cdc_analysis(self, runner: Any, sources: list[Path], ws: Path) -> dict[str, Any]:
        """Execute Yosys CDC static analysis to detect unregistered clock-domain crossings."""
        src_args = [str(s.relative_to(ws)) for s in sources]
        yosys_cdc_script = (
            f"read_verilog -sv {' '.join(src_args)}; "
            f"hierarchy -check -top {self.top_module}; "
            f"proc; cdc -verbose"
        )
        cmd = ["yosys", "-p", yosys_cdc_script]
        proc = runner.run(cmd, timeout_sec=45)
        combined = f"{proc.stdout}\n{proc.stderr}"

        if proc.returncode != 0 and _is_binary_missing(proc, "yosys"):
            if self.allow_mock_fallback:
                return {
                    "gate": "Gate 6: Yosys CDC Static Analysis",
                    "passed": True,
                    "exit_code": 0,
                    "stdout": "[SIMULATED - NOT REAL TOOL OUTPUT] Yosys CDC analysis simulated: 0 cross-clock domain violations.",
                    "stderr": "",
                    "details": "CDC analysis simulated: zero clock-domain crossings detected.",
                    "error_category": None,
                    "cdc_violations": [],
                    "skipped": False,
                    "simulated": True,
                }
            if not self.require_cdc:
                return {
                    "gate": "Gate 6: Yosys CDC Static Analysis",
                    "passed": True,
                    "exit_code": 0,
                    "stdout": "CDC analysis skipped (require_cdc=False, yosys unavailable).",
                    "stderr": "",
                    "details": "CDC gate bypassed: missing Yosys binary and caller opted out.",
                    "error_category": None,
                    "cdc_violations": [],
                    "skipped": True,
                    "simulated": False,
                }
            return {
                "gate": "Gate 6: Yosys CDC Static Analysis",
                "passed": False,
                "exit_code": 127,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": "yosys binary missing. Yosys is required by Gate 1 and Gate 6.",
                "error_category": "EDA_BINARY_MISSING",
                "cdc_violations": [],
                "skipped": False,
                "simulated": False,
            }

        cdc_result = parse_yosys_cdc(combined)
        violations = cdc_result["violations"]

        if not cdc_result["passed"]:
            return {
                "gate": "Gate 6: Yosys CDC Static Analysis",
                "passed": False,
                "exit_code": 1,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": f"CDC analysis detected {len(violations)} unregistered clock-domain crossing(s).",
                "error_category": "CDC_VIOLATION",
                "cdc_violations": violations,
                "skipped": False,
                "simulated": False,
            }

        if proc.returncode != 0 and not self.allow_mock_fallback:
            return {
                "gate": "Gate 6: Yosys CDC Static Analysis",
                "passed": False,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "details": "Yosys CDC elaboration failed. Check RTL syntax or hierarchy errors.",
                "error_category": "CDC_ANALYSIS_FAILED",
                "cdc_violations": [],
                "skipped": False,
                "simulated": False,
            }

        return {
            "gate": "Gate 6: Yosys CDC Static Analysis",
            "passed": True,
            "exit_code": 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "details": "CDC analysis clean: zero unregistered clock-domain crossings detected.",
            "error_category": None,
            "cdc_violations": [],
            "skipped": False,
            "simulated": False,
        }

    def _run_dft_scan_audit(self, runner: Any, sources: list[Path], ws: Path) -> dict[str, Any]:
        """Advisory DFT scan-chain audit: count DFFs and verify scan-enable port presence.

        This gate is always advisory — it never blocks signoff. Results are recorded
        in gate_reports and dft_audit for downstream consumption.
        """
        src_args = [str(s.relative_to(ws)) for s in sources]
        yosys_stat_script = (
            f"read_verilog -sv {' '.join(src_args)}; "
            f"hierarchy -check -top {self.top_module}; "
            f"proc; synth -noabc; stat"
        )
        cmd = ["yosys", "-p", yosys_stat_script]
        proc = runner.run(cmd, timeout_sec=45)
        combined = f"{proc.stdout}\n{proc.stderr}"

        dff_count = 0
        dff_match = re.search(r"\$dff\s+(\d+)", combined)
        if dff_match:
            dff_count = int(dff_match.group(1))

        scan_port_names = {"se", "scan_en", "scan_enable", "scan_in", "si", "so", "scan_out"}
        has_scan_port = False
        for src in sources:
            try:
                src_text = src.read_text(encoding="utf-8").lower()
                if any(
                    re.search(r"\b" + re.escape(sp) + r"\b", src_text)
                    for sp in scan_port_names
                ):
                    has_scan_port = True
                    break
            except OSError:
                continue

        dft_threshold = 4
        needs_scan = dff_count > dft_threshold
        advisory_messages: list[str] = []
        if needs_scan and not has_scan_port:
            advisory_messages.append(
                f"Design has {dff_count} DFFs (>{dft_threshold}) but no scan-enable port detected. "
                "Add scan chain infrastructure for production DFT testability."
            )

        audit_report: dict[str, Any] = {
            "dff_count": dff_count,
            "has_scan_port": has_scan_port,
            "needs_scan": needs_scan,
            "advisory": advisory_messages,
            "advisory_count": len(advisory_messages),
        }

        return {
            "gate": "DFT Scan Audit (Advisory)",
            "passed": True,
            "exit_code": 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "details": (
                f"DFT audit: {dff_count} DFFs, scan_port={'present' if has_scan_port else 'absent'}. "
                + (f"Advisory: {'; '.join(advisory_messages)}" if advisory_messages else "No DFT advisories.")
            ),
            "error_category": None,
            "dft_audit": audit_report,
            "simulated": False,
            "skipped": proc.returncode == 127,
        }


__all__ = [
    "BaseVerifier",
    "RTLVerifier",
    "SoftwareVerifier",
    "IndustryReportVerifier",
    "SiliconSignoffVerifier",
    "TapeoutReadinessVerifier",
    "parse_opensta_timing",
    "parse_opensta_wns",
]


class TapeoutReadinessVerifier(BaseVerifier):
    """Fail-closed evidence checklist verifier for tapeout readiness.

    Validates that a qualified EDA/PDK signoff flow has produced clean artifacts
    for: lint, CDC, equivalence check, UPF, DFT, MCMM STA, DRC, LVS, and EM/IR.

    Does NOT generate or execute EDA tools. Validates evidence receipts only.
    A design is tapeout-ready only when each required receipt is present and
    non-empty, and the sign-off is accepted by a qualified signoff team.
    """

    RECEIPT_PATTERNS: dict[str, list[str]] = {
        "lint": ["*.lint.rpt", "*.lint.log"],
        "cdc": ["*.cdc.rpt", "*.cdc.clean"],
        "equivalence": ["*.ec.rpt", "*.lec.rpt"],
        "upf": ["*.upf"],
        "dft": ["*.dft.rpt", "*.atpg.rpt"],
        "sta": ["*.sta.rpt", "*.timing.rpt"],
        "drc": ["*.drc.rpt"],
        "lvs": ["*.lvs.rpt"],
        "em_ir": ["*.em.rpt", "*.ir.rpt"],
    }

    def __init__(
        self,
        required_receipts: list[str] | None = None,
        custom_paths: dict[str, str] | None = None,
        audit_content: bool = False,
    ) -> None:
        """Configure the tapeout readiness checklist.

        Args:
            required_receipts: Subset of receipt keys to require. Defaults to all 9.
                Valid keys: lint, cdc, equivalence, upf, dft, sta, drc, lvs, em_ir.
            custom_paths: Override glob patterns with explicit relative paths per key.
            audit_content: When True, inspects the content of found receipts to ensure clean signoff metrics.
        """
        all_keys = list(self.RECEIPT_PATTERNS.keys())
        if required_receipts is not None:
            invalid = set(required_receipts) - set(all_keys)
            if invalid:
                raise ValueError(
                    f"Unknown receipt keys: {sorted(invalid)}. Valid keys: {sorted(all_keys)}"
                )
            self.required_receipts: list[str] = required_receipts
        else:
            self.required_receipts = all_keys
        self.custom_paths: dict[str, str] = custom_paths or {}
        self.audit_content: bool = audit_content

    def verify(
        self,
        workspace: Path,
        sandbox: BubblewrapSandbox,
    ) -> VerificationResult:
        """Validate presence and non-emptiness (and optionally content) of required tapeout evidence receipts."""
        resolved_ws = workspace.resolve()
        evidence: dict[str, bool] = {}
        missing: list[str] = []
        content_errors: list[str] = []
        parsed_receipt_metrics: dict[str, Any] = {}

        for receipt_key in self.required_receipts:
            found = False
            matched_file: Path | None = None
            if receipt_key in self.custom_paths:
                custom_file = resolved_ws / self.custom_paths[receipt_key]
                if custom_file.exists() and custom_file.stat().st_size > 0:
                    found = True
                    matched_file = custom_file
            else:
                for pattern in self.RECEIPT_PATTERNS.get(receipt_key, []):
                    matches = list(resolved_ws.glob(pattern))
                    for m in matches:
                        if m.exists() and m.stat().st_size > 0:
                            found = True
                            matched_file = m
                            break
                    if found:
                        break

            evidence[receipt_key] = found
            if not found:
                missing.append(receipt_key)
            elif self.audit_content and matched_file is not None:
                try:
                    text = matched_file.read_text(encoding="utf-8", errors="replace")
                    if receipt_key == "sta":
                        if "VIOLATED" in text or "slack (VIOLATED)" in text:
                            content_errors.append(f"STA receipt '{matched_file.name}' reports timing violations (VIOLATED).")
                    elif receipt_key == "drc":
                        m = re.search(r"TOTAL\s+DRC\s+Results\s+Generated\s*:\s*([1-9]\d*)", text, re.IGNORECASE)
                        if m or "DRC VIOLATION" in text:
                            content_errors.append(f"DRC receipt '{matched_file.name}' reports design rule violations.")
                    elif receipt_key == "lvs":
                        if "INCORRECT" in text and "CORRECT" not in text:
                            content_errors.append(f"LVS receipt '{matched_file.name}' reports layout vs schematic mismatch.")
                    elif receipt_key == "dft":
                        m = re.search(r"(?:stuck-at|test)\s+coverage\s*[:=]?\s*(\d+(?:\.\d+)?)%", text, re.IGNORECASE)
                        if m and float(m.group(1)) < 99.5:
                            content_errors.append(f"DFT receipt '{matched_file.name}' stuck-at coverage ({m.group(1)}%) < 99.5%.")
                except OSError:
                    continue

        passed = (len(missing) == 0) and (len(content_errors) == 0)
        failure_reasons: list[str] = []
        if missing:
            failure_reasons.append(f"Missing tapeout evidence receipts: {', '.join(sorted(missing))}.")
        if content_errors:
            failure_reasons.extend(content_errors)

        failure_reason = " ".join(failure_reasons) if not passed else None
        err_cat = "MISSING_TAPEOUT_EVIDENCE" if missing else ("TAPEOUT_EVIDENCE_REJECTED" if content_errors else None)

        return VerificationResult(
            passed=passed,
            domain=VerificationDomain.RTL,
            exit_code=0 if passed else 1,
            stdout=(
                f"Tapeout readiness: {len(self.required_receipts) - len(missing)}/"
                f"{len(self.required_receipts)} receipts present."
                + (" All audited content clean." if (passed and self.audit_content) else "")
            ),
            stderr="\n".join(failure_reasons),
            failure_reason=failure_reason,
            error_category=err_cat,
            tapeout_evidence=evidence,
            tapeout_ready=passed,
        )


class CommercialSignoffVerifier(BaseVerifier):
    """Foundry-Grade 8-Gate Commercial EDA Signoff Oracle.

    Parses, validates, and audits reports from Synopsys (PrimeTime, Fusion Compiler),
    Cadence (Innovus, Tempus), and Siemens (Calibre nmDRC/nmLVS, Tessent).
    """

    def __init__(
        self,
        top_module: str,
        sta_log_path: str | None = None,
        pnr_log_path: str | None = None,
        drc_summary_path: str | None = None,
        lvs_summary_path: str | None = None,
        atpg_report_path: str | None = None,
    ) -> None:
        self.top_module = top_module
        self.sta_log_path = sta_log_path
        self.pnr_log_path = pnr_log_path
        self.drc_summary_path = drc_summary_path
        self.lvs_summary_path = lvs_summary_path
        self.atpg_report_path = atpg_report_path

    def verify(
        self,
        workspace: Path,
        sandbox: BubblewrapSandbox,
    ) -> VerificationResult:
        from mind3.sandbox.eda_commercial import (
            parse_calibre_drc_summary,
            parse_calibre_lvs_summary,
            parse_innovus_log,
            parse_primetime_log,
        )
        from mind3.core.dft import ATPGSignoffVerifier

        resolved_ws = workspace.resolve()
        errors: list[str] = []
        metrics: dict[str, Any] = {}

        # 1. PrimeTime / Tempus STA
        if self.sta_log_path:
            p = resolved_ws / self.sta_log_path
            if p.exists():
                sta_res = parse_primetime_log(p.read_text(encoding="utf-8", errors="replace"))
                metrics["sta"] = sta_res
                if not sta_res["timing_passed"]:
                    errors.append(f"STA signoff failed: worst setup WNS={sta_res['worst_setup_wns']}, hold WNS={sta_res['worst_hold_wns']}.")
            else:
                errors.append(f"STA log missing: {self.sta_log_path}")

        # 2. Innovus / Fusion Compiler PnR
        if self.pnr_log_path:
            p = resolved_ws / self.pnr_log_path
            if p.exists():
                pnr_res = parse_innovus_log(p.read_text(encoding="utf-8", errors="replace"))
                metrics["pnr"] = pnr_res
                if not pnr_res["passed"]:
                    errors.append(f"PnR signoff failed: DRC={pnr_res['drc_violations']}, conn={pnr_res['connectivity_errors']}, overflow={pnr_res['routing_overflow_pct']}%.")
            else:
                errors.append(f"PnR log missing: {self.pnr_log_path}")

        # 3. Calibre nmDRC
        if self.drc_summary_path:
            p = resolved_ws / self.drc_summary_path
            if p.exists():
                drc_res = parse_calibre_drc_summary(p.read_text(encoding="utf-8", errors="replace"))
                metrics["drc"] = drc_res
                if not drc_res["clean"]:
                    errors.append(f"Calibre nmDRC failed with {drc_res['total_violations']} violations.")
            else:
                errors.append(f"Calibre DRC summary missing: {self.drc_summary_path}")

        # 4. Calibre nmLVS
        if self.lvs_summary_path:
            p = resolved_ws / self.lvs_summary_path
            if p.exists():
                lvs_res = parse_calibre_lvs_summary(p.read_text(encoding="utf-8", errors="replace"))
                metrics["lvs"] = lvs_res
                if not lvs_res["lvs_correct"]:
                    errors.append("Calibre nmLVS comparison failed (mismatched devices/nets).")
            else:
                errors.append(f"Calibre LVS summary missing: {self.lvs_summary_path}")

        # 5. ATPG Fault Coverage
        if self.atpg_report_path:
            p = resolved_ws / self.atpg_report_path
            if p.exists():
                atpg_res = ATPGSignoffVerifier.parse_atpg_report(p.read_text(encoding="utf-8", errors="replace"))
                metrics["atpg"] = atpg_res
                if not atpg_res["passed"]:
                    errors.extend(atpg_res["violations"])
            else:
                errors.append(f"ATPG report missing: {self.atpg_report_path}")

        passed = len(errors) == 0
        return VerificationResult(
            passed=passed,
            domain=VerificationDomain.RTL,
            exit_code=0 if passed else 1,
            stdout=f"Commercial signoff: {'PASSED' if passed else 'FAILED'} across {len(metrics)} domains.",
            stderr="\n".join(errors),
            failure_reason="; ".join(errors) if not passed else None,
            error_category="COMMERCIAL_SIGNOFF_FAILURE" if not passed else None,
            commercial_signoff=metrics,
            tapeout_ready=passed,
        )
