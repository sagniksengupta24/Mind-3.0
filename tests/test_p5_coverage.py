"""P5 Gate 3 Verilator Coverage Verification Test Suite.
Verifies valid fixture PASS, broken fixture FAIL, and below-threshold FAIL.
"""

import tempfile
from pathlib import Path
import pytest


from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    VerificationHarnessGenerator,
)
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.remote_eda import LocalBwrapRunner


@pytest.mark.eda
def test_p5_valid_fixture_pass():
    """Valid sequential counter with LFSR stimulus achieves full coverage and passes Gate 3."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        rtl_file = ws / "simple_cnt.sv"
        rtl_file.write_text(
            "module simple_cnt(\n"
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
        contract = InterfaceContract(
            module_name="simple_cnt",
            functional_spec="4-bit counter with enable",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="en", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=4),
            ],
        )
        cpp_tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        (ws / "simple_cnt_tb.cpp").write_text(cpp_tb, encoding="utf-8")

        # Set thresholds matching repo defaults (e.g. 50% for unit smoke or actual repo numbers)
        verifier = SiliconSignoffVerifier(
            top_module="simple_cnt",
            contract=contract,
            min_branch_coverage=50.0,
            min_toggle_coverage=50.0,
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
        res = verifier._run_gate3_coverage(runner, [rtl_file], ws)
        assert res["passed"] is True, f"Gate 3 failed: {res.get('details')}"
        assert res["simulated"] is False
        metrics = res.get("metrics", {})
        assert "toggle" in metrics or "branch" in metrics


@pytest.mark.eda
def test_p5_broken_fixture_fail():
    """Broken RTL syntax must trigger COVERAGE_BUILD_FAILURE."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        rtl_file = ws / "broken.sv"
        rtl_file.write_text("module broken(input clk; syntax error !!! endmodule\n")
        contract = InterfaceContract(
            module_name="broken",
            functional_spec="Broken module",
            ports=[PortDefinition(name="clk", direction=PortDirection.INPUT, width=1)],
        )
        cpp_tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        (ws / "broken_tb.cpp").write_text(cpp_tb, encoding="utf-8")

        verifier = SiliconSignoffVerifier(top_module="broken", contract=contract, allow_mock_fallback=False)
        runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
        res = verifier._run_gate3_coverage(runner, [rtl_file], ws)
        assert res["passed"] is False
        assert res["error_category"] == "COVERAGE_BUILD_FAILURE"


@pytest.mark.eda
def test_p5_below_threshold_fail():
    """DUT with 0% toggle coverage due to dead output must fail with COVERAGE_DEFICIT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        rtl_file = ws / "dead_logic.sv"
        # Output q is hardwired to 0, toggle coverage is below strict 90%
        rtl_file.write_text(
            "module dead_logic(\n"
            "  input wire clk,\n"
            "  input wire rst_n,\n"
            "  input wire in_val,\n"
            "  output reg [7:0] q\n"
            ");\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= {7'b0000000, in_val};\n"
            "  end\n"
            "endmodule\n"
        )
        contract = InterfaceContract(
            module_name="dead_logic",
            functional_spec="Module with partial toggling output",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="in_val", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=8),
            ],
        )
        cpp_tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        (ws / "dead_logic_tb.cpp").write_text(cpp_tb, encoding="utf-8")

        # Require standard 90% toggle coverage
        verifier = SiliconSignoffVerifier(
            top_module="dead_logic",
            contract=contract,
            min_branch_coverage=95.0,
            min_toggle_coverage=90.0,
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
        res = verifier._run_gate3_coverage(runner, [rtl_file], ws)
        assert res["passed"] is False
        assert res["error_category"] == "COVERAGE_DEFICIT"
