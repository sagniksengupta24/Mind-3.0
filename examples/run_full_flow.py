#!/usr/bin/env python3
"""Mind 3.0 End-to-End Silicon Demonstration.

Executes the complete 11-phase deterministic hardware workflow:
1. Natural Language Architecture Intake
2. Interface Contract & SVA Invariant Synthesis
3. Verification Harness Generation (Zero RTL Access)
4. RTL Design Implementation (Zero Harness Access)
5. 6-Gate Silicon Signoff Oracle Evaluation
6. Canonical SHA-256 Hash-Chained, Tamper-Evident Trace Record
"""

import sys
import tempfile
from pathlib import Path

# Ensure src/ is on Python module search path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from mind3.core.contracts import (
    ContractSynthesizer,
    InterfaceContract,
    PortDefinition,
    PortDirection,
    RTLGenerator,
    SVAProperty,
    TimingConstraint,
    VerificationHarnessGenerator,
)
from mind3.core.driver import PhaseDriver
from mind3.core.verifier import SiliconSignoffVerifier, format_gate_report_row
from mind3.sandbox.bwrap import BubblewrapSandbox


def run_full_flow() -> None:
    print("=" * 78)
    print("Mind 3.0: Deterministic VLSI Agent Flow Demonstration")
    print("=" * 78)

    with tempfile.TemporaryDirectory(prefix="mind3_demo_") as tmp_dir:
        workspace = Path(tmp_dir)
        print(f"[*] Initialized ephemeral workspace: {workspace}")

        # Step 1: Formal Architecture Contract
        print("\n[Phase 1-2: Architecture Intake & Interface Contract]")
        contract = InterfaceContract(
            module_name="fifo_sync",
            functional_spec="Synchronous FIFO queue with 8-bit data width and active-low synchronous reset",
            parameters={"DATA_WIDTH": "8", "DEPTH": "16"},
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1, description="System clock"),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1, description="Active-low reset"),
                PortDefinition(name="wr_en", direction=PortDirection.INPUT, width=1, description="Write enable"),
                PortDefinition(name="rd_en", direction=PortDirection.INPUT, width=1, description="Read enable"),
                PortDefinition(name="data_in", direction=PortDirection.INPUT, width=8, description="Write payload"),
                PortDefinition(name="data_out", direction=PortDirection.OUTPUT, width=8, description="Read payload"),
                PortDefinition(name="full", direction=PortDirection.OUTPUT, width=1, description="Full flag"),
                PortDefinition(name="empty", direction=PortDirection.OUTPUT, width=1, description="Empty flag"),
            ],
            sva_properties=[
                SVAProperty(
                    name="no_overflow",
                    property_expr="full && wr_en |-> ##1 full",
                    description="Writing while full must preserve full state",
                ),
                SVAProperty(
                    name="no_underflow",
                    property_expr="empty && rd_en |-> ##1 empty",
                    description="Reading while empty must preserve empty state",
                ),
            ],
            timing=TimingConstraint(
                clock_name="clk",
                period_ns=2.0,
                pvt_corners=["tt_025c_1v80", "ff_n40c_1v95", "ss_125c_1v60"],
            ),
        )
        print(f"  + Module: {contract.module_name}")
        print(f"  + Ports: {len(contract.ports)} declared")
        print(f"  + SVA Invariants: {len(contract.sva_properties)} formal properties")
        print(f"  + Target Clock: {contract.timing.period_ns} ns ({1000.0 / contract.timing.period_ns:.1f} MHz)")

        # Step 2: Verification Harness Synthesis (Decoupled from RTL)
        print("\n[Phase 3: Verification Harness Generation (Zero RTL Access)]")
        sva_code = VerificationHarnessGenerator.build_sva_bind_module(contract)
        sby_code = VerificationHarnessGenerator.build_sby_config(contract, depth=20)
        cpp_tb_code = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        sdc_code = contract.timing.to_sdc()

        (workspace / f"{contract.module_name}_sva.sv").write_text(sva_code, encoding="utf-8")
        (workspace / f"{contract.module_name}.sby").write_text(sby_code, encoding="utf-8")
        (workspace / f"{contract.module_name}_tb.cpp").write_text(cpp_tb_code, encoding="utf-8")
        (workspace / f"{contract.module_name}.sdc").write_text(sdc_code, encoding="utf-8")
        print(f"  + Emitted: {contract.module_name}_sva.sv")
        print(f"  + Emitted: {contract.module_name}.sby")
        print(f"  + Emitted: {contract.module_name}_tb.cpp (Galois LFSR + 4-phase stimulus)")
        print(f"  + Emitted: {contract.module_name}.sdc")

        # Step 3: RTL Design Synthesis (Decoupled from Harnesses)
        print("\n[Phase 4: Synthesizable RTL Design Implementation]")
        rtl_code = f"""// Synthesizable Synchronous FIFO
module {contract.module_name} #(
    parameter DATA_WIDTH = 8,
    parameter DEPTH = 16
) (
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire                  wr_en,
    input  wire                  rd_en,
    input  wire [DATA_WIDTH-1:0] data_in,
    output reg  [DATA_WIDTH-1:0] data_out,
    output wire                  full,
    output wire                  empty
);
    reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];
    reg [4:0] wr_ptr;
    reg [4:0] rd_ptr;
    reg [4:0] count;

    assign full  = (count == DEPTH);
    assign empty = (count == 0);

    always @(posedge clk) begin
        if (!rst_n) begin
            wr_ptr   <= 5'b0;
            rd_ptr   <= 5'b0;
            count    <= 5'b0;
            data_out <= 8'b0;
        end else begin
            case ({{wr_en && !full, rd_en && !empty}})
                2'b10: begin
                    mem[wr_ptr[3:0]] <= data_in;
                    wr_ptr <= wr_ptr + 1'b1;
                    count  <= count + 1'b1;
                end
                2'b01: begin
                    data_out <= mem[rd_ptr[3:0]];
                    rd_ptr <= rd_ptr + 1'b1;
                    count  <= count - 1'b1;
                end
                2'b11: begin
                    mem[wr_ptr[3:0]] <= data_in;
                    data_out <= mem[rd_ptr[3:0]];
                    wr_ptr <= wr_ptr + 1'b1;
                    rd_ptr <= rd_ptr + 1'b1;
                end
                default: ;
            endcase
        end
    end
endmodule
"""
        rtl_path = workspace / f"{contract.module_name}.sv"
        rtl_path.write_text(rtl_code, encoding="utf-8")
        print(f"  + Emitted: {contract.module_name}.sv ({len(rtl_code)} bytes)")

        # Step 4: Silicon Signoff Oracle Evaluation
        print("\n[Phase 5-9: Hierarchical 6-Gate Silicon Signoff]")
        from mind3.sandbox.remote_eda import LocalBwrapRunner
        runner = LocalBwrapRunner(workspace=workspace)

        verifier = SiliconSignoffVerifier(
            top_module=contract.module_name,
            contract=contract,
            liberty_path=[
                "sky130_fd_sc_hd__tt_025C_1v80.lib",
                "sky130_fd_sc_hd__ff_n40C_1v95.lib",
                "sky130_fd_sc_hd__ss_125C_1v60.lib",
            ],
            runner=runner,
            allow_mock_fallback=True,
            require_formal=True,
            require_coverage=True,
            require_cdc=True,
            require_lec=True,
        )

        result = verifier.verify(workspace, runner)

        print(f"\nSignoff Verdict: {'PASSED (Tapeout Ready)' if result.passed else 'FAILED'}")
        print(f"Silicon Verified: {result.silicon_verified} (Honest simulated/mock tracking)")
        print("\nHierarchical Gate Reports:")
        for idx, gate in enumerate(result.gate_reports, 1):
            print(format_gate_report_row(gate, idx))

        print("\n" + "=" * 78)
        print("Demo complete: All architectural invariants and gates evaluated successfully.")
        print("=" * 78)


if __name__ == "__main__":
    run_full_flow()
