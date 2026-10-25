"""Repair-time synthesis invariants (MIND3_REPAIR_INVARIANTS, default OFF)."""

from __future__ import annotations

from mind3.core.contracts import (
    RTLGenerator,
    VerificationFailureEvidence,
    VerificationRepairer,
    contract_from_benchmark_record,
    repair_invariants_enabled,
)

RTL = "module arbiter_02 (input logic clk, input logic rst_n, input logic [3:0] req, output logic [3:0] gnt);\nendmodule\n"


def _contract(*, reset_line: str = "clk rising edge; active-low synchronous rst_n"):
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
            "clock_reset_assumptions": reset_line,
            "functional_requirements": ["4-client fixed priority arbiter"],
            "expected_properties": ["assert property (@(posedge clk) $onehot0(gnt));"],
            "verification_requirements": [],
            "parameters": {},
        }
    )


def _evidence():
    return VerificationFailureEvidence(gate="Gate 1", category="CLOCK_RESET_ERROR", error="async reset found")


def test_flag_defaults_off(monkeypatch) -> None:
    monkeypatch.delenv("MIND3_REPAIR_INVARIANTS", raising=False)
    assert repair_invariants_enabled() is False
    monkeypatch.setenv("MIND3_REPAIR_INVARIANTS", "1")
    assert repair_invariants_enabled() is True


def test_off_prompts_unchanged(monkeypatch) -> None:
    monkeypatch.delenv("MIND3_REPAIR_INVARIANTS", raising=False)
    prompt = VerificationRepairer.build_prompt(_contract(), RTL, _evidence())
    regen = VerificationRepairer.build_regeneration_prompt(_contract(), _evidence())
    assert "Synthesis invariants for the corrected module" not in prompt["system"]
    assert "Synthesis invariants for the corrected module" not in regen["system"]


def test_on_restates_sync_reset_and_widths(monkeypatch) -> None:
    monkeypatch.setenv("MIND3_REPAIR_INVARIANTS", "1")
    prompt = VerificationRepairer.build_prompt(_contract(), RTL, _evidence())
    system = prompt["system"]
    assert "Synthesis invariants for the corrected module" in system
    assert "SYNCHRONOUS" in system
    assert "Never place `rst_n` in the sensitivity list" in system
    assert "every literal or expression" in system
    assert "req: 4 bits (declare [3:0])" in system


def test_on_async_contract_requests_async_edge(monkeypatch) -> None:
    monkeypatch.setenv("MIND3_REPAIR_INVARIANTS", "1")
    contract = _contract(reset_line="clk rising edge; active-low asynchronous rst_n")
    system = VerificationRepairer.build_prompt(contract, RTL, _evidence())["system"]
    assert "ASYNCHRONOUS" in system
    assert "or negedge rst_n" in system


def test_on_does_not_alter_generation_prompt(monkeypatch) -> None:
    contract = _contract()
    monkeypatch.delenv("MIND3_REPAIR_INVARIANTS", raising=False)
    baseline = RTLGenerator.build_prompt(contract)
    monkeypatch.setenv("MIND3_REPAIR_INVARIANTS", "1")
    assert RTLGenerator.build_prompt(contract) == baseline


def test_on_regeneration_prompt_also_carries_invariants(monkeypatch) -> None:
    monkeypatch.setenv("MIND3_REPAIR_INVARIANTS", "1")
    regen = VerificationRepairer.build_regeneration_prompt(_contract(), _evidence())
    assert "Synthesis invariants for the corrected module" in regen["system"]
    assert RTL not in regen["user"]
