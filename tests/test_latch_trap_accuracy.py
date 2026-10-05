"""Regression: Gate 1 latch trap accuracy in both directions.

1. Yosys optimizer chatter (ff.cc "... ($dlatch) ..." for transient cells
   that are cleaned up) must not fail the gate when the final structured AST
   contains no latch cell.
2. A genuine combinational latch (`always @(*)` without `else`) must still
   fail closed as LATCH_INFERRED.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from mind3.core.verifier import SiliconSignoffVerifier

CHATTER = """4.6. Executing OPT_EXPR pass.
Setting constant 0-bit at position 0 on $auto$ff.cc:266:slice$9 ($dlatch) from module dut.
4.7. Executing OPT_CLEAN pass (remove unused cells and wires).
End of script."""


class _MockRunner:
    def __init__(self, ws: Path) -> None:
        self.ws = ws

    def run(self, cmd, timeout_sec: int = 60):
        if cmd and cmd[0] == "yosys":
            (self.ws / "dut_ast.json").write_text(
                json.dumps({"modules": {"dut": {"cells": {"$auto$ff.cc:0$slice$1": {"type": "$adff"}}}}}),
                encoding="utf-8",
            )
            (self.ws / "dut_netlist.v").write_text(
                "module dut(input clk, output [3:0] q);\nendmodule\n", encoding="utf-8"
            )
            return SimpleNamespace(returncode=0, stdout=CHATTER, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_optimizer_dlatch_chatter_is_not_a_latch(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "dut.sv").write_text(
        "module dut (input clk, input rst_n, output [3:0] q);\n"
        "  reg [3:0] q_reg;\n"
        "  always @(posedge clk or negedge rst_n) begin\n"
        "    if (!rst_n) q_reg <= 4'd0;\n"
        "    else q_reg <= q_reg + 4'd1;\n"
        "  end\n"
        "  assign q = q_reg;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    verifier = SiliconSignoffVerifier(top_module="dut", contract=None)
    result = verifier._run_gate1_yosys(_MockRunner(ws), [ws / "dut.sv"], ws)
    assert result["passed"] is True
    assert result.get("error_category") is None


def test_combinational_latch_still_fails_closed(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "lat.sv").write_text(
        "module lat (input a, input sel, output reg y);\n"
        "always @(*) begin\n"
        "if (sel) y = a;\n"
        "end\n"
        "endmodule\n",
        encoding="utf-8",
    )
    verifier = SiliconSignoffVerifier(top_module="lat", contract=None)
    result = verifier._run_gate1_yosys(_MockRunner(ws), [ws / "lat.sv"], ws)
    assert result["passed"] is False
    assert result.get("error_category") == "LATCH_INFERRED"
