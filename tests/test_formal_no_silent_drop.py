"""No property may disappear silently from the formal harness.

Regression for a real defect: when a contract carried both structured and
legacy properties, ``compile_contract_properties`` returned after the
structured ones and dropped every legacy property without audit. On
``counter_04`` that removed the only non-trivial invariant (a Johnson-rotation
``$past`` comparison), leaving a reset-only check that a dead counter passes.
"""

from __future__ import annotations

from mind3.core.contracts import (
    VerificationHarnessGenerator,
    contract_from_benchmark_record,
)
from mind3.core.formal_templates import (
    UnsupportedFormalTemplate,
    compile_contract_properties,
)


def _record(task_id: str, properties: list[str]) -> dict:
    return {
        "task_id": task_id,
        "natural_language_spec": "8-bit twisted-ring Johnson counter",
        "expected_ports": [
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst_n", "direction": "input", "width": 1},
            {"name": "q", "direction": "output", "width": 8},
        ],
        "clock_reset_assumptions": "clk rising edge; active-low synchronous rst_n",
        "functional_requirements": ["johnson counter"],
        "expected_properties": properties,
        "verification_requirements": [],
        "parameters": {},
    }


def test_mixed_structured_and_unsupported_legacy_fails_closed() -> None:
    contract = contract_from_benchmark_record(
        _record(
            "counter_04",
            [
                "assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> q == 8'h00);",
                "assert property (@(posedge clk) disable iff (!rst_n) q[7:1] == $past(q[6:0]));",
            ],
        )
    )
    assert contract.formal_properties and contract.sva_properties
    try:
        compile_contract_properties(
            structured=contract.formal_properties,
            legacy=contract.sva_properties,
            default_clock="clk",
            default_reset="rst_n:active_low",
            reset_synchronous=True,
        )
    except UnsupportedFormalTemplate as exc:
        assert "contract_property_2" in str(exc)
    else:  # pragma: no cover - the defect this test exists to prevent
        raise AssertionError("unsupported legacy property was silently dropped")


def test_mixed_supported_legacy_is_compiled_too() -> None:
    contract = contract_from_benchmark_record(
        _record(
            "mixed_supported",
            [
                "assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> q == 8'h00);",
                "assert property (@(posedge clk) disable iff (!rst_n) !(q == 8'hFF));",
            ],
        )
    )
    text, audit = compile_contract_properties(
        structured=contract.formal_properties,
        legacy=contract.sva_properties,
        default_clock="clk",
        default_reset="rst_n:active_low",
        reset_synchronous=True,
    )
    names = {item["name"] for item in audit if item.get("supported")}
    assert {"contract_property_1", "contract_property_2"} <= names
    assert text.count("assert (") == 2


def test_bind_module_raises_for_unverifiable_contract_property() -> None:
    contract = contract_from_benchmark_record(
        _record(
            "counter_04",
            [
                "assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> q == 8'h00);",
                "assert property (@(posedge clk) disable iff (!rst_n) q[7:1] == $past(q[6:0]));",
            ],
        )
    )
    try:
        VerificationHarnessGenerator.build_sva_bind_module(contract)
    except UnsupportedFormalTemplate:
        return
    raise AssertionError("harness builder must not emit a checker that omits a declared property")


def test_structured_only_contract_still_compiles() -> None:
    contract = contract_from_benchmark_record(
        _record(
            "structured_only",
            [
                "assert property (@(posedge clk) disable iff (!rst_n) !(q == 8'hFF));",
            ],
        )
    )
    text, audit = compile_contract_properties(
        structured=contract.formal_properties,
        legacy=contract.sva_properties,
        default_clock="clk",
        default_reset="rst_n:active_low",
        reset_synchronous=True,
    )
    assert text.count("assert (") == 1
    assert all(item.get("supported") for item in audit)
