"""Regression: Gate 4 never passes vacuous zero-path timing.

A. "No paths found" + wns 0.00 -> TIMING_NO_PATHS, not PASS.
B. Real path blocks + positive WNS -> PASS.
C. Real path blocks + negative slack (VIOLATED) -> TIMING_SLACK_VIOLATION.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from mind3.core.verifier import SiliconSignoffVerifier

ZERO_PATH_LOG = """OpenSTA 2.3.1 4f13a213e1 Copyright (c) 2021, Parallax Software, Inc.
No paths found.
wns 0.00
"""

MET_PATH_LOG = """Startpoint: f_s0_b0 (rising edge-triggered flip-flop clocked by clk)
Endpoint: f_s1_b0 (rising edge-triggered flip-flop clocked by clk)
Path Group: clk
Path Type: max
  Delay    Time   Description
---------------------------------------------------------
   0.00    0.00   clock clk (rise edge)
   0.27    0.27 v f_s0_b0/Q (sky130_fd_sc_hd__dfxtp_1)
           0.27   data arrival time
  -0.11   -0.11   library setup time
          -0.11   data required time
---------------------------------------------------------
          -0.11   data required time
          -0.27   data arrival time
---------------------------------------------------------
           0.16   slack (MET)
wns 0.16
"""

VIOLATED_PATH_LOG = MET_PATH_LOG.replace("0.16   slack (MET)", "-0.38   slack (VIOLATED)").replace(
    "wns 0.16", "wns -0.38"
)


class _MockRunner:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self._stdout = stdout
        self._returncode = returncode

    def run(self, cmd, timeout_sec: int = 30):
        return SimpleNamespace(returncode=self._returncode, stdout=self._stdout, stderr="")


def _run_gate4(stdout: str, returncode: int = 0) -> dict:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "top.sv").write_text("module top(input clk, input a, output y); assign y = a; endmodule\n")
        (ws / "top.sdc").write_text("create_clock -name clk -period 10.0 [get_ports clk]\n")
        verifier = SiliconSignoffVerifier(
            top_module="top", liberty_path=["/x/y.lib"], allow_mock_fallback=False
        )
        return verifier._run_gate4_timing(_MockRunner(stdout, returncode), [ws / "top.sv"], ws)


def test_zero_paths_never_pass() -> None:
    result = _run_gate4(ZERO_PATH_LOG)
    assert result["passed"] is False
    assert result["error_category"] == "TIMING_NO_PATHS"
    assert result.get("vacuous") is True


def test_real_paths_positive_wns_pass() -> None:
    result = _run_gate4(MET_PATH_LOG)
    assert result["passed"] is True
    assert result.get("error_category") is None


def test_real_paths_negative_slack_fail() -> None:
    result = _run_gate4(VIOLATED_PATH_LOG)
    assert result["passed"] is False
    assert result["error_category"] == "TIMING_SLACK_VIOLATION"
