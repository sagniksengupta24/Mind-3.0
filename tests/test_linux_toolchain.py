"""Stage 5 toolchain evidence tests (R3/R10/R13).

Every test asserts on actually executed binaries. Missing tools produce
explicit unknown/unexecuted records — never passes. Platform labels keep
macOS and Linux evidence separate.
"""

import json
import platform
import shutil

import pytest

from mind3.sandbox.linux_toolchain import (
    TOOL_SPECS,
    collect_environment_report,
    probe_tool,
    probe_yosys_cdc,
)


def test_toolchain_contract_covers_required_tools() -> None:
    assert set(TOOL_SPECS) == {
        "python", "yosys", "sby", "z3", "verilator", "sta", "openroad", "bwrap",
    }


def test_probe_missing_tool_is_unknown_not_pass() -> None:
    rec = probe_tool("definitely_not_a_real_tool_xyz")
    assert rec["executed"] is False
    assert rec["version"] == "unknown"
    assert rec["platform"] == platform.system().lower()


def test_probe_python_executes_and_reports_version() -> None:
    rec = probe_tool("python")
    assert rec["executed"] is True
    assert rec["returncode"] == 0
    assert rec["version"] != "unknown"
    assert platform.python_version() in rec["version"]


def test_probe_versions_come_from_executables() -> None:
    """Each present tool's version must appear verbatim in its own captured output."""
    for name in TOOL_SPECS:
        rec = probe_tool(name)
        assert rec["platform"] == platform.system().lower()
        if rec["executed"] and rec["returncode"] == 0 and rec["version"] != "unknown":
            assert rec["version"] in rec["output_head"]
        if not rec["executed"]:
            assert rec["version"] == "unknown"


def test_probe_yosys_cdc_reports_real_availability() -> None:
    """CDC availability reflects executed `help cdc` output, not documentation."""
    rec = probe_yosys_cdc()
    assert rec["tool"] == "yosys-cdc"
    assert rec["platform"] == platform.system().lower()
    if shutil.which("yosys") is None:
        assert rec["executed"] is False
        assert rec["cdc_available"] is False
        return
    assert rec["executed"] is True
    # This assertion is platform-conditional and honest either way: it checks
    # consistency between the flag and the captured output, not a fixed value.
    if rec["cdc_available"]:
        assert "no such command" not in rec["output_head"].lower()
    else:
        assert "no such command" in rec["output_head"].lower()


def test_probe_yosys_cdc_missing_binary_is_not_available() -> None:
    rec = probe_yosys_cdc(yosys_argv="definitely_not_yosys_xyz")
    assert rec["executed"] is False
    assert rec["cdc_available"] is False


def test_environment_report_field_set_and_unknowns() -> None:
    report = collect_environment_report()
    for key in (
        "platform", "os_release", "python_version",
        "yosys_version", "sby_version", "z3_version", "verilator_version",
        "opensta_version", "openroad_version", "bubblewrap_version",
        "cdc_command", "cdc_execution_result", "opensta_smoke_result",
        "openroad_smoke_result", "bubblewrap_egress_result", "seatbelt_egress_result",
    ):
        assert key in report, f"R18 field missing: {key}"
    assert report["platform"] == platform.system().lower()
    # Behavioral outcomes default to unknown — never fabricated.
    for key in (
        "cdc_execution_result", "opensta_smoke_result", "openroad_smoke_result",
        "bubblewrap_egress_result", "seatbelt_egress_result",
    ):
        assert report[key] == "unknown"
    # Tool versions round-trip through JSON.
    parsed = json.loads(json.dumps(report))
    assert parsed["tools"]["python"]["executed"] is True


def test_environment_report_accepts_executed_evidence_only() -> None:
    report = collect_environment_report(extra={
        "seatbelt_egress_result": {"status": "EGRESS_BLOCK_VERIFIED", "platform": "darwin"},
        "unrelated_key_xyz": "ignored",
    })
    assert report["seatbelt_egress_result"]["status"] == "EGRESS_BLOCK_VERIFIED"
    assert "unrelated_key_xyz" not in report


# ── Live tool smoke tests (eda): invoke executables, never just `which` ──
# Each test declares only the tools it actually executes, so Linux hosts run
# whatever their prerequisites allow instead of all-or-nothing skipping.

_sta_mark = pytest.mark.eda


@_sta_mark
@pytest.mark.eda_tools("sta/opensta")
def test_opensta_smoke_version_and_workload(tmp_path) -> None:
    """OpenSTA must execute: version query plus a minimal legal STA workload.

    Success proves the tool runs in this environment. It is NOT timing
    signoff: the fixture is a combinational passthrough with no clocked
    paths, so no slack numbers are asserted. Skips with reason when neither
    `sta` nor `opensta` exists.

    The Liberty is environment-aware: a real SKY130 library supplied via
    `MIND3_NEGATIVE_CONTROL_LIBERTY`, `MIND3_LIBERTY_PATH`, or
    `MIND3_SKY130_ROOT` is preferred; otherwise the packaged
    fixture is used as a reference. A clear failure is raised when no
    Liberty file is available at all.
    """
    import shutil
    import subprocess

    from mind3.eda.timing_liberty import resolve_timing_liberty

    sta_bin = shutil.which("sta") or shutil.which("opensta")
    if sta_bin is None:
        pytest.skip("neither sta nor opensta found on PATH.")
    ver = subprocess.run([sta_bin, "-version"], capture_output=True, text=True, timeout=30)
    assert ver.returncode == 0
    assert ver.stdout.strip() or ver.stderr.strip()

    liberty, liberty_source = resolve_timing_liberty()
    assert liberty is not None and liberty.exists(), (
        "no timing Liberty available: set MIND3_NEGATIVE_CONTROL_LIBERTY, "
        "MIND3_LIBERTY_PATH, or MIND3_SKY130_ROOT to a real SKY130 library "
        "and ensure the packaged fixture is present"
    )
    (tmp_path / "smoke.v").write_text(
        "module smoke(clk, a, y);\n  input clk;\n  input a;\n  output y;\n"
        "  assign y = a;\nendmodule\n"
    )
    (tmp_path / "smoke.sdc").write_text("create_clock -name clk -period 10.0 [get_ports clk]\n")
    (tmp_path / "smoke.tcl").write_text(
        f"read_liberty {liberty}\nread_verilog smoke.v\nlink_design smoke\n"
        "read_sdc smoke.sdc\nreport_checks\n"
    )
    run = subprocess.run(
        [sta_bin, "-exit", "smoke.tcl"], cwd=tmp_path,
        capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 0, f"OpenSTA workload failed: {run.stdout[-1500:]} {run.stderr[-1500:]}"
    assert "OpenSTA" in (run.stdout + run.stderr)


@_sta_mark
@pytest.mark.eda_tools("openroad")
def test_openroad_smoke_version() -> None:
    """OpenROAD must execute (`openroad -version`).

    Success proves the binary runs; it does NOT prove any PnR design passes.
    Skips with reason when the binary is absent (e.g. this macOS host).
    """
    import shutil
    import subprocess

    if shutil.which("openroad") is None:
        pytest.skip("openroad binary not found on PATH.")
    run = subprocess.run(["openroad", "-version"], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0
    combined = (run.stdout + run.stderr).strip()
    assert combined, "openroad -version produced no output"


@_sta_mark
@pytest.mark.eda_tools("yosys")
def test_gate6_cdc_fixture_environment_behavior(tmp_path) -> None:
    """Real Gate 6 on the cdc_violation fixture: violation where tooling runs,
    CDC_TOOLING_UNAVAILABLE where it does not. Never a pass without execution."""
    import shutil
    from pathlib import Path

    from mind3.core.verifier import SiliconSignoffVerifier
    from mind3.sandbox.remote_eda import LocalBwrapRunner

    repo_root = Path(__file__).resolve().parents[1]
    fixture = repo_root / "tests/negative_controls/cdc_violation.sv"
    assert fixture.exists()
    ws = tmp_path / "cdc_env"
    ws.mkdir()
    (ws / "cdc_violation.sv").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    verifier = SiliconSignoffVerifier(
        top_module="cdc_violation", contract=None, allow_mock_fallback=False, require_cdc=True,
    )
    runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
    res = verifier._run_gate6_cdc_analysis(runner, [ws / "cdc_violation.sv"], ws)
    assert res["simulated"] is False
    if shutil.which("yosys") is None:
        assert res["passed"] is False
        assert res["error_category"] == "EDA_BINARY_MISSING"
        return
    # Yosys present: stock builds without the cdc command fail closed here.
    assert res["passed"] is False
    assert res["error_category"] in ("CDC_TOOLING_UNAVAILABLE", "CDC_VIOLATION")
    if res["error_category"] == "CDC_VIOLATION":
        assert len(res["cdc_violations"]) > 0
