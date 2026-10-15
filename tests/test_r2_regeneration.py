"""R2 anti-anchoring regeneration mode (MIND3_REPAIR_MODE=r2, default r1).

Mocked only, no EDA/Ollama: the failing RTL must never appear in an R2
prompt; R2 candidates parse as fresh full modules; the minimal-patch budget
does not apply to regenerations; R1 default prompts are byte-identical to the
pre-R2 builder output.
"""

from __future__ import annotations

import pytest

from mind3.core.contracts import (
    VerificationFailureEvidence,
    VerificationRepairer,
    contract_from_benchmark_record,
)
from mind3.core.driver import (
    ModelResponseParseError,
    _parse_model_code_response,
    _repair_mode,
)

FAILING_RTL = (
    "module arbiter_02 (\n"
    "  input  logic clk,\n"
    "  input  logic rst_n,\n"
    "  input  logic [3:0] req,\n"
    "  output logic [3:0] gnt\n"
    ");\n"
    "  always_ff @(posedge clk or negedge rst_n) begin\n"
    "    if (!rst_n) gnt <= 4'b0;\n"
    "    else gnt <= req;\n"
    "  end\n"
    "endmodule\n"
)

FRESH_RTL = (
    "module arbiter_02 (\n"
    "  input  logic clk,\n"
    "  input  logic rst_n,\n"
    "  input  logic [3:0] req,\n"
    "  output logic [3:0] gnt\n"
    ");\n"
    "  assign gnt[0] = req[0];\n"
    "  assign gnt[1] = req[1] & ~req[0];\n"
    "  assign gnt[2] = req[2] & ~req[1] & ~req[0];\n"
    "  assign gnt[3] = req[3] & ~req[2] & ~req[1] & ~req[0];\n"
    "endmodule\n"
)


def _contract():
    return contract_from_benchmark_record(
        {
            "task_id": "arbiter_02",
            "natural_language_spec": "4-client fixed priority arbiter",
            "expected_ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "req", "direction": "input", "width": 4},
                {"name": "gnt", "direction": "output", "width": 4},
            ],
            "clock_reset_assumptions": "clk rising edge; active-low synchronous rst_n",
            "functional_requirements": ["4-client fixed priority arbiter"],
            "expected_properties": [
                "assert property (@(posedge clk) req[0] |-> gnt[0]);",
                "assert property (@(posedge clk) $onehot0(gnt));",
            ],
            "verification_requirements": [],
            "parameters": {},
        }
    )


def _evidence():
    return VerificationFailureEvidence(
        gate="Gate 1: Yosys Elaboration & Latch Trap",
        category="CLOCK_RESET_ERROR",
        error="Synchronous reset must not appear in the clocked sensitivity list.",
    )


def test_repair_mode_defaults_r1(monkeypatch) -> None:
    monkeypatch.delenv("MIND3_REPAIR_MODE", raising=False)
    assert _repair_mode() == "r1"
    monkeypatch.setenv("MIND3_REPAIR_MODE", "r2")
    assert _repair_mode() == "r2"
    monkeypatch.setenv("MIND3_REPAIR_MODE", "bogus")
    assert _repair_mode() == "r1"


def test_r1_prompt_shows_failing_code() -> None:
    prompt = VerificationRepairer.build_prompt(_contract(), FAILING_RTL, _evidence())
    assert FAILING_RTL in prompt["user"]


def test_r2_prompt_withholds_failing_code() -> None:
    prompt = VerificationRepairer.build_regeneration_prompt(_contract(), _evidence())
    assert FAILING_RTL not in prompt["user"]
    assert FAILING_RTL not in prompt["system"]
    assert "arbiter_02" in prompt["user"]  # contract present
    assert "CLOCK_RESET_ERROR" in prompt["user"]  # evidence present


def test_r2_parses_fresh_module_without_base() -> None:
    parsed = _parse_model_code_response(FRESH_RTL, default_module_name="arbiter_02", base_code=None)
    assert "assign gnt[0]" in parsed


def test_r2_rejects_patch_without_base() -> None:
    patch = '{"action": "patch", "path": "arbiter_02.sv", "content": "x"}'
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(patch, default_module_name="arbiter_02", base_code=None)


def test_r2_loop_withholds_code_and_records_mode(monkeypatch, tmp_path) -> None:
    """Loop-level: under R2 the model never sees the failing RTL, the mode is
    traced, and the loop still terminates bounded with full verification."""
    from pathlib import Path as _Path  # noqa: F401 (explicitness)

    from mind3.core.driver import PhaseDriver
    from mind3.core.types import PhaseEnum
    from mind3.core.verifier import SiliconSignoffVerifier

    monkeypatch.setenv("MIND3_REPAIR_MODE", "r2")
    ws = tmp_path / "ws"
    ws.mkdir()
    contract = _contract()
    verifier = SiliconSignoffVerifier(top_module="arbiter_02", contract=contract)
    driver = PhaseDriver(
        session_id="r2-loop-test",
        workspace=ws,
        verifier=verifier,
        max_repairs=3,
        model="qwen2.5-coder:7b",
        provider="ollama",
    )
    calls: list[str] = []

    def fake_query(messages, **kwargs):
        # Record every user prompt; always return the same failing RTL so the
        # loop exercises R2 turns and terminates on budgets.
        users = [m.get("content", "") for m in messages if m.get("role") == "user"]
        calls.extend(users)
        return FAILING_RTL

    monkeypatch.setattr(driver, "_query_model", fake_query)
    try:
        ok = driver.run_silicon_pipeline("build arbiter", contract_override=contract)
    finally:
        driver.close()
    assert ok is False
    model_calls = [r for r in driver.transcript if r.phase == PhaseEnum.MODEL_CALL]
    repair_calls = [r for r in model_calls if "Repair Engineer" in str(r.event.payload.get("role", ""))]
    assert repair_calls, "expected repair MODEL_CALL traces"
    for rec in repair_calls:
        assert FAILING_RTL not in str(rec.event.payload.get("guidance", ""))
        assert rec.event.payload.get("repair_mode") == "r2"
    finishes = [r for r in driver.transcript if r.phase == PhaseEnum.REPAIR_OR_FINISH]
    assert finishes and finishes[-1].event.payload.get("status") in {"ROLLED_BACK", "ABORTED_NON_REPAIRABLE"}
