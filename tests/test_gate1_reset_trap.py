"""Gate-1 partial-reset trap: structural, sync contracts only (tests only).

A clocked block that resets *some* registers but not others lets stale
sequential state survive reset. The trap fails Gate 1 closed with
INCOMPLETE_RESET and names the missing registers. Blocks with no reset
branch stay neutral; loop iterators, genvars, block-local temporaries and
memories (unpacked arrays) are excluded.
"""

import tempfile
from pathlib import Path

import pytest

from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    ResetContract,
)
from mind3.core.verifier import SiliconSignoffVerifier, reset_coverage_gaps
from mind3.sandbox.remote_eda import LocalBwrapRunner

REPO_ROOT = Path(__file__).resolve().parents[1]

HALFRESET = """module fsm_heldout_04 (
  input  logic clk,
  input  logic rst_n,
  input  logic din,
  output logic dout,
  output logic stuffed
);
  logic [2:0] ones;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      dout    <= 1'b0;
      stuffed <= 1'b0;
    end else if (ones == 3'd5) begin
      dout    <= 1'b0;
      stuffed <= 1'b1;
      ones    <= 3'd0;
    end else begin
      dout    <= din;
      stuffed <= 1'b0;
      ones    <= din ? ones + 3'd1 : 3'd0;
    end
  end
endmodule
"""

CLEAN_SYNC = """module clean_sync (
  input  logic clk,
  input  logic rst_n,
  input  logic din,
  output logic dout,
  output logic stuffed
);
  logic [2:0] ones;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      dout    <= 1'b0;
      stuffed <= 1'b0;
      ones    <= 3'd0;
    end else begin
      dout    <= din;
      stuffed <= 1'b0;
      ones    <= din ? ones + 3'd1 : 3'd0;
    end
  end
endmodule
"""

NORESET_DATAPATH = """module free_counter (
  input  logic clk,
  output logic [7:0] q
);
  always_ff @(posedge clk) begin
    q <= q + 8'd1;
  end
endmodule
"""

LOOP_MEMORY = """module fifo_like (
  input  logic clk,
  input  logic rst_n,
  input  logic wr_en,
  input  logic [7:0] wr_data,
  output logic full
);
  logic [7:0] mem [0:7];
  logic [2:0] wr_ptr;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_ptr <= 3'd0;
    end else begin
      for (int i = 0; i < 8; i++) mem[i] <= mem[i];
      if (wr_en) begin mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 3'd1; end
    end
  end
  assign full = 1'b0;
endmodule
"""


@pytest.mark.parametrize("flag", ["0", "1"])
def test_partial_reset_catches_halfreset_regardless_of_flag(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    """The pure analyzer is flag-independent (the flag gates the Gate-1 call
    site, never the analysis itself)."""
    monkeypatch.setenv("MIND3_GATE_FIXES", flag)
    gaps = reset_coverage_gaps(HALFRESET, "rst_n")
    assert len(gaps) == 1
    assert gaps[0]["missing"] == ["ones"]


@pytest.mark.parametrize("flag", ["0", "1"])
def test_partial_reset_passes_clean_and_neutral(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setenv("MIND3_GATE_FIXES", flag)
    assert reset_coverage_gaps(CLEAN_SYNC, "rst_n") == []
    assert reset_coverage_gaps(NORESET_DATAPATH, "rst_n") == []
    assert reset_coverage_gaps(LOOP_MEMORY, "rst_n") == []


def test_partial_reset_matches_repo_golden_and_mutant() -> None:
    """Analyzer agrees with the recorded corpus: only halfreset gaps."""
    repo_halfreset = (
        REPO_ROOT / "tests" / "golden_mutants" / "fsm_heldout_04__halfreset.sv"
    ).read_text(encoding="utf-8")
    assert reset_coverage_gaps(repo_halfreset, "rst_n")[0]["missing"] == ["ones"]
    repo_golden = (
        REPO_ROOT / "tests" / "golden" / "fsm_heldout_04.sv"
    ).read_text(encoding="utf-8")
    assert reset_coverage_gaps(repo_golden, "rst_n") == []


def _sync_contract() -> InterfaceContract:
    return InterfaceContract(
        module_name="fsm_heldout_04",
        functional_spec="t",
        ports=[
            PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="din", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="dout", direction=PortDirection.OUTPUT, width=1),
            PortDefinition(name="stuffed", direction=PortDirection.OUTPUT, width=1),
        ],
        reset=ResetContract(name="rst_n", polarity="active_low", synchronous=True),
    )


@pytest.mark.eda
def test_gate1_partial_reset_trap_fires_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Live: halfreset fails Gate 1 closed with the missing register named."""
    monkeypatch.setenv("MIND3_GATE_FIXES", "1")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "fsm_heldout_04.sv").write_text(HALFRESET, encoding="utf-8")
    verifier = SiliconSignoffVerifier(
        top_module="fsm_heldout_04",
        contract=_sync_contract(),
        allow_mock_fallback=False,
    )
    runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
    res = verifier._run_gate1_yosys(runner, [ws / "fsm_heldout_04.sv"], ws)
    assert res["passed"] is False
    assert res["error_category"] == "INCOMPLETE_RESET"
    assert res["missing_reset_registers"] == ["ones"]
    assert "ones" in str(res.get("details", ""))


@pytest.mark.eda
def test_gate1_partial_reset_trap_off_is_neutral_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Live: with the flag off the trap is skipped (byte-identical legacy)."""
    monkeypatch.setenv("MIND3_GATE_FIXES", "0")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "fsm_heldout_04.sv").write_text(HALFRESET, encoding="utf-8")
    verifier = SiliconSignoffVerifier(
        top_module="fsm_heldout_04",
        contract=_sync_contract(),
        allow_mock_fallback=False,
    )
    runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
    res = verifier._run_gate1_yosys(runner, [ws / "fsm_heldout_04.sv"], ws)
    assert res["error_category"] != "INCOMPLETE_RESET"
