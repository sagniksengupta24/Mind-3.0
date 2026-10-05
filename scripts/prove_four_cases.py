#!/usr/bin/env python3
"""Execute and prove the four end-to-end verification cases with live EDA tools."""

import json
import os
import sys
import tempfile
from pathlib import Path

# Setup paths
MIND3_ROOT = Path(os.environ.get("MIND3_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(MIND3_ROOT / "src"))

from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    SVAProperty,
    VerificationHarnessGenerator,
)
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.remote_eda import LocalBwrapRunner

ARTIFACTS_P6 = Path(os.environ.get("MIND3_ARTIFACTS_DIR", MIND3_ROOT / "artifacts")) / "P6"
ARTIFACTS_P6.mkdir(parents=True, exist_ok=True)
LIBERTY_PATH = os.environ.get("MIND3_LIBERTY_PATH", "")


def run_case_a():
    """Case A: Full PASS (Gate 1 PASS, Gate 2 PASS, Gate 3 PASS -> Signoff PASS)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        rtl_code = (
            "module case_a(\n"
            "  input wire clk,\n"
            "  input wire rst_n,\n"
            "  input wire en,\n"
            "  output reg [3:0] q\n"
            ");\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 4'b0000;\n"
            "    else if (en) q <= q + 1;\n"
            "  end\n"
            "endmodule\n"
        )
        (ws / "case_a.sv").write_text(rtl_code, encoding="utf-8")
        contract = InterfaceContract(
            module_name="case_a",
            functional_spec="4-bit counter with reset and enable",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="en", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=4),
            ],
            sva_properties=[
                SVAProperty(name="reset_val", property_expr="!rst_n |-> (q == 4'b0000)"),
            ],
        )
        cpp_tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        (ws / "case_a_tb.cpp").write_text(cpp_tb, encoding="utf-8")

        verifier = SiliconSignoffVerifier(
            top_module="case_a",
            contract=contract,
            liberty_path=LIBERTY_PATH,
            min_branch_coverage=50.0,
            min_toggle_coverage=50.0,
            allow_mock_fallback=False,
            require_pnr=False,
            require_cdc=False,
        )
        runner = LocalBwrapRunner(ws)
        res = verifier.verify(ws, runner)  # type: ignore

        log_content = (
            f"=== CASE A: FULL PASS ===\n"
            f"Overall Passed: {res.passed}\n"
            f"Silicon Verified: {res.silicon_verified}\n"
            f"Failure Reason: {res.failure_reason}\n"
            f"Gate Reports:\n{json.dumps(res.gate_reports, indent=2)}\n"
        )
        (ARTIFACTS_P6 / "case_A.log").write_text(log_content, encoding="utf-8")
        assert res.passed is True
        assert res.silicon_verified is True
        print("[Case A] PROVEN: Full PASS cleanly verified.", flush=True)


def run_case_b():
    """Case B: Gate 1 PASS + genuine Gate 2 FAIL -> Signoff FAIL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        rtl_code = (
            "module case_b(\n"
            "  input wire clk,\n"
            "  input wire rst_n,\n"
            "  input wire [3:0] d,\n"
            "  output reg [3:0] q\n"
            ");\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 4'hF; // BUG: resets to 0xF instead of 0x0\n"
            "    else q <= d;\n"
            "  end\n"
            "endmodule\n"
        )
        (ws / "case_b.sv").write_text(rtl_code, encoding="utf-8")
        contract = InterfaceContract(
            module_name="case_b",
            functional_spec="4-bit register",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="d", direction=PortDirection.INPUT, width=4),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=4),
            ],
            sva_properties=[
                SVAProperty(name="reset_val", property_expr="!rst_n |-> (q == 4'h0)"),
            ],
        )
        cpp_tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        (ws / "case_b_tb.cpp").write_text(cpp_tb, encoding="utf-8")

        verifier = SiliconSignoffVerifier(
            top_module="case_b",
            contract=contract,
            liberty_path=LIBERTY_PATH,
            allow_mock_fallback=False,
            require_pnr=False,
            require_cdc=False,
        )
        runner = LocalBwrapRunner(ws)
        res = verifier.verify(ws, runner)  # type: ignore

        log_content = (
            f"=== CASE B: G1 PASS + G2 FAIL ===\n"
            f"Overall Passed: {res.passed}\n"
            f"Error Category: {res.error_category}\n"
            f"Failure Reason: {res.failure_reason}\n"
            f"Gate Reports:\n{json.dumps(res.gate_reports, indent=2)}\n"
        )
        (ARTIFACTS_P6 / "case_B.log").write_text(log_content, encoding="utf-8")
        assert res.passed is False
        assert res.error_category == "FORMAL_INVARIANT_BREACH"
        print("[Case B] PROVEN: G1 PASS + G2 FAIL -> Signoff FAIL.", flush=True)


def run_case_c():
    """Case C: Invalid RTL -> Gate 1 FAIL, no downstream PASS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        rtl_code = (
            "module case_c(input a, input sel, output reg y);\n"
            "  always @* begin\n"
            "    if (sel) y = a; // BUG: Incomplete if infers latch\n"
            "  end\n"
            "endmodule\n"
        )
        (ws / "case_c.sv").write_text(rtl_code, encoding="utf-8")
        contract = InterfaceContract(
            module_name="case_c",
            functional_spec="Combinational mux",
            ports=[
                PortDefinition(name="a", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="sel", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="y", direction=PortDirection.OUTPUT, width=1),
            ],
            sva_properties=[
                SVAProperty(name="mux_sel", property_expr="sel |-> (y == a)"),
            ],
        )
        verifier = SiliconSignoffVerifier(
            top_module="case_c",
            contract=contract,
            liberty_path=LIBERTY_PATH,
            allow_mock_fallback=False,
            require_pnr=False,
            require_cdc=False,
        )
        runner = LocalBwrapRunner(ws)
        res = verifier.verify(ws, runner)  # type: ignore

        log_content = (
            f"=== CASE C: INVALID RTL -> G1 FAIL ===\n"
            f"Overall Passed: {res.passed}\n"
            f"Error Category: {res.error_category}\n"
            f"Failure Reason: {res.failure_reason}\n"
            f"Gate Reports:\n{json.dumps(res.gate_reports, indent=2)}\n"
        )
        (ARTIFACTS_P6 / "case_C.log").write_text(log_content, encoding="utf-8")
        assert res.passed is False
        assert res.error_category == "LATCH_INFERRED"
        assert len(res.gate_reports) == 1  # Downstream gates halted
        print("[Case C] PROVEN: Invalid RTL halts at Gate 1, zero downstream passes.", flush=True)


def run_case_d():
    """Case D: Gate 1+2 PASS + Gate 3 FAIL -> Signoff FAIL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        rtl_code = (
            "module case_d(\n"
            "  input wire clk,\n"
            "  input wire rst_n,\n"
            "  input wire in_val,\n"
            "  output reg [7:0] q\n"
            ");\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= {7'b0000000, in_val}; // Dead: upper 7 bits never toggle\n"
            "  end\n"
            "endmodule\n"
        )
        (ws / "case_d.sv").write_text(rtl_code, encoding="utf-8")
        contract = InterfaceContract(
            module_name="case_d",
            functional_spec="Module with dead un-toggled bits",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="in_val", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=8),
            ],
            sva_properties=[
                SVAProperty(name="valid_reset", property_expr="!rst_n |-> (q == 8'h00)"),
            ],
        )
        cpp_tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        (ws / "case_d_tb.cpp").write_text(cpp_tb, encoding="utf-8")

        verifier = SiliconSignoffVerifier(
            top_module="case_d",
            contract=contract,
            liberty_path=LIBERTY_PATH,
            min_branch_coverage=95.0,
            min_toggle_coverage=90.0,
            allow_mock_fallback=False,
            require_pnr=False,
            require_cdc=False,
        )
        runner = LocalBwrapRunner(ws)
        res = verifier.verify(ws, runner)  # type: ignore

        log_content = (
            f"=== CASE D: G1+G2 PASS + G3 FAIL ===\n"
            f"Overall Passed: {res.passed}\n"
            f"Error Category: {res.error_category}\n"
            f"Failure Reason: {res.failure_reason}\n"
            f"Gate Reports:\n{json.dumps(res.gate_reports, indent=2)}\n"
        )
        (ARTIFACTS_P6 / "case_D.log").write_text(log_content, encoding="utf-8")
        assert res.passed is False
        assert res.error_category == "COVERAGE_DEFICIT"
        assert res.gate_reports[0]["passed"] is True  # Gate 1 PASS
        assert res.gate_reports[1]["passed"] is True  # Gate 2 PASS
        assert res.gate_reports[2]["passed"] is False  # Gate 3 FAIL
        print("[Case D] PROVEN: Gate 1+2 PASS + Gate 3 FAIL -> Signoff FAIL.", flush=True)


if __name__ == "__main__":
    run_case_a()
    run_case_b()
    run_case_c()
    run_case_d()
    print("ALL 4 END-TO-END CASES PROVEN WITH LIVE EDA ARTIFACTS.")
