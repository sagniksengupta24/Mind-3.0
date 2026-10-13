"""D3 regression: a formal/sim failure must stay labeled and budgeted as
formal/sim across repair iterations (snapshot hardcodes "compile")."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from test_mind3 import MockSandbox

from mind3.core.driver import PhaseDriver
from mind3.core.types import PhaseEnum, VerificationDomain, VerificationResult
from mind3.core.verifier import SiliconSignoffVerifier


def test_formal_stage_preserved_across_repairs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Formal failures must remain labeled/formally budgeted on subsequent repair calls."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        class FailFormalTwiceVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="formal_reg", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                if self.calls <= 2:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="BMC assertion failed at step 2",
                        error_category="FORMAL_INVARIANT_BREACH",
                        gate_reports=[{
                            "gate": "Gate 2: Formal Verification",
                            "failing_property": "data_updates_when_enabled",
                            "details": "Assertion failed at step 2",
                            "step": 2,
                        }],
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    silicon_verified=True,
                )

        verifier = FailFormalTwiceVerifier()
        driver = PhaseDriver(
            session_id="formal-stage-budget-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps({
            "module_name": "formal_reg",
            "functional_spec": "An enabled register must capture d when enabled.",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"},
                {"name": "en", "direction": "input", "width": 1, "description": "Enable"},
                {"name": "d", "direction": "input", "width": 8, "description": "Data input"},
                {"name": "q", "direction": "output", "width": 8, "description": "Registered output"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })
        candidates = [
            "module formal_reg(input clk, input rst_n, input en, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else if (en) q <= q;\nendmodule",
            "module formal_reg(input clk, input rst_n, input en, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else if (en) q <= d;\nendmodule",
            "module formal_reg(input clk, input rst_n, input en, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else q <= en ? d : q;\nendmodule",
        ]
        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return contract_json
            return candidates[min(query_count - 2, len(candidates) - 1)]

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize formal_reg", liberty_path="sky130.lib") is True
        repair_calls = [
            record.event.payload
            for record in driver.transcript
            if record.phase == PhaseEnum.MODEL_CALL
            and record.event.payload.get("role") == "Independent RTL Verification Repair Engineer"
        ]
        assert len(repair_calls) == 2
        assert [call.get("stage") for call in repair_calls] == ["formal", "formal"]
        assert driver._stage_repair_attempts["formal"] == 2
