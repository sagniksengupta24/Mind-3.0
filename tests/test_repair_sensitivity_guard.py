"""Sync-reset sensitivity guard (flag-gated MIND3_EVIDENCE_V2, default OFF).

Models reflexively emit `always_ff @(posedge clk or negedge rst_n)` on
seeing `rst_n`, even for synchronous-reset contracts. The guard injects the
exact required header into generation/repair prompts and rejects mismatched
candidates pre-EDA with the header in the feedback.
"""

import pytest

from mind3.core.contracts import (
    ClockContract,
    InterfaceContract,
    PortDefinition,
    PortDirection,
    ResetContract,
    RTLGenerator,
    VerificationFailureEvidence,
    VerificationRepairer,
)
from mind3.core.vcd_evidence import (
    required_sensitivity_header,
    sensitivity_guard_block,
    sensitivity_mismatch,
)

SYNC_RTL = """module m(input logic clk, input logic rst_n, output logic q);
  always_ff @(posedge clk) begin
    if (!rst_n) q <= 1'b0;
    else q <= 1'b1;
  end
endmodule
"""

ASYNC_RTL = """module m(input logic clk, input logic rst_n, output logic q);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 1'b0;
    else q <= 1'b1;
  end
endmodule
"""


def _sync_contract() -> InterfaceContract:
    return InterfaceContract(
        module_name="m",
        functional_spec="s",
        ports=[
            PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="q", direction=PortDirection.OUTPUT, width=1),
        ],
        clock=ClockContract(name="clk", edge="posedge"),
        reset=ResetContract(name="rst_n", polarity="active_low", synchronous=True),
    )


def _async_contract() -> InterfaceContract:
    contract = _sync_contract()
    object.__setattr__(
        contract, "reset",
        ResetContract(name="rst_n", polarity="active_low", synchronous=False),
    )
    return contract


def test_required_header_sync() -> None:
    assert required_sensitivity_header(_sync_contract()) == "always_ff @(posedge clk)"


def test_required_header_async() -> None:
    assert (
        required_sensitivity_header(_async_contract())
        == "always_ff @(posedge clk or negedge rst_n)"
    )


def test_mismatch_sync_contract() -> None:
    hit = sensitivity_mismatch(ASYNC_RTL, _sync_contract())
    assert hit is not None
    assert hit["direction"] == "async-in-sync"
    assert hit["required"] == "always_ff @(posedge clk)"
    assert sensitivity_mismatch(SYNC_RTL, _sync_contract()) is None


def test_mismatch_async_contract() -> None:
    hit = sensitivity_mismatch(SYNC_RTL, _async_contract())
    assert hit is not None
    assert hit["direction"] == "sync-in-async"
    assert hit["required"] == "always_ff @(posedge clk or negedge rst_n)"
    assert sensitivity_mismatch(ASYNC_RTL, _async_contract()) is None


def test_mismatch_ignores_comments_and_neutral() -> None:
    commented = ASYNC_RTL.replace("or negedge rst_n", "// or negedge rst_n")
    assert sensitivity_mismatch(commented, _sync_contract()) is None
    no_reset = InterfaceContract(
        module_name="m",
        functional_spec="s",
        ports=[PortDefinition(name="clk", direction=PortDirection.INPUT, width=1)],
    )
    assert sensitivity_mismatch(ASYNC_RTL, no_reset) is None


def test_generation_prompt_flag_off_identical() -> None:
    contract = _sync_contract()
    assert RTLGenerator.build_prompt(contract) == RTLGenerator.build_prompt(
        contract, sensitivity_guard=False
    )


def test_generation_prompt_flag_on_has_header() -> None:
    prompt = RTLGenerator.build_prompt(_sync_contract(), sensitivity_guard=True)
    assert "always_ff @(posedge clk)" in prompt["system"]
    assert "or negedge" in prompt["system"]


def test_repair_prompt_flag_on_has_header() -> None:
    evidence = VerificationFailureEvidence(gate="g", category="c")
    prompt = VerificationRepairer.build_prompt(
        _sync_contract(), "module m(); endmodule", evidence, evidence_v2=True
    )
    assert "always_ff @(posedge clk)" in prompt["system"]


def test_sensitivity_guard_block_none_without_clock() -> None:
    contract = InterfaceContract(
        module_name="m",
        functional_spec="s",
        ports=[PortDefinition(name="q", direction=PortDirection.OUTPUT, width=1)],
    )
    assert sensitivity_guard_block(contract) is None


def test_sensitivity_mismatch_rejected_pre_eda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An async-sensitivity repair is rejected without rerunning the verifier."""
    import json
    import tempfile
    from pathlib import Path
    from typing import Any

    from test_mind3 import MockSandbox

    from mind3.core.driver import PhaseDriver
    from mind3.core.types import PhaseEnum, VerificationDomain, VerificationResult
    from mind3.core.verifier import SiliconSignoffVerifier

    monkeypatch.setenv("MIND3_EVIDENCE_V2", "1")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        class FailOnceVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="m", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                if self.calls == 1:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="Latch inferred in m",
                        error_category="LATCH_INFERRED",
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    silicon_verified=True,
                )

        verifier = FailOnceVerifier()
        driver = PhaseDriver(
            session_id="sensitivity-repair-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps(
            {
                "module_name": "m",
                "functional_spec": "s",
                "ports": [
                    {"name": "clk", "direction": "input", "width": 1},
                    {"name": "rst_n", "direction": "input", "width": 1},
                    {"name": "q", "direction": "output", "width": 1},
                ],
                "sva_properties": [],
                "timing": {"clock_name": "clk", "period_ns": 5.0},
                "reset": {
                    "name": "rst_n",
                    "polarity": "active_low",
                    "synchronous": True,
                },
            }
        )
        query_count = 0
        feedbacks: list[str] = []

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return contract_json
            if query_count == 2:
                return SYNC_RTL
            if query_count == 3:
                return ASYNC_RTL
            feedbacks.append(messages[-1]["content"])
            return SYNC_RTL

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize m") is True
        assert verifier.calls == 2, "mismatched candidate must not rerun the verifier"
        assert any(
            record.phase == PhaseEnum.VERIFY
            and record.event.payload.get("error_category") == "REPAIR_SENSITIVITY_MISMATCH"
            for record in driver.transcript
        )
        assert feedbacks and "always_ff @(posedge clk)" in feedbacks[0]


COMBINATIONAL_ASSIGN = """module m(input logic clk, input logic rst_n, input logic [3:0] req, output logic [3:0] gnt);
  assign gnt[0] = req[0];
  assign gnt[1] = req[1] & ~req[0];
  assign gnt[2] = req[2] & ~req[1] & ~req[0];
  assign gnt[3] = req[3] & ~req[2] & ~req[1] & ~req[0];
endmodule
"""

COMBINATIONAL_ALWAYS_COMB = """module m(input logic clk, input logic rst_n, input logic [3:0] req, output logic [3:0] gnt);
  always_comb begin
    gnt[0] = req[0];
    gnt[1] = req[1] & ~req[0];
    gnt[2] = req[2] & ~req[1] & ~req[0];
    gnt[3] = req[3] & ~req[2] & ~req[1] & ~req[0];
  end
endmodule
"""


def test_combinational_designs_pass_sensitivity() -> None:
    """Zero always_ff blocks means zero clocked sensitivity lists: purely
    combinational outputs (assign / always_comb) are neutral under a sync
    contract. Under an async contract the missing reset edge mirrors the
    Gate-1 requirement exactly (flagged, same as the gate)."""
    from mind3.core.vcd_evidence import sensitivity_mismatch

    assert sensitivity_mismatch(COMBINATIONAL_ASSIGN, _sync_contract()) is None
    assert sensitivity_mismatch(COMBINATIONAL_ALWAYS_COMB, _sync_contract()) is None
    hit = sensitivity_mismatch(COMBINATIONAL_ASSIGN, _async_contract())
    assert hit is not None
    assert hit["direction"] == "sync-in-async"
