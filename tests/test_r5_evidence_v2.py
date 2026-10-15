"""R5 evidence decoder and repair guard (flag-gated, default OFF).

- VCD counterexample decoding is pure/deterministic and tested against a
  real arbiter_02 formal-breach trace checked in as a fixture.
- The single-driver repair guard is enforced in the prompt (flag ON) and in
  the repair loop (multidriven candidates rejected pre-EDA).
- Flag OFF keeps every prompt byte-identical to baseline.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    VerificationFailureEvidence,
    VerificationRepairer,
    contract_from_benchmark_record,
)
from mind3.core.formal_templates import (
    contract_property_source,
    resolve_witness_property,
)
from mind3.core.vcd_evidence import (
    decode_counterexample,
    detect_multidriven_nets,
    evidence_v2_enabled,
    latency_hint_for_repair,
    parse_vcd,
    property_signal_names,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VCD_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "vcd" / "arbiter_02_formal_breach.vcd"
)


def _evidence() -> VerificationFailureEvidence:
    return VerificationFailureEvidence(
        gate="Gate 2: SymbiYosys Formal Property Verification",
        category="FORMAL_INVARIANT_BREACH",
        failing_property="req[0] |-> gnt[0]",
        failing_step="2",
    )


def test_evidence_v2_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIND3_EVIDENCE_V2", raising=False)
    assert evidence_v2_enabled() is False


def test_prompt_flag_off_byte_identical() -> None:
    """Flag OFF (and default call) builds the legacy prompt exactly."""
    contract = InterfaceContract(
        module_name="m",
        functional_spec="s",
        ports=[PortDefinition(name="clk", direction=PortDirection.INPUT, width=1)],
    )
    evidence = _evidence()
    baseline = VerificationRepairer.build_prompt(contract, "module m(); endmodule", evidence)
    flagged_off = VerificationRepairer.build_prompt(
        contract, "module m(); endmodule", evidence, evidence_v2=False
    )
    assert flagged_off == baseline
    assert "EVIDENCE-V2" not in flagged_off["system"]


def test_prompt_flag_on_adds_guard() -> None:
    contract = InterfaceContract(
        module_name="m",
        functional_spec="s",
        ports=[PortDefinition(name="clk", direction=PortDirection.INPUT, width=1)],
    )
    flagged_on = VerificationRepairer.build_prompt(
        contract, "module m(); endmodule", _evidence(), evidence_v2=True
    )
    assert "EVIDENCE-V2 REPAIR GUARD" in flagged_on["system"]
    assert "assign" in flagged_on["system"]


def test_decode_real_arbiter_vcd() -> None:
    """A real arbiter_02 breach trace decodes to a grounded cycle table."""
    vcd = VCD_FIXTURE.read_text(encoding="utf-8")
    parsed = parse_vcd(vcd)
    assert len(parsed["signals"]) == 15
    assert [s["step"] for s in parsed["steps"]] == [0, 1, 2, 3]
    decoded = decode_counterexample(
        vcd,
        port_names=["clk", "rst_n", "req", "gnt"],
        extra_names=property_signal_names("req[0] |-> gnt[0]"),
        t_fail=2,
        failing_assertion="req[0] |-> gnt[0]",
    )
    assert decoded["t_fail"] == 2
    assert decoded["signals"] == ["clk", "rst_n", "req", "gnt"]
    assert [r["step"] for r in decoded["rows"]] == [0, 1, 2]
    assert "1 (released)" in decoded["markdown"]
    assert "t_fail: req[0] |-> gnt[0]" in decoded["markdown"]
    # Every cell quotes the fixture (spot-check one known sample).
    assert "| 1 | 0 | 1 (released) | 1001 | 0000 |" in decoded["markdown"]


def test_decode_caps_deep_traces() -> None:
    lines = ["$var wire 1 a clk $end", "$enddefinitions $end", "#0", "b0 a"]
    for step in range(1, 30):
        lines += [f"#{step * 10}", f"b{step % 2} a"]
    decoded = decode_counterexample(
        "\n".join(lines), port_names=["a"], t_fail=29, max_cycles=10
    )
    assert decoded["truncated"] is True
    assert [r["step"] for r in decoded["rows"]] == list(range(20, 30))


def test_decode_malformed_never_raises() -> None:
    decoded = decode_counterexample("not a vcd at all", port_names=["clk"])
    assert decoded["rows"] == []
    assert "undecodable" in decoded["markdown"]


ARBITER_CLEAN = """module arbiter_02 (
  input  logic clk,
  input  logic rst_n,
  input  logic [3:0] req,
  output logic [3:0] gnt
);
  always_ff @(posedge clk) begin
    if (!rst_n) gnt <= 4'b0000;
    else gnt <= req;
  end
endmodule
"""

ARBITER_MULTIDRIVEN = ARBITER_CLEAN.replace(
    "endmodule",
    "  // Repair attempt: second driver on gnt (must be rejected).\n"
    "  assign gnt = (req[0]) ? 4'b0001 : 4'b0000;\n"
    "endmodule",
)


def test_multidriven_detects_assign_plus_always() -> None:
    hits = detect_multidriven_nets(ARBITER_MULTIDRIVEN)
    assert [h["signal"] for h in hits] == ["gnt"]
    assert hits[0]["continuous"] is True
    assert hits[0]["procedural_blocks"] == 1


def test_multidriven_clean_passes() -> None:
    assert detect_multidriven_nets(ARBITER_CLEAN) == []


def test_multidriven_ignores_comparisons_and_locals() -> None:
    rtl = """module t(input logic clk, input logic [3:0] a, b, output logic [3:0] y);
  always_ff @(posedge clk) begin
    logic tmp;
    tmp = (a <= b);
    if (tmp) y <= a;
    else y <= b;
  end
endmodule
"""
    assert detect_multidriven_nets(rtl) == []


def test_repair_multidriven_rejected_pre_eda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A duplicate-driver repair is rejected without rerunning the verifier."""
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
                super().__init__(top_module="arbiter_02", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                if self.calls == 1:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="Latch inferred in arbiter_02",
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
            session_id="multidriven-repair-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps(
            {
                "module_name": "arbiter_02",
                "functional_spec": "Fixed-priority arbiter.",
                "ports": [
                    {"name": "clk", "direction": "input", "width": 1},
                    {"name": "rst_n", "direction": "input", "width": 1},
                    {"name": "req", "direction": "input", "width": 4},
                    {"name": "gnt", "direction": "output", "width": 4},
                ],
                "sva_properties": [],
                "timing": {"clock_name": "clk", "period_ns": 5.0},
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
                return ARBITER_CLEAN
            if query_count == 3:
                return ARBITER_MULTIDRIVEN
            feedbacks.append(messages[-1]["content"])
            return ARBITER_CLEAN

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize arbiter_02") is True
        assert verifier.calls == 2, "multidriven candidate must not rerun the verifier"
        assert any(
            record.phase == PhaseEnum.VERIFY
            and record.event.payload.get("error_category") == "REPAIR_MULTIDRIVEN"
            for record in driver.transcript
        )
        assert feedbacks and "assign" in feedbacks[0]


def _dev_contract(task_id: str):
    import json as _json

    for line in (
        REPO_ROOT / "benchmarks" / "development-20" / "tasks.jsonl"
    ).read_text(encoding="utf-8").splitlines():
        record = _json.loads(line)
        if record.get("task_id") == task_id:
            return contract_from_benchmark_record(
                {
                    "task_id": record["task_id"],
                    "natural_language_spec": record["natural_language_spec"],
                    "expected_ports": record["expected_ports"],
                    "clock_reset_assumptions": record["clock_reset_assumptions"],
                    "functional_requirements": record["functional_requirements"],
                    "expected_properties": record["expected_properties"],
                }
            )
    raise KeyError(task_id)


def test_witness_resolves_to_property_marker() -> None:
    sva_lines = ["module arbiter_02_sva;"]
    sva_lines += [f"  // filler line {i}" for i in range(2, 16)]
    sva_lines.append("  // [MIND3-TEMPLATE:same_cycle_implication] contract_property_1")
    sva_lines += ["  always @(posedge clk) begin", "    if (req[0]) assert (gnt[0]);", "  end"]
    sva_lines.append("endmodule")
    sva_text = "\n".join(sva_lines)
    assert (
        resolve_witness_property(
            "arbiter_02_formal_top.sva._witness_.check_assert_arbiter_02_sva_sv_17_5",
            sva_text,
        )
        == "contract_property_1"
    )


def test_witness_resolve_fallbacks() -> None:
    assert resolve_witness_property("not_a_witness", "module x; endmodule") is None
    assert resolve_witness_property(None, "module x; endmodule") is None
    assert resolve_witness_property("check_assert_m_sva_sv_3_1", None) is None
    assert resolve_witness_property("check_assert_m_sva_sv_99_5", "line1\nline2") is None
    assert (
        resolve_witness_property("check_assert_m_sva_sv_2_1", "line1\nline2") is None
    )


def test_contract_property_source_shapes() -> None:
    from types import SimpleNamespace

    formal = [
        SimpleNamespace(
            name="p_impl",
            kind="same_cycle_implication",
            antecedent="req[0]",
            consequent="gnt[0]",
            expression=None,
            signal=None,
            value=None,
        ),
        SimpleNamespace(
            name="p_next",
            kind="next_cycle_implication",
            antecedent="a",
            consequent="b",
            expression=None,
            signal=None,
            value=None,
        ),
        SimpleNamespace(
            name="p_bool",
            kind="boolean",
            antecedent=None,
            consequent=None,
            expression="x == y",
            signal=None,
            value=None,
        ),
        SimpleNamespace(
            name="p_oh0",
            kind="onehot0",
            antecedent=None,
            consequent=None,
            expression=None,
            signal="gnt",
            value=None,
        ),
    ]
    legacy = [SimpleNamespace(name="p_leg", property_expr="a |-> b")]
    contract = SimpleNamespace(formal_properties=formal, sva_properties=legacy)
    assert contract_property_source(contract, "p_impl") == (
        "same_cycle_implication",
        "req[0] |-> gnt[0]",
    )
    assert contract_property_source(contract, "p_next") == (
        "next_cycle_implication",
        "a |=> b",
    )
    assert contract_property_source(contract, "p_bool") == ("boolean", "x == y")
    assert contract_property_source(contract, "p_oh0") == ("onehot0", "$onehot0(gnt)")
    assert contract_property_source(contract, "p_leg") == ("legacy_sva", "a |-> b")
    assert contract_property_source(contract, "missing") is None
    assert contract_property_source(contract, None) is None


def test_witness_end_to_end_on_real_render() -> None:
    """The real arbiter_02 witness resolves against the real generated SVA."""
    from mind3.core.contracts import VerificationHarnessGenerator

    contract = _dev_contract("arbiter_02")
    sva_text = VerificationHarnessGenerator.build_sva_bind_module(contract)
    witness = "arbiter_02_formal_top.sva._witness_.check_assert_arbiter_02_sva_sv_19_5"
    assert resolve_witness_property(witness, sva_text) == "contract_property_1"
    assert contract_property_source(contract, "contract_property_1") == (
        "same_cycle_implication",
        "req[0] |-> gnt[0]",
    )


REGISTERED_ARBITER = """module arbiter_02 (
  input  logic clk,
  input  logic rst_n,
  input  logic [3:0] req,
  output logic [3:0] gnt
);
  always_ff @(posedge clk) begin
    if (!rst_n) gnt <= 4'b0000;
    else gnt <= req;
  end
endmodule
"""

COMBINATIONAL_ARBITER = """module arbiter_02 (
  input  logic clk,
  input  logic rst_n,
  input  logic [3:0] req,
  output logic [3:0] gnt
);
  assign gnt[0] = req[0];
  assign gnt[1] = req[1] & ~req[0];
  assign gnt[2] = req[2] & ~req[1] & ~req[0];
  assign gnt[3] = req[3] & ~req[2] & ~req[1] & ~req[0];
endmodule
"""


def test_latency_hint_fires_on_registered_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIND3_EVIDENCE_V2", "1")
    contract = _dev_contract("arbiter_02")
    hint = latency_hint_for_repair(contract, REGISTERED_ARBITER, "req[0] |-> gnt[0]")
    assert hint == (
        "TIMING LATENCY HINT: Violated property 'req[0] |-> gnt[0]' requires "
        "same-cycle (0-cycle combinational) response via '|->', but candidate "
        "RTL registers the output inside 'always_ff' (causing a 1-cycle delay). "
        "Drive same-cycle outputs combinationally using 'always_comb' or "
        "'assign' instead of 'always_ff'."
    )


def test_latency_hint_abstains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIND3_EVIDENCE_V2", "1")
    contract = _dev_contract("arbiter_02")
    assert (
        latency_hint_for_repair(contract, REGISTERED_ARBITER, "req[0] |=> gnt[0]")
        is None
    )
    assert (
        latency_hint_for_repair(contract, REGISTERED_ARBITER, "a |-> $past(b)")
        is None
    )
    assert (
        latency_hint_for_repair(contract, COMBINATIONAL_ARBITER, "req[0] |-> gnt[0]")
        is None
    )
    assert (
        latency_hint_for_repair(contract, REGISTERED_ARBITER, "req |-> gnt")
        is not None
    )
    assert latency_hint_for_repair(contract, REGISTERED_ARBITER, None) is None
    assert latency_hint_for_repair(contract, "", "req[0] |-> gnt[0]") is None


def test_latency_hint_flag_off_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIND3_EVIDENCE_V2", "0")
    contract = _dev_contract("arbiter_02")
    assert (
        latency_hint_for_repair(contract, REGISTERED_ARBITER, "req[0] |-> gnt[0]")
        is None
    )
