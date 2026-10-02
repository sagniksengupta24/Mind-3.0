"""Stage 4b temporal + vacuity evidence for Gate 2.

Live tests invoke real SymbiYosys (smtbmc/z3, BMC depth 25) through the real
contract -> harness -> .sby -> sby path. They are marked `eda` like the
existing mandatory Gate 2 suite.

Temporal fixtures are deliberately reset-free and free-running: with fully
free primary inputs, the only way the broken designs below can fail is the
intended timing mismatch (no reset-deassertion edge exists to blame). The
correct next-cycle design passes, proving the template preserves timing
semantics instead of rejecting everything.

Deterministic classifier tests (no EDA) pin the supported/unsupported
boundary for every audited construct.
"""

import json
import tempfile
from pathlib import Path

import pytest

from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    SVAProperty,
    VerificationHarnessGenerator,
)
from mind3.core.formal_templates import (
    FormalPropertySpec,
    FormalTemplateKind,
    UnsupportedFormalTemplate,
    classify_legacy_property,
    compile_cover_point,
    compile_formal_property,
)
from mind3.core.verifier import SiliconSignoffVerifier, parse_sby_cover
from mind3.sandbox.remote_eda import LocalBwrapRunner

pytestmark = pytest.mark.eda


def _live_gate2(tmpdir: str, module: str, dut: str, contract: InterfaceContract) -> dict:
    """Generate DUT, run the real Gate 2 path (harness + sby), return the gate dict."""
    ws = Path(tmpdir)
    dut_file = ws / f"{module}.sv"
    dut_file.write_text(dut)
    verifier = SiliconSignoffVerifier(top_module=module, contract=contract, allow_mock_fallback=False)
    runner = LocalBwrapRunner(ws, allow_unsandboxed=True)
    return verifier._run_gate2_formal_sby(runner, [dut_file], ws)


def _free_running_ports() -> list:
    return [
        PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
        PortDefinition(name="req", direction=PortDirection.INPUT, width=1),
        PortDefinition(name="gnt", direction=PortDirection.OUTPUT, width=1),
    ]


# ── R5A: same-cycle implication, broken RTL must FAIL live ────────────────

def test_temporal_same_cycle_broken_caught_live() -> None:
    """`req |-> gnt` is false (gated by en); live SBY must report FAIL with evidence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        contract = InterfaceContract(
            module_name="sc_broken",
            functional_spec="same-cycle grant",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="req", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="en", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="gnt", direction=PortDirection.OUTPUT, width=1),
            ],
            sva_properties=[SVAProperty(name="req_implies_gnt", property_expr="req |-> gnt")],
        )
        res = _live_gate2(
            tmpdir,
            "sc_broken",
            "module sc_broken(input clk, input req, input en, output gnt);\n  assign gnt = req && en;\nendmodule\n",
            contract,
        )
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"
        assert res["simulated"] is False


# ── R5B (mandatory): next-cycle implication, broken RTL must FAIL live ───

def test_temporal_next_cycle_broken_caught_live() -> None:
    """`req |=> gnt` against same-cycle `gnt = req`: only a timing mismatch can fail.

    The design is reset-free with free inputs, so no reset edge or
    initialization artifact can explain a failure — the checker must catch
    req(t-1)=1, req(t)=0 producing gnt(t)=0.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        contract = InterfaceContract(
            module_name="nc_broken",
            functional_spec="next-cycle grant, broken as same-cycle",
            ports=_free_running_ports(),
            formal_properties=[
                FormalPropertySpec(
                    name="req_next_gnt",
                    kind=FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
                    clock="clk",
                    antecedent="req",
                    consequent="gnt",
                )
            ],
        )
        res = _live_gate2(
            tmpdir,
            "nc_broken",
            "module nc_broken(input clk, input req, output gnt);\n  assign gnt = req;\nendmodule\n",
            contract,
        )
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"
        assert res["step"] not in (None, "unknown")
        assert res["simulated"] is False


# ── R5C: next-cycle implication, correct RTL must PASS exercised ──────────

def test_temporal_next_cycle_correct_passes_exercised_live() -> None:
    """Flopped `gnt <= req` satisfies `req |=> gnt`; PASS must be exercised, not vacuous."""
    with tempfile.TemporaryDirectory() as tmpdir:
        contract = InterfaceContract(
            module_name="nc_correct",
            functional_spec="next-cycle grant, correct one-cycle delay",
            ports=_free_running_ports(),
            formal_properties=[
                FormalPropertySpec(
                    name="req_next_gnt",
                    kind=FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
                    clock="clk",
                    antecedent="req",
                    consequent="gnt",
                )
            ],
        )
        res = _live_gate2(
            tmpdir,
            "nc_correct",
            "module nc_correct(input clk, input req, output reg gnt);\n  always @(posedge clk) gnt <= req;\nendmodule\n",
            contract,
        )
        assert res["passed"] is True, f"Correct next-cycle design must pass: {res.get('details')}"
        assert res["error_category"] is None
        assert res["bmc_depth"] == 25
        assert "for all" not in res["details"]
        vacuity = res["vacuity"]
        assert vacuity["status"] == "EXERCISED"
        assert vacuity["assert_depth"] == 25
        assert vacuity["cover_depth"] == 25
        assert vacuity["antecedents"]["req_next_gnt"]["reached"] is True
        assert isinstance(vacuity["antecedents"]["req_next_gnt"]["step"], int)
        # Serialization preserves the exercised pass.
        parsed = json.loads(json.dumps(res))
        assert parsed["vacuity"]["status"] == "EXERCISED"
        assert parsed["bmc_depth"] == 25


# ── R5D: $past (supported) — broken sequential design must FAIL live ──────

def test_temporal_past_broken_caught_live() -> None:
    """`$past(q, 1) == 0` against constant-1 `q` must FAIL live."""
    with tempfile.TemporaryDirectory() as tmpdir:
        contract = InterfaceContract(
            module_name="past_broken",
            functional_spec="past value check",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=1),
            ],
            formal_properties=[
                FormalPropertySpec(
                    name="q_was_zero",
                    kind=FormalTemplateKind.PAST_EQUALS,
                    clock="clk",
                    signal="q",
                    value="1'b0",
                    cycles=1,
                )
            ],
        )
        res = _live_gate2(
            tmpdir,
            "past_broken",
            "module past_broken(input clk, output reg q);\n  always @(posedge clk) q <= 1'b1;\nendmodule\n",
            contract,
        )
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"


# ── R5E: $stable (supported) — toggling signal must FAIL live ─────────────

def test_temporal_stable_broken_caught_live() -> None:
    """`$stable(q)` against a toggling `q` must FAIL live."""
    with tempfile.TemporaryDirectory() as tmpdir:
        contract = InterfaceContract(
            module_name="stable_broken",
            functional_spec="stability check",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="q", direction=PortDirection.OUTPUT, width=1),
            ],
            formal_properties=[
                FormalPropertySpec(
                    name="q_stable",
                    kind=FormalTemplateKind.PAST_STABLE,
                    clock="clk",
                    signal="q",
                )
            ],
        )
        res = _live_gate2(
            tmpdir,
            "stable_broken",
            "module stable_broken(input clk, output reg q);\n  always @(posedge clk) q <= ~q;\nendmodule\n",
            contract,
        )
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"


# ── R7/R8: vacuous antecedent must NOT become an ordinary PASS ────────────

def test_temporal_vacuous_antecedent_reported_live() -> None:
    """`dead |-> out` with `dead` tied 0 passes BMC but is VACUOUS, never PASS."""
    with tempfile.TemporaryDirectory() as tmpdir:
        contract = InterfaceContract(
            module_name="vac_mod",
            functional_spec="impossible antecedent",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
                PortDefinition(name="dead", direction=PortDirection.OUTPUT, width=1),
                PortDefinition(name="out", direction=PortDirection.OUTPUT, width=1),
            ],
            sva_properties=[SVAProperty(name="dead_implies_out", property_expr="dead |-> out")],
        )
        res = _live_gate2(
            tmpdir,
            "vac_mod",
            "module vac_mod(input clk, input rst_n, output dead, output out);\n"
            "  assign dead = 1'b0;\n  assign out = 1'b0;\nendmodule\n",
            contract,
        )
        assert res["passed"] is False
        assert res["error_category"] == "VACUOUS_PROPERTY"
        assert res["unexercised_properties"] == ["dead_implies_out"]
        assert res["vacuity"]["status"] == "VACUOUS"
        assert res["vacuity"]["antecedents"]["dead_implies_out"]["reached"] is False
        assert res["bmc_depth"] == 25
        # A vacuous result survives serialization as vacuous, never as PASS.
        parsed = json.loads(json.dumps(res))
        assert parsed["passed"] is False
        assert parsed["error_category"] == "VACUOUS_PROPERTY"
        assert parsed["vacuity"]["status"] == "VACUOUS"


# ── R10: counterexample evidence is really captured ───────────────────────

def test_temporal_counterexample_evidence_captured_live() -> None:
    """A caught violation preserves the VCD witness file, step, depth, and solver output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        contract = InterfaceContract(
            module_name="ce_mod",
            functional_spec="next-cycle grant, broken as same-cycle",
            ports=_free_running_ports(),
            formal_properties=[
                FormalPropertySpec(
                    name="req_next_gnt",
                    kind=FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
                    clock="clk",
                    antecedent="req",
                    consequent="gnt",
                )
            ],
        )
        res = _live_gate2(
            tmpdir,
            "ce_mod",
            "module ce_mod(input clk, input req, output gnt);\n  assign gnt = req;\nendmodule\n",
            contract,
        )
        assert res["passed"] is False
        assert res["trace_file"] is not None and res["trace_file"].endswith(".vcd")
        vcd_path = ws / res["trace_file"]
        assert vcd_path.exists(), f"Witness VCD must exist on disk: {res['trace_file']}"
        assert res["counterexample_trace"] is not None
        assert "$version" in res["counterexample_trace"] or "Generated by Yosys" in res["counterexample_trace"]
        assert res["step"] not in (None, "unknown")
        assert "SBY" in res["stdout"] or "smtbmc" in res["stdout"]


# ── R5E/R11: $rose / $fell explicitly unsupported, fail closed ────────────

def test_rose_fell_unsupported_fail_closed() -> None:
    """$rose/$fell cannot be rendered: classifier rejects, gate reports UNSUPPORTED."""
    for expr in ("$rose(req) |-> gnt", "$fell(req) |-> gnt"):
        with pytest.raises(UnsupportedFormalTemplate):
            classify_legacy_property("p", expr, default_clock="clk")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "rose_mod.sv"
        dut.write_text("module rose_mod(input clk, input req, output gnt);\n  assign gnt = req;\nendmodule\n")
        contract = InterfaceContract(
            module_name="rose_mod",
            functional_spec="rose property",
            ports=_free_running_ports(),
            sva_properties=[SVAProperty(name="p_rose", property_expr="$rose(req) |-> gnt")],
        )
        verifier = SiliconSignoffVerifier(top_module="rose_mod", contract=contract, allow_mock_fallback=False)
        res = verifier._run_gate2_formal_sby(
            LocalBwrapRunner(ws, allow_unsandboxed=True), [dut], ws
        )
        assert res["passed"] is False
        assert res["error_category"] == "UNSUPPORTED_FORMAL_PROPERTY"
        # No sby invocation happened for an unsupported property.
        assert list(ws.glob("*.sby")) == []


# ── R4/R11: ##1 handling — bare ##1 unsupported, |=> ##1 not rewritten ────

def test_delay_chain_not_rewritten() -> None:
    """`a |=> ##1 b` means `a |-> ##2 b`: outside the subset, must fail closed.

    The old classifier silently rewrote it to same-cycle `|->`; that temporal
    alteration is removed.
    """
    with pytest.raises(UnsupportedFormalTemplate):
        classify_legacy_property("p", "req |=> ##1 gnt", default_clock="clk")
    with pytest.raises(UnsupportedFormalTemplate):
        classify_legacy_property("p", "req |-> ##1 gnt", default_clock="clk")
    # Plain |=> still classifies as next-cycle (supported spelling).
    prop = classify_legacy_property("p", "req |=> gnt", default_clock="clk")
    assert prop.kind == FormalTemplateKind.NEXT_CYCLE_IMPLICATION
    code = compile_formal_property(prop)
    assert "if ($past(req)) assert (gnt);" in code


# ── R11: construct support table pinned by behavior ───────────────────────

def test_construct_support_table() -> None:
    """Each audited construct is either rendered (supported) or fail-closed."""
    # Supported: render to executable checks.
    assert "$past(req)" in compile_formal_property(
        FormalPropertySpec(
            name="p", kind=FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
            clock="clk", antecedent="req", consequent="gnt",
        )
    )
    assert "$past(q, 2)" in compile_formal_property(
        FormalPropertySpec(
            name="p", kind=FormalTemplateKind.PAST_EQUALS,
            clock="clk", signal="q", value="1'b0", cycles=2,
        )
    )
    # $stable is accepted by the classifier and compiled to its $past equivalent.
    assert classify_legacy_property("p", "$stable(q)", default_clock="clk").kind == FormalTemplateKind.PAST_STABLE
    assert "q == $past(q, 1)" in compile_formal_property(
        FormalPropertySpec(
            name="p", kind=FormalTemplateKind.PAST_STABLE, clock="clk", signal="q",
        )
    )
    # Unsupported: fail closed, never silently executed.
    for expr in ("$rose(req) |-> gnt", "$fell(req) |-> gnt", "req |-> ##1 gnt",
                 "req |=> ##1 gnt", "a ##2 b"):
        with pytest.raises(UnsupportedFormalTemplate):
            classify_legacy_property("p", expr, default_clock="clk")


# ── Cover machinery units (calibration-locked, SBY v0.69 formats) ─────────

def test_parse_sby_cover_calibration() -> None:
    reached = "SBY engine_0: ## 0:00:00 Reached cover statement in step 2 at top.cov: top_cover.sv:15.16-15.30 (_witness_.x)"
    unreached = "SBY engine_0: ## 0:00:00 Unreached cover statement at top.cov: top_cover.sv:15.16-15.30 (_witness_.x)"
    targets = [{"name": "p", "file": "top_cover.sv", "line": 15}]
    assert parse_sby_cover(reached, targets) == {"p": {"reached": True, "step": 2}}
    assert parse_sby_cover(unreached, targets) == {"p": {"reached": False, "step": None}}
    # A witness for a different line is unattributable, never guessed.
    other = "SBY engine_0: ## Reached cover statement in step 1 at top.cov: top_cover.sv:16.7-16.18 (_witness_.x)"
    assert parse_sby_cover(other, targets) == {"p": {"reached": None, "step": None}}


def test_cover_guard_mirrors_assert_guard() -> None:
    """Cover points use exactly the assert evaluation condition (no stricter, no looser)."""
    same = FormalPropertySpec(
        name="p", kind=FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        clock="clk", reset="rst_n:active_low", antecedent="req", consequent="gnt",
    )
    expr, guard = compile_cover_point(same)
    assert expr == "req"
    rendered = compile_formal_property(same)
    assert f"if ({guard}) begin" in rendered

    nxt = FormalPropertySpec(
        name="q", kind=FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
        clock="clk", reset="rst_n:active_low", antecedent="req", consequent="gnt",
    )
    expr_n, guard_n = compile_cover_point(nxt)
    assert expr_n == "$past(req)"
    rendered_n = compile_formal_property(nxt)
    assert f"if ({guard_n}) begin" in rendered_n

    # Kinds without antecedents produce no cover point.
    boolean = FormalPropertySpec(
        name="b", kind=FormalTemplateKind.BOOLEAN, clock="clk", expression="q == 1'b0",
    )
    assert compile_cover_point(boolean) is None


def test_cover_line_attribution_pinned() -> None:
    """Recorded cover lines point at actual cover statements in generated code."""
    contract = InterfaceContract(
        module_name="m",
        functional_spec="s",
        ports=[
            PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="a", direction=PortDirection.INPUT, width=8),
            PortDefinition(name="y", direction=PortDirection.OUTPUT, width=8),
        ],
        formal_properties=[
            FormalPropertySpec(
                name="p1", kind=FormalTemplateKind.SAME_CYCLE_IMPLICATION,
                clock="clk", antecedent="a == 8'h00", consequent="y == 8'h00",
            ),
            FormalPropertySpec(
                name="p2", kind=FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
                clock="clk", antecedent="a == 8'h01", consequent="y == 8'h01",
            ),
        ],
    )
    implications, unsupported = VerificationHarnessGenerator.implication_antecedents(contract)
    assert unsupported == []
    assert [i["name"] for i in implications] == ["p1", "p2"]
    code, lines = VerificationHarnessGenerator.build_cover_bind_module(contract, implications)
    src_lines = code.splitlines()
    assert len(lines) == 2
    for recorded, name in zip(lines, ("p1", "p2")):
        statement = src_lines[recorded - 1]
        assert "cover (" in statement, f"line {recorded} is not a cover statement: {statement}"
        assert f"vacuity: {name}" in statement
