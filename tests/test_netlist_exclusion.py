"""Regression: stale Yosys netlists must never poison signoff source selection.

A previous verify() pass writes ``<top>_netlist.v`` into the workspace. The
signoff source glob must exclude it: the netlist re-declares the top module,
and compiling it alongside the RTL made iverilog fail every repair turn with
a spurious duplicate-declaration error, so no valid design could pass Gate 1
twice (found during Track F, counter_04).
"""
from pathlib import Path

from mind3.core.verifier import _select_signoff_sources


def test_stale_netlist_excluded_from_signoff_sources(tmp_path: Path) -> None:
    (tmp_path / "dut.sv").write_text("module dut(input logic clk); endmodule\n", encoding="utf-8")
    (tmp_path / "dut_netlist.v").write_text("module dut(input clk); endmodule\n", encoding="utf-8")
    (tmp_path / "dut_tb.sv").write_text("module dut_tb; endmodule\n", encoding="utf-8")
    (tmp_path / "dut_sva.sv").write_text("// sva bind\n", encoding="utf-8")

    selected = [p.name for p in _select_signoff_sources(tmp_path.resolve())]
    assert selected == ["dut.sv"]


def test_netlist_exclusion_is_name_based_not_content_based(tmp_path: Path) -> None:
    (tmp_path / "helper_netlist.v").write_text("// just a comment\n", encoding="utf-8")
    (tmp_path / "top.sv").write_text("module top(input logic a); endmodule\n", encoding="utf-8")

    selected = [p.name for p in _select_signoff_sources(tmp_path.resolve())]
    assert selected == ["top.sv"]


def test_sby_workdir_copies_excluded_from_signoff_sources(tmp_path: Path) -> None:
    """SBY workdirs (<top>/src/<top>.sv) must not poison Gate 1 (arbiter_03)."""
    (tmp_path / "arbiter_03.sv").write_text("module arbiter_03(input logic clk); endmodule\n", encoding="utf-8")
    sby_src = tmp_path / "arbiter_03" / "src"
    sby_src.mkdir(parents=True)
    (sby_src / "arbiter_03.sv").write_text("module arbiter_03(input logic clk); endmodule\n", encoding="utf-8")
    sby_model = tmp_path / "arbiter_03" / "model"
    sby_model.mkdir(parents=True)
    (sby_model / "design.il").write_text("// yosys IL\n", encoding="utf-8")

    selected = [p.relative_to(tmp_path.resolve()).as_posix() for p in _select_signoff_sources(tmp_path.resolve())]
    assert selected == ["arbiter_03.sv"]


def test_genuine_src_subdir_still_included(tmp_path: Path) -> None:
    """A shared <ws>/src/helper.sv must keep compiling (only <top>/ nesting is cut)."""
    (tmp_path / "top.sv").write_text("module top(input logic a); endmodule\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.sv").write_text("module helper(input logic a); endmodule\n", encoding="utf-8")

    selected = sorted(p.relative_to(tmp_path.resolve()).as_posix() for p in _select_signoff_sources(tmp_path.resolve()))
    assert selected == ["src/helper.sv", "top.sv"]
