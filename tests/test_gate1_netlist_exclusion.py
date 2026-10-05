"""Regression: Gate 1 synthesis outputs are never compile inputs.

A repair rewrites ``<top>.sv`` while a stale ``<top>_netlist.v`` from the
previous Gate 1 run remains. Compiling both declares the module twice
(``'counter_01' has already been declared``), failing every post-Gate-1
repair spuriously. Gate 1 regenerates the netlist deterministically, and
Gate 4 selects it explicitly, so excluding ``*_netlist.v`` from compile
inputs loses nothing.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mind3.core.verifier import SiliconSignoffVerifier


class _RecordingRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, cmd, timeout_sec: int = 60):
        self.commands.append([str(c) for c in cmd])
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_stale_netlist_excluded_from_gate1_compile(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "dut.sv").write_text(
        "module dut (input clk, output [7:0] q);\n"
        "  always @(posedge clk) q <= q + 1'b1;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    (ws / "dut_netlist.v").write_text(
        "module dut(input clk, output [7:0] q);\nendmodule\n",
        encoding="utf-8",
    )
    verifier = SiliconSignoffVerifier(top_module="dut", contract=None)
    runner = _RecordingRunner()
    verifier._run_gate1_yosys(runner, [ws / "dut.sv", ws / "dut_netlist.v"], ws)
    compile_cmds = [c for c in runner.commands if c and c[0] in ("iverilog", "verilator")]
    assert compile_cmds, "Gate 1 must attempt a compile stage"
    for cmd in compile_cmds:
        assert not any(arg.endswith("_netlist.v") for arg in cmd), cmd
        assert any(str(arg).endswith("dut.sv") for arg in cmd), cmd
