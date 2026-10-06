"""Regression: rtl-buddy-cdc report parsing and Gate 6 fallback wiring.

The JSON fixture is a real captured ``rtl-buddy-cdc lint --format json``
report on ``tests/negative_controls/cdc_violation.sv`` (NOT synthetic).
Only error-severity findings fail; warnings never do.
"""

from __future__ import annotations

import json
from pathlib import Path

from mind3.core.verifier import derive_cdc_clock_sdc, parse_rbcdc_report

FIXTURE = Path(__file__).parent / "fixtures" / "eda_outputs" / "rbcdc_cdc_violation.json"


def test_rbcdc_fixture_is_real_capture() -> None:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert report["tool"]["name"] == "rtl-buddy-cdc"
    assert report["module"] == "cdc_violation"
    assert report["summary"]["violations"] == 3


def test_rbcdc_parser_flags_errors_only() -> None:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = parse_rbcdc_report(report)
    assert parsed["passed"] is False
    assert parsed["error_count"] == 2
    assert len(parsed["violations"]) == 2
    assert any(v.startswith("CDC-001 error") for v in parsed["violations"])
    assert all("warning" not in v.split(" ", 2)[1] for v in parsed["violations"])


def test_rbcdc_parser_passes_clean_report() -> None:
    parsed = parse_rbcdc_report({
        "summary": {"violations": 0},
        "violations": [
            {"rule_id": "CDC-011", "severity": "warning",
             "message": "untyped port", "location": {"file": "d.sv", "line": 3}},
        ],
    })
    assert parsed["passed"] is True
    assert parsed["violations"] == []
    assert parsed["warning_count"] == 1


def test_rbcdc_parser_rejects_garbage() -> None:
    assert parse_rbcdc_report({})["passed"] is True
    assert parse_rbcdc_report({"violations": "nonsense"})["passed"] is True


def test_clock_sdc_derivation() -> None:
    rtl = (
        "module cdc_violation (\n"
        "    input logic clk_a,\n"
        "    input logic clk_b,\n"
        "    input logic rst_n,\n"
        "    input logic data_a,\n"
        "    output logic data_b\n"
        ");\nendmodule\n"
    )
    sdc = derive_cdc_clock_sdc("cdc_violation", rtl)
    assert sdc is not None
    assert "create_clock -name clk_a" in sdc
    assert "create_clock -name clk_b" in sdc
    assert "set_clock_groups -asynchronous" in sdc
    assert "data_a" not in sdc and "rst_n" not in sdc


def test_clock_sdc_derivation_needs_no_clocks() -> None:
    assert derive_cdc_clock_sdc("m", "module m (input a, output y); endmodule") is None


def test_derived_sdc_types_single_clock_inputs_explicitly() -> None:
    from mind3.core.verifier import derive_cdc_clock_sdc

    rtl = (
        "module m (input clk, input rst_n, input [7:0] d, output [7:0] q);\n"
        "endmodule\n"
    )
    timing = (
        "create_clock -name clk -period 12.500 [get_ports clk]\n"
        "set_input_delay -clock clk 1.000 [all_inputs]\n"
    )
    sdc = derive_cdc_clock_sdc("m", rtl, timing)
    assert sdc is not None
    assert "create_clock -name clk -period 12.500 [get_ports clk]" in sdc
    assert "[all_inputs]" not in sdc
    assert "set_input_delay -clock clk 1.000 [get_ports rst_n]" in sdc
    assert "set_input_delay -clock clk 1.000 [get_ports d]" in sdc
    assert "set_clock_groups" not in sdc


def test_derived_sdc_multi_clock_leaves_inputs_untyped() -> None:
    from mind3.core.verifier import derive_cdc_clock_sdc

    rtl = "module m (input clk_a, input clk_b, input d, output y);\nendmodule\n"
    sdc = derive_cdc_clock_sdc("m", rtl, "")
    assert sdc is not None
    assert "set_clock_groups -asynchronous" in sdc
    assert "set_input_delay" not in sdc
