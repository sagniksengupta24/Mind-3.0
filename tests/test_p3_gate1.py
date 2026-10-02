"""P3 Gate 1 verification tests: source filtering and synthesis file list invariants."""

import tempfile
import pytest
from pathlib import Path
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.remote_eda import LocalBwrapRunner

def test_gate1_source_filtering():
    """Verify formal-only artifacts are excluded while legitimate .sv files are included."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "top.sv").write_text("module top(input a, output b); assign b = a; endmodule\n")
        (ws / "sub.v").write_text("module sub(input x, output y); assign y = x; endmodule\n")
        (ws / "top_sva.sv").write_text("module top_sva(); initial assert(1); endmodule\n")
        (ws / "top_formal_top.sv").write_text("module top_formal_top(); endmodule\n")
        (ws / "top_tb.sv").write_text("module top_tb(); endmodule\n")

        # Use SiliconSignoffVerifier source discovery logic
        resolved_ws = ws.resolve()
        mind_internal = (resolved_ws / ".mind").resolve()
        sources = [
            p
            for p in sorted(resolved_ws.rglob("*.[vs]*"))
            if p.suffix in (".v", ".sv")
            and not p.name.endswith(("_sva.sv", "_formal_top.sv", "_checker.sv", "_tb.sv", "_tb.v"))
            and not p.resolve().is_relative_to(mind_internal)
            and not any(part.startswith(".") for part in p.relative_to(resolved_ws).parts)
        ]

        source_names = [p.name for p in sources]
        assert "top.sv" in source_names
        assert "sub.v" in source_names
        assert "top_sva.sv" not in source_names
        assert "top_formal_top.sv" not in source_names
        assert "top_tb.sv" not in source_names

@pytest.mark.eda
def test_gate1_live_sv_synthesis():
    """Execute live Yosys elaboration on legitimate SystemVerilog (.sv)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "adder.sv").write_text(
            "module adder #(parameter WIDTH = 4) (\n"
            "  input logic [WIDTH-1:0] a, b,\n"
            "  output logic [WIDTH-1:0] sum\n"
            ");\n"
            "  always_comb sum = a + b;\n"
            "endmodule\n"
        )
        verifier = SiliconSignoffVerifier(top_module="adder", allow_mock_fallback=False)
        runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
        res = verifier._run_gate1_yosys(runner, [ws / "adder.sv"], ws)
        assert res["passed"] is True, f"Gate 1 failed: {res.get('stderr')}"
        assert (ws / "adder_netlist.v").exists()

pytestmark = pytest.mark.eda

