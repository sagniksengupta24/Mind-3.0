"""Regression: write_file normalizes trailing newline (Verilator -Wall EOFNEWLINE).

Model RTL parsed from strict/fenced/raw paths is stripped of trailing
whitespace. Written verbatim, the file then trips Verilator
``%Warning-EOFNEWLINE`` which ``-Wall`` escalates to a fatal build error
(``COVERAGE_BUILD_FAILURE``) even when the RTL itself is fine.
_execute_action must ensure POSIX trailing newline on write.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from mind3.core.driver import PhaseDriver
from mind3.core.types import WriteFileAction
from mind3.core.verifier import (
    BaseVerifier,
    VerificationDomain,
    VerificationResult,
)
from sandbox_stub import StubSandbox


class _MockVerifier(BaseVerifier):
    def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
        return VerificationResult(
            passed=True,
            domain=VerificationDomain.SOFTWARE,
            exit_code=0,
            stdout="ok",
            stderr="",
            failure_reason=None,
        )


def _driver(ws: Path) -> PhaseDriver:
    return PhaseDriver(
        session_id="newline-test",
        workspace=ws,
        verifier=_MockVerifier(),
        max_repairs=1,
        sandbox=StubSandbox(),
    )


def test_write_file_appends_missing_trailing_newline() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        driver = _driver(ws)
        try:
            driver._execute_action(
                WriteFileAction(path="dut.sv", content="module dut(input logic clk); endmodule")
            )
            assert (ws / "dut.sv").read_text(encoding="utf-8").endswith("\n")
        finally:
            driver.close()


def test_write_file_does_not_double_newline() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        driver = _driver(ws)
        try:
            driver._execute_action(
                WriteFileAction(path="dut.sv", content="module dut(input logic clk); endmodule\n")
            )
            assert (ws / "dut.sv").read_text(encoding="utf-8") == (
                "module dut(input logic clk); endmodule\n"
            )
        finally:
            driver.close()
