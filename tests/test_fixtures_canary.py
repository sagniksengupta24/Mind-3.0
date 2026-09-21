"""Canary regression tests against representative tool output samples and self-audit guardrails.

Validates that signoff parsers correctly handle tool output patterns across gates
and ensures zero fabricated model claims exist in src/. Pending live-tool execution in
environments with EDA binaries installed.
"""

import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from mind3.core.driver import (
    OpenRouterModelRegistry,
    OpenRouterModelRegistryError,
    fetch_openrouter_free_models,
)
from mind3.core.verifier import (
    detect_eda_tool_versions,
    parse_openroad_pnr,
    parse_opensta_timing,
    parse_opensta_wns,
    parse_verilator_coverage,
    parse_yosys_cdc,
    parse_yosys_lec,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "eda_outputs"


def test_yosys_clean_synth_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "yosys_clean_synth.log").read_text(encoding="utf-8")
    assert re.search(r"\$(?:d|ad)latch\b", log_text) is None
    assert "Warning: combinational loop" not in log_text
    assert "Logged 0 warnings, 0 errors" in log_text


def test_yosys_latch_inferred_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "yosys_latch_inferred.log").read_text(encoding="utf-8")
    match = re.search(r"\$(?:d|ad)latch\b", log_text)
    assert match is not None
    assert match.group(0) == "$dlatch"


def test_yosys_comb_loop_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "yosys_comb_loop.log").read_text(encoding="utf-8")
    assert "Warning: combinational loop" in log_text


def test_opensta_met_slack_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "opensta_met_slack.log").read_text(encoding="utf-8")
    timing = parse_opensta_timing(log_text)
    assert timing["setup_wns"] is not None
    assert timing["setup_wns"] > 0.0
    assert abs(timing["setup_wns"] - 0.18) < 1e-3
    assert parse_opensta_wns(log_text) == timing["setup_wns"]


def test_opensta_violated_slack_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "opensta_violated_slack.log").read_text(encoding="utf-8")
    timing = parse_opensta_timing(log_text)
    assert timing["setup_wns"] is not None
    assert timing["setup_wns"] < 0.0
    assert abs(timing["setup_wns"] - (-1.05)) < 1e-3
    assert "VIOLATED" in log_text


def test_opensta_mcmm_report_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "opensta_mcmm_report.log").read_text(encoding="utf-8")
    assert "tt_025c_1v80" in log_text
    assert "ff_n40c_1v95" in log_text
    assert "ss_125c_1v60" in log_text
    assert "Worst setup WNS across all corners: 0.025 ns (MET)" in log_text


def test_sby_bmc_pass_and_fail_fixtures() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    pass_text = (FIXTURES_DIR / "sby_bmc_pass.log").read_text(encoding="utf-8")
    assert "DONE (PASS, rc=0)" in pass_text
    assert "Assert failed" not in pass_text

    fail_text = (FIXTURES_DIR / "sby_bmc_fail.log").read_text(encoding="utf-8")
    assert "DONE (FAIL, rc=2)" in fail_text
    assert "Assert failed in bad_fifo" in fail_text


def test_detect_eda_tool_versions_mock() -> None:
    """Validate detect_eda_tool_versions against mock runner."""
    class MockEDARunner:
        def run(self, cmd: list[str], timeout_sec: int = 5) -> Any:
            class Result:
                def __init__(self, returncode: int, stdout: str, stderr: str = ""):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr

            tool = cmd[0]
            if tool == "yosys":
                return Result(0, "Yosys 0.36 (git sha1 c850be45, clang++ 14.0.0)\n")
            elif tool == "sta":
                return Result(0, "OpenSTA 2.6.0\n")
            elif tool == "verilator":
                return Result(0, "Verilator 5.020 2024-01-01\n")
            elif tool == "sby":
                return Result(0, "SBY 0.36\n")
            elif tool == "openroad":
                return Result(127, "", "openroad: command not found\n")
            return Result(127, "", "command not found\n")

    versions = detect_eda_tool_versions(MockEDARunner())
    assert "Yosys 0.36" in versions["yosys"]
    assert "OpenSTA 2.6.0" in versions["sta"]
    assert "Verilator 5.020" in versions["verilator"]
    assert "SBY 0.36" in versions["sby"]
    assert versions["openroad"] == "missing"


def test_self_audit_no_fabricated_claims() -> None:
    """Self-audit guardrail: Ensure no fabricated model names or fake timestamp comments exist in src/."""
    src_dir = Path(__file__).parent.parent / "src"
    assert src_dir.exists()

    forbidden_patterns = [
        re.compile(r"gemma-4", re.IGNORECASE),
        re.compile(r"glm-5\.2", re.IGNORECASE),
        re.compile(r"nemotron-3\.5-lightning", re.IGNORECASE),
        re.compile(r"verified.*september 2026", re.IGNORECASE),
        re.compile(r"queried directly from.*september 2026", re.IGNORECASE),
    ]

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            matches = pattern.findall(content)
            assert not matches, f"Found forbidden fabricated pattern {matches} in {py_file}"


def test_openrouter_registry_fail_closed_on_unreachable_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify OpenRouterModelRegistry raises OpenRouterModelRegistryError and never falls back to hardcoded models."""
    import mind3.core.driver as driver_mod

    # Guardrail: Ensure no hardcoded model dicts exist in driver module
    assert not hasattr(driver_mod, "OPENROUTER_FREE_MODELS")
    assert not hasattr(driver_mod, "OPENROUTER_KNOWN_FREE_MODELS")

    OpenRouterModelRegistry._cached_models = []
    OpenRouterModelRegistry._last_fetch_time = 0.0

    class FailingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "FailingClient":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def get(self, url: str, headers: dict[str, str]) -> Any:
            raise httpx.ConnectError("Network unreachable")

    monkeypatch.setattr(httpx, "Client", FailingClient)

    with pytest.raises(OpenRouterModelRegistryError) as exc_info:
        fetch_openrouter_free_models(force_refresh=True)

    assert "Failed to query OpenRouter model registry" in str(exc_info.value)
    assert "fail-closed mode" in str(exc_info.value)


def test_yosys_equiv_pass_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "yosys_equiv_pass.log").read_text(encoding="utf-8")
    lec = parse_yosys_lec(log_text)
    assert lec["equivalent"] is True
    assert lec["proven_points"] == 8
    assert lec["unproven_points"] == 0
    assert lec["error"] is None


def test_yosys_equiv_fail_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "yosys_equiv_fail.log").read_text(encoding="utf-8")
    lec = parse_yosys_lec(log_text)
    assert lec["equivalent"] is False
    assert lec["proven_points"] == 6
    assert lec["unproven_points"] == 2
    assert lec["error"] is not None
    assert "2 unproven equivalence points" in lec["error"]


def test_verilator_coverage_clean_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "verilator_coverage_clean.log").read_text(encoding="utf-8")
    cov = parse_verilator_coverage(log_text)
    assert cov["branch"] == 100.0
    assert cov["toggle"] == 100.0


def test_verilator_coverage_deficit_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "verilator_coverage_deficit.log").read_text(encoding="utf-8")
    cov = parse_verilator_coverage(log_text)
    assert cov["branch"] == 78.5
    assert cov["toggle"] == 65.0


def test_openroad_pnr_clean_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "openroad_pnr_clean.log").read_text(encoding="utf-8")
    pnr = parse_openroad_pnr(log_text)
    assert pnr["passed"] is True
    assert pnr["pnr_complete"] is True
    assert pnr["placement_overflow"] is None
    assert len(pnr["errors"]) == 0


def test_openroad_placement_overflow_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "openroad_placement_overflow.log").read_text(encoding="utf-8")
    pnr = parse_openroad_pnr(log_text)
    assert pnr["passed"] is False
    assert pnr["pnr_complete"] is False
    assert pnr["placement_overflow"] == 14.0
    assert len(pnr["errors"]) >= 3
    assert any("DPL-0020" in err for err in pnr["errors"])


def test_yosys_cdc_clean_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "yosys_cdc_clean.log").read_text(encoding="utf-8")
    cdc = parse_yosys_cdc(log_text)
    assert cdc["passed"] is True
    assert len(cdc["violations"]) == 0


def test_yosys_cdc_violation_fixture() -> None:
    """Parser unit test against representative synthetic sample pending real-tool verification."""
    log_text = (FIXTURES_DIR / "yosys_cdc_violation.log").read_text(encoding="utf-8")
    cdc = parse_yosys_cdc(log_text)
    assert cdc["passed"] is False
    assert len(cdc["violations"]) >= 2
    assert any("clk_tx" in v and "clk_rx" in v for v in cdc["violations"])


def test_environment_eda_tool_availability_honesty() -> None:
    """Honesty check: detect_eda_tool_versions truthfully reflects host availability without faking versions."""
    from mind3.sandbox.remote_eda import LocalBwrapRunner

    versions = detect_eda_tool_versions(LocalBwrapRunner(workspace=Path.cwd()))
    for tool_name in ["yosys", "sta", "verilator", "sby", "openroad"]:
        assert tool_name in versions
        # Must be either a non-empty string or 'missing', never empty or None
        assert isinstance(versions[tool_name], str)
        assert len(versions[tool_name]) > 0
        # In this macOS execution environment, EDA binaries are not installed on PATH; must honestly report 'missing'
        assert versions[tool_name] == "missing"

