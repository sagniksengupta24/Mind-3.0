"""Regression: source discovery ignores tool-generated subdirectory copies.

SymbiYosys materializes ``<top>/src/<top>.sv`` copies inside its workdir.
A recursive workspace scan would compile those alongside the rewritten
top-level file, failing every post-formal repair with a spurious duplicate
module declaration. Discovery is top-level only, matching every other
artifact lookup in the pipeline (SDC, TCL, netlists).
"""

from __future__ import annotations

from pathlib import Path

from mind3.core.verifier import discover_rtl_sources


def test_discovery_ignores_sby_workdir_copies(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "dut").mkdir(parents=True)
    (ws / "dut" / "src").mkdir(parents=True)
    (ws / "dut.sv").write_text("module dut (input clk);\nendmodule\n", encoding="utf-8")
    (ws / "dut" / "src" / "dut.sv").write_text(
        "module dut (input clk);\nendmodule\n", encoding="utf-8"
    )
    (ws / "obj_dir").mkdir(parents=True)
    found = discover_rtl_sources(ws)
    assert found == [ws.resolve() / "dut.sv"]


def test_discovery_keeps_root_excludes_derived(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "dut.sv").write_text("module dut;\nendmodule\n", encoding="utf-8")
    (ws / "dut_netlist.v").write_text("module dut;\nendmodule\n", encoding="utf-8")
    (ws / "dut_tb.sv").write_text("module tb;\nendmodule\n", encoding="utf-8")
    found = discover_rtl_sources(ws)
    assert found == [ws.resolve() / "dut.sv"]
