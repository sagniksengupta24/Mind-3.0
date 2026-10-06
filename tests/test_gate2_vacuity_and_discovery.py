"""Regression: nested tool-generated RTL never enters compilation,
and formal vacuity is reported honestly in both directions.

- R5: a workspace with a root design file plus a nested duplicate (the SBY
  workdir shape) must compile only the root file.
- R3a: an implication with an unreachable antecedent through real Gate 2
  must yield VACUOUS_PROPERTY, never an ordinary PASS.
- R3b: a reachable-antecedent implication through real Gate 2 must PASS.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from mind3.core.verifier import RTLVerifier, SiliconSignoffVerifier
from mind3.sandbox.bwrap import BubblewrapSandbox
from mind3.sandbox.remote_eda import LocalBwrapRunner


def _needs_bwrap_sby() -> None:
    if shutil.which("bwrap") is None or shutil.which("sby") is None:
        pytest.skip("requires bwrap and sby on PATH")


def test_nested_tool_copy_excluded_from_compilation(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    (ws / "tooldir" / "src").mkdir(parents=True)
    (ws / "top.sv").write_text(
        "module top(input clk, output reg q); always @(posedge clk) q <= ~q; endmodule\n"
    )
    (ws / "tooldir" / "src" / "top.sv").write_text(
        "module top(input clk, output reg q); always @(posedge clk) q <= ~q; endmodule\n"
    )
    (ws / "tb.sv").write_text(
        "module tb; reg clk = 0; wire q; top dut(.clk(clk), .q(q));"
        " initial begin #10 $finish; end always #1 clk = ~clk; endmodule\n"
    )
    if shutil.which("bwrap") is None or shutil.which("iverilog") is None:
        pytest.skip("requires bwrap and iverilog on PATH")
    res = RTLVerifier(top_module="tb", testbench_path="tb.sv").verify(
        ws, BubblewrapSandbox(ws)
    )
    assert res.passed is True


@pytest.mark.eda
@pytest.mark.eda_tools("sby")
def test_unreachable_antecedent_is_vacuous_not_pass(tmp_path: Path) -> None:
    _needs_bwrap_sby()
    from mind3.benchmarks.runner import contract_from_benchmark_record

    rec = {
        "task_id": "vacuity_probe",
        "expected_ports": [
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst_n", "direction": "input", "width": 1},
            {"name": "up", "direction": "input", "width": 1},
            {"name": "down", "direction": "input", "width": 1},
            {"name": "count", "direction": "output", "width": 8},
        ],
        "sva_properties": [],
        "expected_properties": [
            "assert property (@(posedge clk) disable iff (!rst_n)"
            " (count == 8'hFF && count == 8'h00) |=> count == 8'hFF);"
        ],
        "verification_requirements": [],
    }
    contract = contract_from_benchmark_record(rec)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "vacuity_probe.sv").write_text(
        "module vacuity_probe (input clk, input rst_n, input up, input down,"
        " output [7:0] count);\n"
        " reg [7:0] c;\n"
        " always @(posedge clk or negedge rst_n) begin"
        " if (!rst_n) c <= 0; else c <= c + 1; end\n"
        " assign count = c;\nendmodule\n"
    )
    runner = LocalBwrapRunner(ws, sandbox=None, allow_unsandboxed=True)
    verifier = SiliconSignoffVerifier(
        top_module="vacuity_probe", contract=contract, allow_mock_fallback=False
    )
    res = verifier._run_gate2_formal_sby(runner, [ws / "vacuity_probe.sv"], ws)
    assert res["passed"] is False
    assert res["error_category"] == "VACUOUS_PROPERTY"
    assert res["vacuity"]["status"] == "VACUOUS"


@pytest.mark.eda
@pytest.mark.eda_tools("sby")
def test_reached_antecedent_passes_gate2(tmp_path: Path) -> None:
    _needs_bwrap_sby()
    from mind3.benchmarks.runner import contract_from_benchmark_record

    rec = {
        "task_id": "reach_probe",
        "expected_ports": [
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst_n", "direction": "input", "width": 1},
            {"name": "q", "direction": "output", "width": 1},
        ],
        "sva_properties": [],
        "expected_properties": [
            "assert property (@(posedge clk) disable iff (!rst_n)"
            " (q == 1'b0) |=> (q == 1'b0 || q == 1'b1));"
        ],
        "verification_requirements": [],
    }
    contract = contract_from_benchmark_record(rec)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "reach_probe.sv").write_text(
        "module reach_probe (input clk, input rst_n, output q);\n"
        " reg r;\n"
        " always @(posedge clk or negedge rst_n) begin"
        " if (!rst_n) r <= 0; else r <= ~r; end\n"
        " assign q = r;\nendmodule\n"
    )
    runner = LocalBwrapRunner(ws, sandbox=None, allow_unsandboxed=True)
    verifier = SiliconSignoffVerifier(
        top_module="reach_probe", contract=contract, allow_mock_fallback=False
    )
    res = verifier._run_gate2_formal_sby(runner, [ws / "reach_probe.sv"], ws)
    assert res["passed"] is True, res.get("details")
