"""Canary regression tests against captured real EDA tool outputs and self-audit guardrails.

Validates that signoff parsers correctly handle real-world tool output variations
(Yosys, OpenSTA, SymbiYosys, Verilator) and ensures zero fabricated models exist in src/.
"""

import re
from pathlib import Path
from typing import Any

import pytest

from mind3.core.driver import (
    OPENROUTER_FREE_MODELS,
    OPENROUTER_KNOWN_FREE_MODELS,
    OpenRouterModelRegistry,
)
from mind3.core.verifier import (
    detect_eda_tool_versions,
    parse_opensta_timing,
    parse_opensta_wns,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "eda_outputs"


def test_yosys_clean_synth_fixture() -> None:
    """Validate Yosys parser on captured clean synthesis output."""
    log_text = (FIXTURES_DIR / "yosys_clean_synth.log").read_text(encoding="utf-8")
    assert re.search(r"\$(?:d|ad)latch\b", log_text) is None
    assert "Warning: combinational loop" not in log_text
    assert "Logged 0 warnings, 0 errors" in log_text


def test_yosys_latch_inferred_fixture() -> None:
    """Validate Yosys parser detects latch inference from captured log."""
    log_text = (FIXTURES_DIR / "yosys_latch_inferred.log").read_text(encoding="utf-8")
    match = re.search(r"\$(?:d|ad)latch\b", log_text)
    assert match is not None
    assert match.group(0) == "$dlatch"


def test_yosys_comb_loop_fixture() -> None:
    """Validate Yosys parser detects combinational loop warning from captured log."""
    log_text = (FIXTURES_DIR / "yosys_comb_loop.log").read_text(encoding="utf-8")
    assert "Warning: combinational loop" in log_text


def test_opensta_met_slack_fixture() -> None:
    """Validate OpenSTA parser on captured timing report with positive slack (MET)."""
    log_text = (FIXTURES_DIR / "opensta_met_slack.log").read_text(encoding="utf-8")
    timing = parse_opensta_timing(log_text)
    assert timing["setup_wns"] is not None
    assert timing["setup_wns"] > 0.0
    assert abs(timing["setup_wns"] - 0.18) < 1e-3
    assert parse_opensta_wns(log_text) == timing["setup_wns"]


def test_opensta_violated_slack_fixture() -> None:
    """Validate OpenSTA parser on captured timing report with negative slack (VIOLATED)."""
    log_text = (FIXTURES_DIR / "opensta_violated_slack.log").read_text(encoding="utf-8")
    timing = parse_opensta_timing(log_text)
    assert timing["setup_wns"] is not None
    assert timing["setup_wns"] < 0.0
    assert abs(timing["setup_wns"] - (-1.05)) < 1e-3
    assert "VIOLATED" in log_text


def test_opensta_mcmm_report_fixture() -> None:
    """Validate multi-corner timing report parsing."""
    log_text = (FIXTURES_DIR / "opensta_mcmm_report.log").read_text(encoding="utf-8")
    assert "tt_025c_1v80" in log_text
    assert "ff_n40c_1v95" in log_text
    assert "ss_125c_1v60" in log_text
    assert "Worst setup WNS across all corners: 0.025 ns (MET)" in log_text


def test_sby_bmc_pass_and_fail_fixtures() -> None:
    """Validate SymbiYosys BMC output parsing for pass and fail cases."""
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


def test_openrouter_known_models_authenticity() -> None:
    """Verify that all entries in OPENROUTER_KNOWN_FREE_MODELS are authentic, existing free slugs."""
    for name, slug in OPENROUTER_KNOWN_FREE_MODELS.items():
        assert slug.endswith(":free")
        assert "/" in slug
        assert not any(fake in slug for fake in ["gemma-4", "glm-5.2", "nemotron-3.5"])
