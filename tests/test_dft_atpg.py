"""Tests for Industrial DFT (JTAG, IEEE 1500) and ATPG Fault Coverage Verification."""

from mind3.core.dft import (
    ATPGSignoffVerifier,
    IEEE1500Wrapper,
    JTAGControllerConfig,
    JTAGControllerGenerator,
)


def test_jtag_tap_controller_synthesis() -> None:
    """Validate 16-state IEEE 1149.1 TAP Controller generation."""
    cfg = JTAGControllerConfig(
        module_name="my_jtag_tap",
        ir_width=5,
        idcode_hex=0x20002002,
        include_trst=True,
    )
    tap_v = JTAGControllerGenerator.generate_tap_controller(cfg)
    assert "module my_jtag_tap" in tap_v
    assert "STATE_TL_RESET" in tap_v
    assert "STATE_SHIFT_DR" in tap_v
    assert "STATE_SHIFT_IR" in tap_v
    assert "STATE_UPDATE_DR" in tap_v
    assert "STATE_UPDATE_IR" in tap_v
    assert "IDCODE_VAL = 32'h20002002" in tap_v
    assert "input  wire        trst_n," in tap_v


def test_ieee1500_core_wrapper() -> None:
    """Validate IEEE 1500 embedded core test wrapper generation."""
    wrapper_v = IEEE1500Wrapper.generate_core_wrapper(
        core_name="dsp_core",
        input_ports=[("data_in", 32), ("valid_in", 1)],
        output_ports=[("data_out", 32), ("ready_out", 1)],
    )
    assert "module dsp_core_1500_wrapper" in wrapper_v
    assert "input  wire wrck," in wrapper_v
    assert "input  wire select_wir," in wrapper_v
    assert "wire [31:0] data_in_to_core = select_wir ? w_extest_in : data_in;" in wrapper_v
    assert "assign data_out = select_wir ? w_extest_out : data_out_from_core;" in wrapper_v


def test_atpg_report_parser_clean() -> None:
    """Validate ATPG report parser with passing stuck-at and transition coverage."""
    report = """
    ------------------------------------------------------------------------------
                          Test Pattern Generation Summary
    ------------------------------------------------------------------------------
    Fault model: stuck-at
    Total faults: 154200
    Test coverage: 99.82%
    Fault coverage: 99.75%
    Total patterns: 1420

    Fault model: transition
    Transition fault coverage: 96.40%
    ------------------------------------------------------------------------------
    """
    res = ATPGSignoffVerifier.parse_atpg_report(report)
    assert res["passed"] is True
    assert res["stuck_at_coverage_pct"] == 99.82
    assert res["transition_coverage_pct"] == 96.40
    assert res["pattern_count"] == 1420
    assert len(res["violations"]) == 0


def test_atpg_report_parser_coverage_deficit() -> None:
    """Validate ATPG report parser fails when stuck-at coverage falls below 99.5%."""
    report = """
    ------------------------------------------------------------------------------
                          Test Pattern Generation Summary
    ------------------------------------------------------------------------------
    Fault model: stuck-at
    Total faults: 154200
    Test coverage: 98.40%
    Fault coverage: 98.10%
    Total patterns: 950
    ------------------------------------------------------------------------------
    """
    res = ATPGSignoffVerifier.parse_atpg_report(report)
    assert res["passed"] is False
    assert res["stuck_at_coverage_pct"] == 98.40
    assert any("below foundry signoff threshold" in v for v in res["violations"])
