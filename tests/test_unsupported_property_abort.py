"""An unverifiable contract property must abort, not masquerade as SYNTAX_ERROR."""

from __future__ import annotations

from mind3.core.contracts import contract_from_benchmark_record
from mind3.core.driver import PhaseDriver
from mind3.core.types import PhaseEnum
from mind3.core.verifier import SiliconSignoffVerifier
from sandbox_stub import StubSandbox


def _contract():
    return contract_from_benchmark_record(
        {
            "task_id": "counter_04",
            "natural_language_spec": "8-bit twisted-ring Johnson counter",
            "expected_ports": [
                {"name": "clk", "direction": "input", "width": 1},
                {"name": "rst_n", "direction": "input", "width": 1},
                {"name": "q", "direction": "output", "width": 8},
            ],
            "clock_reset_assumptions": "clk rising edge; active-low synchronous rst_n",
            "functional_requirements": ["johnson counter"],
            "expected_properties": [
                "assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> q == 8'h00);",
                "assert property (@(posedge clk) disable iff (!rst_n) q[7:1] == $past(q[6:0]));",
            ],
            "verification_requirements": [],
            "parameters": {},
        }
    )


def test_unsupported_property_aborts_before_generation(tmp_path) -> None:
    contract = _contract()
    ws = tmp_path / "ws"
    ws.mkdir()
    driver = PhaseDriver(
        session_id="unsupported-prop",
        workspace=ws,
        verifier=SiliconSignoffVerifier(top_module="counter_04", contract=contract),
        max_repairs=3,
        model="qwen2.5-coder:7b",
        provider="ollama",
        sandbox=StubSandbox(),
    )
    calls: list[str] = []

    def fake_query(messages, **kwargs):
        calls.append("called")
        return "module counter_04; endmodule"

    driver._query_model = fake_query
    try:
        ok = driver.run_silicon_pipeline("build johnson counter", contract_override=contract)
    finally:
        driver.close()

    assert ok is False
    assert calls == [], "no model call may be spent on an unverifiable contract"
    verifies = [
        r.event.payload
        for r in driver.transcript
        if r.phase == PhaseEnum.VERIFY
        and (r.event.payload or {}).get("error_category") == "UNSUPPORTED_FORMAL_PROPERTY"
    ]
    assert verifies, "abort must be reported with the real category"
    assert "cannot verify" in str(verifies[0].get("failure_reason"))
    finishes = [r.event.payload for r in driver.transcript if r.phase == PhaseEnum.REPAIR_OR_FINISH]
    assert finishes[-1]["status"] == "ABORTED_NON_REPAIRABLE"
    assert finishes[-1]["error_category"] == "UNSUPPORTED_FORMAL_PROPERTY"
    assert not (ws / "counter_04_sva.sv").exists()
