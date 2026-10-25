"""A vacuous-only contract must abort with its real category, not crash the run.

The driver builds the formal harness before spending a model call. If every
declared property classifies as vacuous-by-text, ``compile_contract_properties``
raises ``NoGenuineProperty``. Before this regression test that exception escaped
the pipeline and the benchmark runner recorded the task as ``RUN_EXCEPTION`` /
``ENVIRONMENT_FAILURE`` -- a contract defect mislabeled as infrastructure.
"""

from __future__ import annotations

from mind3.core.contracts import (
    VerificationHarnessGenerator,
    contract_from_benchmark_record,
)
from mind3.core.driver import NON_REPAIRABLE_CATEGORIES, PhaseDriver
from mind3.core.failure_taxonomy import FailureCategory, classify_failure
from mind3.core.types import PhaseEnum
from mind3.core.verifier import SiliconSignoffVerifier


def _record(properties: list[str]) -> dict:
    return {
        "task_id": "stub_vacuous",
        "natural_language_spec": "8-bit passthrough register",
        "expected_ports": [
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst_n", "direction": "input", "width": 1},
            {"name": "out_data", "direction": "output", "width": 8},
        ],
        "clock_reset_assumptions": "clk rising edge; active-low synchronous rst_n",
        "functional_requirements": ["register out_data"],
        "expected_properties": properties,
        "verification_requirements": [],
        "parameters": {},
    }


def _vacuous_contract():
    return contract_from_benchmark_record(_record(
        ["assert property (@(posedge clk) disable iff (!rst_n) out_data == out_data);"]
    ))


def _mixed_contract():
    return contract_from_benchmark_record(_record([
        "assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> out_data == 0);",
        "assert property (@(posedge clk) disable iff (!rst_n) out_data == out_data);",
    ]))


def test_vacuous_only_contract_aborts_before_generation(tmp_path) -> None:
    contract = _vacuous_contract()
    ws = tmp_path / "ws"
    ws.mkdir()
    driver = PhaseDriver(
        session_id="vacuous-contract",
        workspace=ws,
        verifier=SiliconSignoffVerifier(top_module="stub_vacuous", contract=contract),
        max_repairs=3,
        model="qwen2.5-coder:7b",
        provider="ollama",
    )
    calls: list[str] = []

    def fake_query(messages, **kwargs):
        calls.append("called")
        return "module stub_vacuous; endmodule"

    driver._query_model = fake_query
    try:
        ok = driver.run_silicon_pipeline("build passthrough register", contract_override=contract)
    finally:
        driver.close()

    assert ok is False
    assert calls == [], "no model call may be spent on a vacuous-only contract"
    verifies = [
        r.event.payload
        for r in driver.transcript
        if r.phase == PhaseEnum.VERIFY
        and (r.event.payload or {}).get("error_category") == "NO_GENUINE_PROPERTY"
    ]
    assert verifies, "abort must be reported with the real category"
    assert "vacuous" in str(verifies[0].get("failure_reason")).lower()
    finishes = [r.event.payload for r in driver.transcript if r.phase == PhaseEnum.REPAIR_OR_FINISH]
    assert finishes[-1]["status"] == "ABORTED_NON_REPAIRABLE"
    assert finishes[-1]["error_category"] == "NO_GENUINE_PROPERTY"
    assert not (ws / "stub_vacuous_sva.sv").exists(), (
        "no harness may be written for a contract with no genuine property"
    )


def test_mixed_contract_keeps_genuine_property() -> None:
    """One genuine property is enough to verify; the tautology is audited away."""
    harness = VerificationHarnessGenerator.build_sva_bind_module(_mixed_contract())
    assert "out_data == 0" in harness, "the genuine reset property must be rendered"
    assert "property-audit: contract_property_2" in harness
    assert "kind=tautology" in harness


def test_no_genuine_property_is_non_repairable() -> None:
    assert "NO_GENUINE_PROPERTY" in NON_REPAIRABLE_CATEGORIES, (
        "repairing RTL cannot fix a vacuous contract"
    )


def test_no_genuine_property_classifies_as_specification_error() -> None:
    classified = classify_failure(
        error_category="NO_GENUINE_PROPERTY",
        failure_reason="Every specified property was dropped as vacuous-by-text.",
    )
    assert classified.canonical_category == FailureCategory.SPECIFICATION_ERROR
    assert classified.fine_grained_category == "NO_GENUINE_PROPERTY"
