"""Tests for the structural CDC checker (subprocess-based, no sys.path hacks).

Exercises the real CLI contract: executable exists, exit codes
(0 PASS / 1 FAIL / 2 INCONCLUSIVE / 3 ERROR), JSON report shape, and the
mandatory fixture matrix. INCONCLUSIVE/ERROR must never read as PASS.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tools" / "cdc_checker" / "tests"

# (fixture, expected exit code) — mirrors tools.cdc_checker.cli.PREFLIGHT_CASES
# plus the extended Phase 13 matrix.
MATRIX: tuple[tuple[str, int], ...] = (
    ("same_clock", 0),
    ("unsafe_direct", 1),
    ("safe_2ff", 0),
    ("unsafe_bypass", 1),
    ("safe_handshake", 0),
    ("unsafe_handshake", 1),
    ("safe_async_fifo", 0),
    ("multi_bit_unsafe", 2),
    ("unknown_structure", 2),
)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tools.cdc_checker", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_checker_executable_exists() -> None:
    proc = _run_cli("--preflight")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "preflight" in proc.stdout.lower()


@pytest.mark.parametrize(("fixture", "expected"), MATRIX)
def test_fixture_matrix(fixture: str, expected: int, tmp_path: Path) -> None:
    rtl = FIXTURES / f"{fixture}.sv"
    assert rtl.exists(), f"fixture missing: {rtl}"
    report_path = tmp_path / "cdc.json"
    proc = _run_cli("--rtl", str(rtl), "--top", fixture, "--report", str(report_path))
    assert proc.returncode == expected, proc.stdout + proc.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["tool"] == "structural_cdc_checker"
    assert report["tool_version"] == "1.0"
    assert report["top"] == fixture
    assert report["status"] in ("PASS", "FAIL", "INCONCLUSIVE", "ERROR")
    assert isinstance(report["crossings"], list)
    for crossing in report["crossings"]:
        for key in ("source", "source_clock", "destination", "destination_clock",
                    "path", "classification", "severity", "detail"):
            assert key in crossing


def test_inconclusive_is_not_pass(tmp_path: Path) -> None:
    proc = _run_cli("--rtl", str(FIXTURES / "unknown_structure.sv"),
                    "--top", "unknown_structure",
                    "--report", str(tmp_path / "cdc.json"))
    assert proc.returncode == 2
    report = json.loads((tmp_path / "cdc.json").read_text(encoding="utf-8"))
    assert report["status"] == "INCONCLUSIVE"


def test_input_error_exit_code(tmp_path: Path) -> None:
    bad = tmp_path / "bad.sv"
    bad.write_text("module bad(input logic a); for (genvar i = 0;;) begin end endmodule\n",
                   encoding="utf-8")
    proc = _run_cli("--rtl", str(bad), "--top", "bad",
                    "--report", str(tmp_path / "cdc.json"))
    assert proc.returncode == 3
    report = json.loads((tmp_path / "cdc.json").read_text(encoding="utf-8"))
    assert report["status"] == "ERROR"


def test_missing_top_is_error(tmp_path: Path) -> None:
    proc = _run_cli("--rtl", str(FIXTURES / "same_clock.sv"), "--top", "nope",
                    "--report", str(tmp_path / "cdc.json"))
    assert proc.returncode == 3


def test_version_pin_matches_verifier() -> None:
    from mind3.core.verifier import STRUCTURAL_CDC_VERSION

    assert STRUCTURAL_CDC_VERSION == "1.0"


def _structural_contract() -> "object":
    from mind3.core.contracts import (
        ClockContract,
        InterfaceContract,
        PortDefinition,
        PortDirection,
        ResetContract,
    )

    ports = [
        PortDefinition(name="clk", direction=PortDirection("input"), width=1),
        PortDefinition(name="rst_n", direction=PortDirection("input"), width=1),
    ]
    return InterfaceContract(
        module_name="gate6_mod",
        functional_spec="structural Gate 6 test design",
        ports=ports,
        clock=ClockContract(name="clk"),
        reset=ResetContract(name="rst_n", polarity="active_low", synchronous=True),
        async_inputs=None,
    )


def _gate6(mod_name: str, fixture: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    import shutil

    from mind3.core.verifier import SiliconSignoffVerifier

    monkeypatch.setattr("mind3.core.verifier.has_external_yosys_cdc", lambda: False)
    ws = tmp_path / "ws"
    ws.mkdir()
    # Fixture module names equal their file stems; analyze them directly.
    assert fixture == mod_name
    shutil.copy(FIXTURES / f"{fixture}.sv", ws / f"{mod_name}.sv")
    verifier = SiliconSignoffVerifier(
        top_module=mod_name,
        contract=_structural_contract(),  # type: ignore[arg-type]
        allow_mock_fallback=False,
        require_cdc=True,
    )
    return verifier._run_gate6_cdc_analysis(None, [ws / f"{mod_name}.sv"], ws)


def test_gate6_structural_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    res = _gate6("same_clock", "same_clock", tmp_path, monkeypatch)
    assert res["passed"] is True
    assert res["error_category"] is None
    assert res["cdc"]["implementation"] == "structural_cdc_checker"
    assert res["cdc"]["version"] == "1.0"


def test_gate6_structural_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    res = _gate6("unsafe_direct", "unsafe_direct", tmp_path, monkeypatch)
    assert res["passed"] is False
    assert res["error_category"] == "CDC_VIOLATION"
    assert len(res["cdc_violations"]) >= 1


def test_gate6_structural_inconclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    res = _gate6("unknown_structure", "unknown_structure", tmp_path, monkeypatch)
    assert res["passed"] is False
    assert res["error_category"] == "CDC_INCONCLUSIVE"


def test_gate6_no_fallback_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mind3.core.verifier import SiliconSignoffVerifier

    monkeypatch.setattr("mind3.core.verifier.has_external_yosys_cdc", lambda: False)
    monkeypatch.setenv("MIND3_CDC_NO_FALLBACK", "1")
    ws = tmp_path / "ws"
    ws.mkdir()
    verifier = SiliconSignoffVerifier(
        top_module="gate6_mod",
        contract=_structural_contract(),  # type: ignore[arg-type]
        allow_mock_fallback=False,
        require_cdc=True,
    )
    res = verifier._run_gate6_cdc_analysis(None, [], ws)
    assert res["passed"] is False
    assert res["error_category"] == "CDC_TOOLING_UNAVAILABLE"


def test_select_prefers_external_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from mind3.core import verifier as verifier_mod

    monkeypatch.setattr(verifier_mod, "has_external_yosys_cdc", lambda: True)
    assert verifier_mod.select_cdc_implementation()[0] == "external"
    monkeypatch.setattr(verifier_mod, "has_external_yosys_cdc", lambda: False)
    monkeypatch.setattr(verifier_mod, "has_crux", lambda: False)
    kind, version = verifier_mod.select_cdc_implementation()
    assert kind == "structural" and "1.0" in version


def test_run_cdc_preflight_clean() -> None:
    from mind3.core.verifier import run_cdc_preflight

    assert run_cdc_preflight() == []
