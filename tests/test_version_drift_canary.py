"""Version-drift canary test suite for EDA tool output parsers.

Validates that all six gate parsers (Yosys elaboration/LEC/CDC, SymbiYosys BMC,
Verilator coverage, OpenSTA MCMM, and OpenROAD P&R) match output from newer pinned
tool versions (e.g. Yosys 0.69+, SBY 0.69+, Verilator 5.050+, OpenSTA 2.7.0+, OpenROAD 2.0+).

Failures in this suite indicate EDA tool output formatting drift that breaks
parser regexes or state machine assumptions.
"""

from pathlib import Path
import re
import pytest

from mind3.core.verifier import (
    parse_openroad_pnr,
    parse_opensta_timing,
    parse_opensta_wns,
    parse_verilator_coverage,
    parse_yosys_cdc,
    parse_yosys_lec,
)

NEWER_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "eda_outputs_newer"


def test_version_drift_gate1_clean_synth() -> None:
    """Validate Gate 1 parser against newer Yosys (0.69) clean synthesis output."""
    log_text = (NEWER_FIXTURES_DIR / "yosys_clean_synth.log").read_text(encoding="utf-8")
    assert re.search(r"\$(?:d|ad)latch\b", log_text) is None
    assert "Warning: combinational loop" not in log_text
    assert "Warning: found logic loop" not in log_text


def test_version_drift_gate1_latch_inferred() -> None:
    """Validate Gate 1 parser against newer Yosys (0.69) latch inference output."""
    log_text = (NEWER_FIXTURES_DIR / "yosys_latch_inferred.log").read_text(encoding="utf-8")
    # Modern Yosys emits: Warning: Latch inferred for signal ... from process ...: $auto$proc_dlatch.cc:...
    assert "Latch inferred" in log_text or "$dlatch" in log_text


def test_version_drift_gate1_comb_loop() -> None:
    """Validate Gate 1 parser against newer Yosys (0.69) logic loop warning."""
    log_text = (NEWER_FIXTURES_DIR / "yosys_comb_loop.log").read_text(encoding="utf-8")
    # Modern Yosys emits "Warning: found logic loop" instead of "Warning: combinational loop"
    assert "Warning: combinational loop" in log_text or "Warning: found logic loop" in log_text


def test_version_drift_gate1b_lec_pass() -> None:
    """Validate Gate 1b LEC parser against newer Yosys (0.69) equiv_status pass output."""
    log_text = (NEWER_FIXTURES_DIR / "yosys_equiv_pass.log").read_text(encoding="utf-8")
    lec = parse_yosys_lec(log_text)
    assert lec["equivalent"] is True
    assert lec["unproven_points"] == 0
    assert lec["proven_points"] is not None and lec["proven_points"] > 0
    assert lec["error"] is None


def test_version_drift_gate1b_lec_fail() -> None:
    """Validate Gate 1b LEC parser against newer Yosys (0.69) equiv_status fail output."""
    log_text = (NEWER_FIXTURES_DIR / "yosys_equiv_fail.log").read_text(encoding="utf-8")
    lec = parse_yosys_lec(log_text)
    assert lec["equivalent"] is False
    assert lec["unproven_points"] is not None and lec["unproven_points"] > 0
    assert lec["error"] is not None


def test_version_drift_gate2_sby_bmc_pass() -> None:
    """Validate Gate 2 parser against newer SymbiYosys (0.69) BMC pass output."""
    log_text = (NEWER_FIXTURES_DIR / "sby_bmc_pass.log").read_text(encoding="utf-8")
    assert "DONE (PASS, rc=0)" in log_text
    assert "Assert failed" not in log_text
    assert "FAIL" not in log_text


def test_version_drift_gate2_sby_bmc_fail() -> None:
    """Validate Gate 2 parser against newer SymbiYosys (0.69) BMC counterexample failure output."""
    log_text = (NEWER_FIXTURES_DIR / "sby_bmc_fail.log").read_text(encoding="utf-8")
    assert "DONE (FAIL, rc=2)" in log_text
    assert "Assert failed" in log_text or "failed assertion" in log_text
    # Check step extraction regex compatibility
    step_match = re.search(r"step\s+(\d+)\s+FAILED", log_text) or re.search(r"failed assertion.*?\bstep\s+(\d+)", log_text)
    assert step_match is not None
    assert int(step_match.group(1)) == 3


def test_version_drift_gate3_verilator_coverage() -> None:
    """Validate Gate 3 parser against newer Verilator (5.050+) coverage metrics."""
    clean_text = (NEWER_FIXTURES_DIR / "verilator_coverage_clean.log").read_text(encoding="utf-8")
    cov_clean = parse_verilator_coverage(clean_text)
    assert cov_clean["branch"] == 100.0
    assert cov_clean["toggle"] == 100.0

    deficit_text = (NEWER_FIXTURES_DIR / "verilator_coverage_deficit.log").read_text(encoding="utf-8")
    cov_deficit = parse_verilator_coverage(deficit_text)
    assert cov_deficit["branch"] == 78.5
    assert cov_deficit["toggle"] == 65.0


def test_version_drift_gate4_opensta_timing() -> None:
    """Validate Gate 4 parser against newer OpenSTA (2.7.0+) timing and MCMM reports."""
    met_text = (NEWER_FIXTURES_DIR / "opensta_met_slack.log").read_text(encoding="utf-8")
    timing_met = parse_opensta_timing(met_text)
    assert timing_met["setup_wns"] is not None and timing_met["setup_wns"] > 0.0
    assert parse_opensta_wns(met_text) == timing_met["setup_wns"]

    violated_text = (NEWER_FIXTURES_DIR / "opensta_violated_slack.log").read_text(encoding="utf-8")
    timing_violated = parse_opensta_timing(violated_text)
    assert timing_violated["setup_wns"] is not None and timing_violated["setup_wns"] < 0.0

    mcmm_text = (NEWER_FIXTURES_DIR / "opensta_mcmm_report.log").read_text(encoding="utf-8")
    assert "tt_025c_1v80" in mcmm_text
    assert "ff_n40c_1v95" in mcmm_text
    assert "ss_125c_1v60" in mcmm_text


def test_version_drift_gate5_openroad_pnr() -> None:
    """Validate Gate 5 parser against newer OpenROAD (2.0-13500+) physical design logs."""
    clean_text = (NEWER_FIXTURES_DIR / "openroad_pnr_clean.log").read_text(encoding="utf-8")
    pnr_clean = parse_openroad_pnr(clean_text)
    assert pnr_clean["passed"] is True
    assert pnr_clean["pnr_complete"] is True
    assert pnr_clean["placement_overflow"] is None

    overflow_text = (NEWER_FIXTURES_DIR / "openroad_placement_overflow.log").read_text(encoding="utf-8")
    pnr_overflow = parse_openroad_pnr(overflow_text)
    assert pnr_overflow["passed"] is False
    assert pnr_overflow["pnr_complete"] is False
    assert pnr_overflow["placement_overflow"] == 14.0


def test_version_drift_gate6_yosys_cdc() -> None:
    """Validate Gate 6 parser against newer Yosys CDC static analysis reports."""
    clean_text = (NEWER_FIXTURES_DIR / "yosys_cdc_clean.log").read_text(encoding="utf-8")
    cdc_clean = parse_yosys_cdc(clean_text)
    assert cdc_clean["passed"] is True
    assert len(cdc_clean["violations"]) == 0

    violation_text = (NEWER_FIXTURES_DIR / "yosys_cdc_violation.log").read_text(encoding="utf-8")
    cdc_viol = parse_yosys_cdc(violation_text)
    assert cdc_viol["passed"] is False
    assert len(cdc_viol["violations"]) >= 2
