"""Live verification canary for Gate 4 (OpenSTA) and Gate 5 (OpenROAD) using real SkyWater 130nm PDK.

Executes within the unprivileged Bubblewrap sandbox on Linux with zero mock fallbacks.
Skips gracefully if PDK artifacts or EDA tools are absent from host environment. Set `MIND3_SKY130_ROOT` to a SkyWater 130nm PDK root.
"""

from pathlib import Path
import os
import shutil
import tempfile
import pytest

from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.bwrap import BubblewrapSandbox
from mind3.sandbox.remote_eda import LocalBwrapRunner

SKY130_ROOT = Path(os.getenv("MIND3_SKY130_ROOT", "")).expanduser().resolve() if os.getenv("MIND3_SKY130_ROOT") else None
PDK_LIB = SKY130_ROOT / "libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib" if SKY130_ROOT else Path("__missing_sky130_lib__")
PDK_TLEF = SKY130_ROOT / "libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef" if SKY130_ROOT else Path("__missing_sky130_tlef__")
PDK_LEF = SKY130_ROOT / "libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef" if SKY130_ROOT else Path("__missing_sky130_lef__")

PDK_PRESENT = PDK_LIB.exists() and PDK_TLEF.exists() and PDK_LEF.exists()
BWRAP_PRESENT = shutil.which("bwrap") is not None
STA_PRESENT = shutil.which("sta") is not None
OPENROAD_PRESENT = shutil.which("openroad") is not None
YOSYS_PRESENT = shutil.which("yosys") is not None

COUNTER_VERILOG = """
module counter (
    input wire clk,
    input wire rst_n,
    output reg [7:0] count
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            count <= 8'h00;
        else
            count <= count + 1'b1;
    end
endmodule
"""

VALID_SDC = """
create_clock -name clk -period 10.0 [get_ports clk]
set_input_delay 2.0 -clock clk [get_ports rst_n]
set_output_delay 2.0 -clock clk [get_ports count*]
"""


@pytest.mark.skipif(
    not (PDK_PRESENT and BWRAP_PRESENT and STA_PRESENT and YOSYS_PRESENT),
    reason="Requires SkyWater 130nm PDK, bwrap, yosys, and OpenSTA on host",
)
def test_gate4_opensta_live_sky130_in_bubblewrap() -> None:
    """Gate 4 OpenSTA static timing analysis against authentic SkyWater 130nm Liberty file inside bwrap sandbox."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "counter.v").write_text(COUNTER_VERILOG, encoding="utf-8")
        (ws / "counter.sdc").write_text(VALID_SDC, encoding="utf-8")

        sb = BubblewrapSandbox(ws)
        runner = LocalBwrapRunner(ws, sandbox=sb)
        verifier = SiliconSignoffVerifier(
            top_module="counter",
            liberty_path=[PDK_LIB],
            allow_mock_fallback=False,
        )

        g1 = verifier._run_gate1_yosys(runner, [ws / "counter.v"], ws)
        assert g1["passed"] is True, f"Gate 1 failed: {g1.get('stderr')}"
        assert g1["simulated"] is False

        g4 = verifier._run_gate4_timing(runner, [ws / "counter.v"], ws)
        assert g4["passed"] is True, f"Gate 4 failed: {g4.get('stderr')} | {g4.get('details')}"
        assert g4["simulated"] is False
        assert g4["exit_code"] == 0
        assert g4["metrics"]["setup_wns"] is not None
        assert "Timing closure confirmed" in g4["details"]


@pytest.mark.skipif(
    not (PDK_PRESENT and BWRAP_PRESENT and OPENROAD_PRESENT and YOSYS_PRESENT),
    reason="Requires SkyWater 130nm PDK, bwrap, yosys, and OpenROAD on host",
)
def test_gate5_openroad_live_sky130_in_bubblewrap() -> None:
    """Gate 5 OpenROAD place-and-route against authentic SkyWater 130nm LEF/Liberty geometry inside bwrap sandbox."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "counter.v").write_text(COUNTER_VERILOG, encoding="utf-8")
        (ws / "counter.sdc").write_text(VALID_SDC, encoding="utf-8")

        sb = BubblewrapSandbox(ws)
        runner = LocalBwrapRunner(ws, sandbox=sb)
        verifier = SiliconSignoffVerifier(
            top_module="counter",
            liberty_path=[PDK_LIB],
            lef_path=[PDK_TLEF, PDK_LEF],
            require_pnr=True,
            allow_mock_fallback=False,
        )

        g1 = verifier._run_gate1_yosys(runner, [ws / "counter.v"], ws)
        assert g1["passed"] is True, f"Gate 1 failed: {g1.get('stderr')}"

        g5 = verifier._run_gate5_openroad_pnr(runner, [ws / "counter.v"], ws)
        assert g5["passed"] is True, f"Gate 5 failed: {g5.get('stderr')} | {g5.get('details')}"
        assert g5["simulated"] is False
        assert g5["exit_code"] == 0
        assert g5["metrics"]["pnr_complete"] is True
        assert g5["metrics"]["placement_overflow"] is None


@pytest.mark.skipif(
    not (PDK_PRESENT and BWRAP_PRESENT and STA_PRESENT and YOSYS_PRESENT),
    reason="Requires SkyWater 130nm PDK, bwrap, yosys, and OpenSTA on host",
)
def test_gate4_live_sky130_timing_violation_detection() -> None:
    """Gate 4 OpenSTA accurately detects timing violations under genuine tool execution without masking."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "counter.v").write_text(COUNTER_VERILOG, encoding="utf-8")
        # 100 picosecond clock period is physically unattainable in Sky130 130nm
        (ws / "counter.sdc").write_text(
            "create_clock -name clk -period 0.1 [get_ports clk]\n"
            "set_input_delay 0.05 -clock clk [get_ports rst_n]\n"
            "set_output_delay 0.05 -clock clk [get_ports count*]\n",
            encoding="utf-8",
        )

        sb = BubblewrapSandbox(ws)
        runner = LocalBwrapRunner(ws, sandbox=sb)
        verifier = SiliconSignoffVerifier(
            top_module="counter",
            liberty_path=[PDK_LIB],
            max_wns_ps=0.0,
            allow_mock_fallback=False,
        )

        verifier._run_gate1_yosys(runner, [ws / "counter.v"], ws)
        g4 = verifier._run_gate4_timing(runner, [ws / "counter.v"], ws)
        assert g4["passed"] is False
        assert g4["simulated"] is False
        assert g4["error_category"] == "TIMING_SLACK_VIOLATION"
        assert "Setup timing violation" in g4["details"]
