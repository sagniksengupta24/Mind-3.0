"""Gate 1 liberty handling: a missing Liberty library is an environment
failure, never a synthesis/elaboration defect.

Regression for the head-baseline misattribution where a relative
--liberty path that does not resolve from the task workspace made Yosys
fail with "not found or is a directory" and the outcome was recorded as
SYNTHESIS_ELABORATION_ERROR (an RTL defect) instead of ENVIRONMENT_FAILURE.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mind3.core.verifier import SiliconSignoffVerifier

CLEAN_RTL = """\
module env_probe (
  input  logic clk,
  input  logic rst_n,
  output logic [7:0] q
);
  always_ff @(posedge clk) begin
    if (!rst_n)
      q <= 8'h00;
    else
      q <= q + 8'h01;
  end
endmodule
"""

YOSYS_MISSING_LIB = """\
1. Executing Liberty frontend.
ERROR: File `nonexistent/sky130.lib' not found or is a directory
"""


class _ScriptedRunner:
    """Fake EDA runner: iverilog passes, yosys fails on the missing liberty."""

    def __init__(self, ws: Path) -> None:
        self.ws = ws
        self.calls: list[list[str]] = []

    def run(self, cmd: list[str], timeout_sec: int = 60) -> SimpleNamespace:
        self.calls.append(list(cmd))
        if cmd[0] == "iverilog":
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        assert cmd[0] == "yosys"
        return SimpleNamespace(stdout="", stderr=YOSYS_MISSING_LIB, returncode=1)


def test_missing_liberty_reports_environment_failure(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "env_probe.sv").write_text(CLEAN_RTL, encoding="utf-8")
    verifier = SiliconSignoffVerifier(
        top_module="env_probe",
        contract=None,
        liberty_path="nonexistent/sky130.lib",
        allow_mock_fallback=False,
    )
    res = verifier._run_gate1_yosys(_ScriptedRunner(ws), [ws / "env_probe.sv"], ws)
    assert res["passed"] is False
    assert res["error_category"] == "ENVIRONMENT_FAILURE"
    assert "liberty" in str(res.get("details", "")).lower()


def test_genuine_yosys_failure_keeps_elaboration_category(tmp_path: Path) -> None:
    """A Yosys failure with no missing-library signature must keep its
    elaboration category (no overcorrection)."""

    class _ElabFailRunner(_ScriptedRunner):
        def run(self, cmd: list[str], timeout_sec: int = 60) -> SimpleNamespace:
            self.calls.append(list(cmd))
            if cmd[0] == "iverilog":
                return SimpleNamespace(stdout="", stderr="", returncode=0)
            return SimpleNamespace(
                stdout="", stderr="ERROR: syntax error, unexpected $end", returncode=1
            )

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "env_probe.sv").write_text(CLEAN_RTL, encoding="utf-8")
    verifier = SiliconSignoffVerifier(
        top_module="env_probe",
        contract=None,
        liberty_path="nonexistent/sky130.lib",
        allow_mock_fallback=False,
    )
    res = verifier._run_gate1_yosys(_ElabFailRunner(ws), [ws / "env_probe.sv"], ws)
    assert res["passed"] is False
    assert res["error_category"] == "SYNTHESIS_ELABORATION_ERROR"
