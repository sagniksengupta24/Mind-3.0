"""Regression: generation prompt carries an exact, immutable interface signature.

The model systematically rendered 1-bit ports as ``[1:0]`` from the
"[1 bits]" pinout prose. The prompt now additionally shows the exact
SystemVerilog header. These tests lock the presentation without touching
validation: wrong widths must still fail Gate 1.
"""

from __future__ import annotations

import json

from mind3.benchmarks.runner import contract_from_benchmark_record
from mind3.core.contracts import (
    RTLGenerator,
    VerificationFailureEvidence,
    VerificationRepairer,
    module_signature_block,
    validate_rtl_against_contract,
)


def _counter01_contract():
    task = json.loads(open("benchmarks/heldout/tasks.jsonl", encoding="utf-8").readline())
    assert task["task_id"] == "counter_01"
    return contract_from_benchmark_record(task)


def test_prompt_contains_every_port_name() -> None:
    contract = _counter01_contract()
    user = RTLGenerator.build_prompt(contract)["user"]
    for port in contract.ports:
        assert port.name in user


def test_signature_renders_scalar_and_vector_widths() -> None:
    contract = _counter01_contract()
    user = RTLGenerator.build_prompt(contract)["user"]
    assert "module counter_01 (" in user
    assert "\n  input clk," in user or "\n  input clk\n" in user
    assert "output [7:0] count" in user
    assert "[1:0] clk" not in user


def test_prompt_prohibits_interface_mutation() -> None:
    contract = _counter01_contract()
    user = RTLGenerator.build_prompt(contract)["user"]
    assert "Do not add, remove, rename, reorder, or resize ports" in user


def test_validator_still_rejects_widened_scalar() -> None:
    contract = _counter01_contract()
    bad_rtl = (
        "module counter_01 (\n"
        "  input [1:0] clk,\n"
        "  input rst_n,\n"
        "  input up,\n"
        "  input down,\n"
        "  output [7:0] count\n"
        ");\n"
        "  always @(posedge clk or negedge rst_n) begin\n"
        "    if (!rst_n) count <= 8'h00;\n"
        "    else count <= count + 1'b1;\n"
        "  end\n"
        "endmodule\n"
    )
    violations = validate_rtl_against_contract(contract, bad_rtl)
    assert violations, "widened scalar port must fail structural validation"
    assert any(v["category"] == "TYPE_WIDTH_ERROR" for v in violations)


def test_validator_accepts_exact_signature() -> None:
    contract = _counter01_contract()
    good_rtl = (
        "module counter_01 (\n"
        "  input clk,\n"
        "  input rst_n,\n"
        "  input up,\n"
        "  input down,\n"
        "  output [7:0] count\n"
        ");\n"
        "  always @(posedge clk or negedge rst_n) begin\n"
        "    if (!rst_n) count <= 8'h00;\n"
        "    else count <= count + 1'b1;\n"
        "  end\n"
        "endmodule\n"
    )
    width_violations = [
        v for v in validate_rtl_against_contract(contract, good_rtl)
        if v["category"] in ("TYPE_WIDTH_ERROR", "INTERFACE_ERROR")
    ]
    assert width_violations == []


def test_repair_prompt_pins_exact_header_and_interface() -> None:
    contract = _counter01_contract()
    evidence = VerificationFailureEvidence(
        gate="Gate 1",
        category="TYPE_WIDTH_ERROR",
        error="Port 'clk' width is 2, expected 1.",
    )
    prompt = VerificationRepairer.build_prompt(
        contract,
        "module counter_01 ( input [1:0] clk ); endmodule",
        evidence,
    )
    assert "Do not change the module interface" in prompt["system"]
    assert module_signature_block(contract) in prompt["user"]
    assert "The repaired module header must still be exactly:" in prompt["user"]


def test_signature_helper_marks_scalars_and_vectors() -> None:
    contract = _counter01_contract()
    sig = module_signature_block(contract)
    assert sig.startswith("module counter_01 (")
    assert "  input clk," in sig
    assert "  output [7:0] count" in sig


def test_prompt_carries_behavioral_specification() -> None:
    contract = _counter01_contract()
    user = RTLGenerator.build_prompt(contract)["user"]
    assert contract.functional_spec in user
    assert "The module header must be exactly:" in user


def test_write_path_preserves_terminated_content_byte_identical(tmp_path) -> None:
    from mind3.core.driver import PhaseDriver
    from mind3.core.types import WriteFileAction

    class _StubVerifier:
        pass

    class _SandboxStub:
        pass

    ws = tmp_path / "ws"
    ws.mkdir()
    driver = PhaseDriver(session_id="nl", workspace=ws, verifier=_StubVerifier(), sandbox=_SandboxStub())  # type: ignore[arg-type]
    content = "module m;\nendmodule\n"
    rec = driver._execute_action(WriteFileAction(path="m.sv", content=content))
    assert (ws / "m.sv").read_text(encoding="utf-8") == content
    assert rec["bytes_written"] == len(content.encode("utf-8"))


def test_write_path_terminates_unterminated_file(tmp_path) -> None:
    from mind3.core.driver import PhaseDriver
    from mind3.core.types import WriteFileAction

    class _StubVerifier:
        pass

    class _SandboxStub:
        pass

    ws = tmp_path / "ws"
    ws.mkdir()
    driver = PhaseDriver(session_id="nl", workspace=ws, verifier=_StubVerifier(), sandbox=_SandboxStub())  # type: ignore[arg-type]
    rec = driver._execute_action(WriteFileAction(path="m.sv", content="module m;\nendmodule"))
    assert (ws / "m.sv").read_text(encoding="utf-8") == "module m;\nendmodule\n"
    assert rec["bytes_written"] == len("module m;\nendmodule\n".encode("utf-8"))


def test_sva_bind_assumes_reset_at_init() -> None:
    from mind3.core.contracts import VerificationHarnessGenerator

    contract = _counter01_contract()
    sva = VerificationHarnessGenerator.build_sva_bind_module(contract)
    assert "if (init) assume (!rst_n);" in sva


def test_sva_bind_assume_uses_active_high_polarity() -> None:
    from mind3.core.contracts import InterfaceContract, VerificationHarnessGenerator

    contract = InterfaceContract(
        module_name="rsthigh",
        functional_spec="active-high reset check",
        ports=[
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "rst", "direction": "input", "width": 1},
            {"name": "q", "direction": "output", "width": 1},
        ],
        clock={"name": "clk", "edge": "posedge"},
        reset={"name": "rst", "polarity": "active_high", "synchronous": False},
        timing={"clock_name": "clk", "period_ns": 10.0},
        formal_properties=[{
            "name": "p1", "kind": "boolean",
            "clock": "clk", "reset": "rst:active_high",
            "expression": "q == 0",
        }],
    )
    sva = VerificationHarnessGenerator.build_sva_bind_module(contract)
    assert "if (init) assume (rst);" in sva


def test_numeric_facts_render_widths_and_bounds() -> None:
    from mind3.core.contracts import numeric_facts_block

    contract = _counter01_contract()
    block = numeric_facts_block(contract)
    assert "clk" in block and "width 1 (scalar, no range)" in block
    assert "count" in block and "unsigned range 0..255" in block
    assert "rst_n" in block


def test_numeric_facts_signed_formula_scales_with_width() -> None:
    from mind3.core.contracts import InterfaceContract, numeric_facts_block

    contract = InterfaceContract(
        module_name="w4",
        functional_spec="x",
        ports=[
            {"name": "clk", "direction": "input", "width": 1},
            {"name": "v", "direction": "output", "width": 4},
        ],
        timing={"clock_name": "clk", "period_ns": 10.0},
    )
    block = numeric_facts_block(contract)
    assert "unsigned range 0..15" in block
    assert "signed 4-bit range would be -2^3..2^3-1" in block


def test_generation_prompt_carries_numeric_block_and_discipline() -> None:
    from mind3.core.contracts import RTLGenerator

    prompt = RTLGenerator.build_prompt(_counter01_contract())
    assert "Numeric facts (derived from contract" in prompt["user"]
    assert "saturation bounds derive from width and signedness" in prompt["system"]
    assert "terminal count is a half-period toggle point" in prompt["system"]
