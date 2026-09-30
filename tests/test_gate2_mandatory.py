"""Mandatory P4 Gate 2 Formal Verification Test Suite.
Verifies all 7 required invariants using live SBY execution.
"""

import tempfile
from pathlib import Path
import pytest

from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    SVAProperty,
    VerificationHarnessGenerator,
    UnsupportedFormalPropertyError,
)
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.remote_eda import LocalBwrapRunner


def test_1_comb_pass():
    """Combinational DUT verified clean via live SBY BMC."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut_file = ws / "comb_adder.sv"
        dut_file.write_text(
            "module comb_adder(input [3:0] a, b, output [3:0] sum);\n"
            "  assign sum = a + b;\n"
            "endmodule\n"
        )
        contract = InterfaceContract(
            module_name="comb_adder",
            functional_spec="4-bit adder",
            ports=[
                PortDefinition(name="a", direction=PortDirection.INPUT, width=4),
                PortDefinition(name="b", direction=PortDirection.INPUT, width=4),
                PortDefinition(name="sum", direction=PortDirection.OUTPUT, width=4),
            ],
            sva_properties=[
                SVAProperty(name="correct_sum", property_expr="sum == (a + b)"),
            ],
        )
        verifier = SiliconSignoffVerifier(top_module="comb_adder", contract=contract, allow_mock_fallback=False)
        runner = LocalBwrapRunner(ws)
        res = verifier._run_gate2_formal_sby(runner, [dut_file], ws)
        assert res["passed"] is True, f"Combinational PASS failed: {res.get('details')}"
        assert res["simulated"] is False


def test_2_comb_fail():
    """Buggy combinational DUT caught via live SBY with counterexample."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut_file = ws / "comb_adder_buggy.sv"
        dut_file.write_text(
            "module comb_adder_buggy(input [3:0] a, b, output [3:0] sum);\n"
            "  assign sum = a ^ b; // Bug: XOR instead of ADD\n"
            "endmodule\n"
        )
        contract = InterfaceContract(
            module_name="comb_adder_buggy",
            functional_spec="4-bit adder",
            ports=[
                PortDefinition(name="a", direction=PortDirection.INPUT, width=4),
                PortDefinition(name="b", direction=PortDirection.INPUT, width=4),
                PortDefinition(name="sum", direction=PortDirection.OUTPUT, width=4),
            ],
            sva_properties=[
                SVAProperty(name="correct_sum", property_expr="sum == (a + b)"),
            ],
        )
        verifier = SiliconSignoffVerifier(top_module="comb_adder_buggy", contract=contract, allow_mock_fallback=False)
        runner = LocalBwrapRunner(ws)
        res = verifier._run_gate2_formal_sby(runner, [dut_file], ws)
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"
        assert res["failing_property"] is not None or "assert" in res["stdout"].lower()


def test_3_seq_pass():
    """Sequential DUT verified clean via live SBY BMC."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut_file = ws / "seq_reg.sv"
        dut_file.write_text(
            "module seq_reg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= d;\n"
            "  end\n"
            "endmodule\n"
        )
        contract = InterfaceContract(
            module_name="seq_reg",
            functional_spec="Register with active-low reset",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="d", direction=PortDirection.INPUT, width=8),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=8),
            ],
            sva_properties=[
                SVAProperty(name="reset_val", property_expr="!rst_n |-> (q == 8'h00)"),
            ],
        )
        verifier = SiliconSignoffVerifier(top_module="seq_reg", contract=contract, allow_mock_fallback=False)
        runner = LocalBwrapRunner(ws)
        res = verifier._run_gate2_formal_sby(runner, [dut_file], ws)
        assert res["passed"] is True, f"Sequential PASS failed: {res.get('details')}"
        assert res["simulated"] is False


def test_4_seq_fail():
    """Buggy sequential DUT caught via live SBY BMC."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut_file = ws / "seq_reg_buggy.sv"
        dut_file.write_text(
            "module seq_reg_buggy(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'hFF; // BUG: resets to 0xFF instead of 0x00\n"
            "    else q <= d;\n"
            "  end\n"
            "endmodule\n"
        )
        contract = InterfaceContract(
            module_name="seq_reg_buggy",
            functional_spec="Register with active-low reset",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="d", direction=PortDirection.INPUT, width=8),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=8),
            ],
            sva_properties=[
                SVAProperty(name="reset_val", property_expr="!rst_n |-> (q == 8'h00)"),
            ],
        )
        verifier = SiliconSignoffVerifier(top_module="seq_reg_buggy", contract=contract, allow_mock_fallback=False)
        runner = LocalBwrapRunner(ws)
        res = verifier._run_gate2_formal_sby(runner, [dut_file], ws)
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"


def test_5_no_reset_seq_has_no_reset_references():
    """Sequential contract without reset must have zero reset references in harness."""
    contract = InterfaceContract(
        module_name="free_running",
        functional_spec="Free running counter",
        ports=[
            PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="q", direction=PortDirection.OUTPUT, width=4),
        ],
        sva_properties=[
            SVAProperty(name="valid_range", property_expr="q <= 4'd15"),
        ],
    )
    sva_code = VerificationHarnessGenerator.build_sva_bind_module(contract)
    wrapper_code = VerificationHarnessGenerator.build_formal_wrapper(contract)
    assert "rst" not in sva_code.lower()
    assert "reset" not in sva_code.lower()
    assert "rst" not in wrapper_code.lower()
    assert "reset" not in wrapper_code.lower()


def test_6_clockless_comb_has_no_clock_references():
    """Combinational contract without clock must have zero clock references in harness."""
    contract = InterfaceContract(
        module_name="pure_comb",
        functional_spec="Pure combinational mux",
        ports=[
            PortDefinition(name="sel", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="a", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="b", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="y", direction=PortDirection.OUTPUT, width=1),
        ],
        sva_properties=[
            SVAProperty(name="mux_sel0", property_expr="!sel |-> (y == a)"),
        ],
    )
    sva_code = VerificationHarnessGenerator.build_sva_bind_module(contract)
    wrapper_code = VerificationHarnessGenerator.build_formal_wrapper(contract)
    assert "clk" not in sva_code.lower()
    assert "clock" not in sva_code.lower()
    assert "posedge" not in sva_code.lower()
    assert "clk" not in wrapper_code.lower()
    assert "clock" not in wrapper_code.lower()
    assert "posedge" not in wrapper_code.lower()


def test_7_unsupported_property_never_pass():
    """Unsupported complex temporal construct must fail closed with UNSUPPORTED_FORMAL_PROPERTY."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut_file = ws / "unsupported_dut.sv"
        dut_file.write_text("module unsupported_dut(input clk, output reg q); endmodule\n")
        contract = InterfaceContract(
            module_name="unsupported_dut",
            functional_spec="DUT with multi-cycle delay sequence",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=1),
            ],
            sva_properties=[
                SVAProperty(name="complex_seq", property_expr="req ##3 gnt"),
            ],
        )
        verifier = SiliconSignoffVerifier(top_module="unsupported_dut", contract=contract, allow_mock_fallback=False)
        runner = LocalBwrapRunner(ws)
        res = verifier._run_gate2_formal_sby(runner, [dut_file], ws)
        assert res["passed"] is False
        assert res["error_category"] == "UNSUPPORTED_FORMAL_PROPERTY"
