"""R3 verifier-integrity tests (P3-COMPLETE fixes the classifier escapes below).

Covers: pinning of _OPTIONAL_GATE_NAMES, formal-template vacuity, per-family
known-bad mutants (formal AND coverage must reject, reported per gate), and
parser rejection of prose-as-RTL.

Conventions: live-verifier tests carry @pytest.mark.eda and use the same
LocalBwrapRunner(ws, allow_unsandboxed=True) pattern as the existing gate
suites. Tautology reproducers below are conditional xfails: they xfail
(strict) only with MIND3_GATE_FIXES=0 (legacy escape) and must pass with the
fixes on (P3-COMPLETE classifier rejection).
"""

import ast
import os
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
from mind3.core.driver import ModelResponseParseError, _parse_model_code_response
from mind3.core.formal_templates import (
    FormalTemplateKind,
    UnsupportedFormalTemplate,
    classify_legacy_property,
)
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.remote_eda import LocalBwrapRunner

REPO_ROOT = Path(__file__).resolve().parents[1]

PINNED_OPTIONAL_GATES = frozenset({"Gate 5: OpenROAD Place-and-Route", "DFT Scan Audit (Advisory)"})

# Tautology reproducers xfail (strict) only with the fixes off. Fixes on
# (default): P3-COMPLETE must reject them and the tests pass normally.
_XFAIL_TAUTOLOGY_OFF = os.environ.get("MIND3_GATE_FIXES", "").strip().lower() in (
    "0",
    "false",
    "no",
    "off",
)


def _ports(specs: list[tuple[str, str, int]]) -> list[PortDefinition]:
    return [PortDefinition(name=n, direction=PortDirection(d), width=w) for n, d, w in specs]


def _contract(module: str, ports: list[tuple[str, str, int]], exprs: list[str]) -> InterfaceContract:
    return InterfaceContract(
        module_name=module,
        functional_spec=f"R3 integrity contract for {module}",
        ports=_ports(ports),
        sva_properties=[SVAProperty(name=f"r3_prop_{i}", property_expr=e) for i, e in enumerate(exprs)],
    )


# ── 1. Optional-gate pinning ──────────────────────────────────────────────────

def test_optional_gate_names_pinned_in_source() -> None:
    """The unconditional _OPTIONAL_GATE_NAMES literal must equal exactly the two
    known-optional gates. Any silent widening (letting required skips pass) or
    renaming fails here. Verifier code itself is NOT modified by this test."""
    tree = ast.parse((REPO_ROOT / "src" / "mind3" / "core" / "verifier.py").read_text(encoding="utf-8"))
    found: list[set[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_OPTIONAL_GATE_NAMES" for t in node.targets
        ):
            if isinstance(node.value, ast.Set):
                found.append({el.value for el in node.value.elts if isinstance(el, ast.Constant)})
    assert found, "_OPTIONAL_GATE_NAMES literal not found in verifier.py"
    assert found[0] == set(PINNED_OPTIONAL_GATES), f"optional gate set changed: {found[0]!r}"


@pytest.mark.eda
def test_optional_gate_rule_holds_on_live_partial_run() -> None:
    """Live wiring check on a real partial run. The async-reset register passes
    Gates 1/3/2 with real tools; Gate 4 then env-fails without liberty (this
    Mac's ABC cannot read liberty files either, so later gates are
    unreachable here — documented, not asserted). The test pins that
    silicon_verified equals the fail-closed rule recomputed in-test from the
    real reports with the pinned optional set: a silent widening that flips a
    verdict would disagree."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "r3_areg.sv"
        dut.write_text(
            "module r3_areg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= d;\n"
            "  end\n"
            "endmodule\n"
        )
        contract = _contract(
            "r3_areg",
            [("clk", "input", 1), ("rst_n", "input", 1), ("d", "input", 8), ("q", "output", 8)],
            ["!rst_n |-> (q == 8'h00)"],
        )
        (ws / "r3_areg_tb.cpp").write_text(
            VerificationHarnessGenerator.build_verilator_cpp_testbench(contract), encoding="utf-8"
        )
        verifier = SiliconSignoffVerifier(top_module="r3_areg", contract=contract, allow_mock_fallback=False)
        res = verifier.verify(ws, LocalBwrapRunner(ws, allow_unsandboxed=True))
        names = [g.get("gate", "") for g in res.gate_reports]
        assert names[:3] == [
            "Gate 1: Yosys Elaboration & Latch Trap",
            "Gate 3: Verilator Coverage Signoff",
            "Gate 2: SymbiYosys Formal Property Verification",
        ]
        assert all(g.get("passed") for g in res.gate_reports[:3])
        assert all(g.get("simulated", False) is False for g in res.gate_reports)
        # Gate 4 without liberty is a tool/environment stop, not a model failure.
        assert res.gate_reports[3]["gate"] == "Gate 4: OpenSTA Multi-Corner Timing Signoff"
        assert res.gate_reports[3]["error_category"] == "ENVIRONMENT_FAILURE"
        # Mirror the verifier's own structure: the sim/skip rule is evaluated on
        # the all-passed path; any failed gate forces silicon_verified False.
        recomputed = (
            all(g.get("passed", False) for g in res.gate_reports)
            and not any(g.get("simulated", False) for g in res.gate_reports)
            and not any(
                g.get("skipped", False)
                for g in res.gate_reports
                if g.get("gate", "") not in PINNED_OPTIONAL_GATES
            )
        )
        assert res.silicon_verified == recomputed == False


# ── 2. Formal-template vacuity ────────────────────────────────────────────────

def test_supported_shapes_classify_deterministically() -> None:
    """Pin desired classifier behavior (must keep passing)."""
    assert classify_legacy_property("a", "assert property (@(posedge clk) req[0] |-> gnt[0]);").kind == FormalTemplateKind.SAME_CYCLE_IMPLICATION
    assert classify_legacy_property("b", "assert property (@(posedge clk) $onehot0(gnt));").kind == FormalTemplateKind.ONEHOT0
    assert classify_legacy_property("c", "assert property (@(posedge clk) sum == (a + b));").kind == FormalTemplateKind.BOOLEAN
    with pytest.raises(UnsupportedFormalTemplate):
        classify_legacy_property("d", "assert property (@(posedge clk) a ##2 b);")


@pytest.mark.parametrize("tautology", ["1'b1", "q == q", "req[0] |-> req[0]"])
@pytest.mark.xfail(
    _XFAIL_TAUTOLOGY_OFF,
    strict=True,
    reason="R3-B legacy escape: classifier accepts tautologies with MIND3_GATE_FIXES=0",
)
def test_tautology_rejected_by_classifier(tautology: str) -> None:
    """P3-COMPLETE: a trivially-true property must classify TAUTOLOGY, never
    compile into a passing assertion."""
    spec = classify_legacy_property("t", f"assert property (@(posedge clk) {tautology});")
    assert spec.kind == FormalTemplateKind.TAUTOLOGY


@pytest.mark.eda
@pytest.mark.xfail(
    _XFAIL_TAUTOLOGY_OFF,
    strict=True,
    reason="R3-B legacy escape: tautology-only contract verifies a buggy DUT with MIND3_GATE_FIXES=0",
)
def test_tautology_only_contract_rejects_buggy_dut() -> None:
    """P3-COMPLETE: a contract containing ONLY `1'b1` must fail closed
    (NO_GENUINE_PROPERTY), never verify a deliberately wrong adder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "r3_buggy.sv"
        dut.write_text(
            "module r3_buggy(input [3:0] a, input [3:0] b, output [3:0] sum);\n"
            "  assign sum = a ^ b;\n"
            "endmodule\n"
        )
        contract = _contract(
            "r3_buggy",
            [("a", "input", 4), ("b", "input", 4), ("sum", "output", 4)],
            ["1'b1"],
        )
        verifier = SiliconSignoffVerifier(top_module="r3_buggy", contract=contract, allow_mock_fallback=False)
        res = verifier._run_gate2_formal_sby(LocalBwrapRunner(ws, allow_unsandboxed=True), [dut], ws)
        assert res["passed"] is False, "vacuous contract verified a buggy DUT"
        assert res["error_category"] == "NO_GENUINE_PROPERTY"


# ── 2b. P3-COMPLETE scope: table positives and conservative negatives ────────

_P3C_TABLE_POSITIVES = [
    "en |-> 1'b1",
    "1'b0 |-> gnt[0]",
    "a || !a || b",
    "(a || !a) && (b || !b)",
    "!(a || b) || !a || !b || (a && b)",
    "((a && b)) || (!((a && b)))",
    "(a || b) || !(a || b)",
    "(b == a) || !(a == b)",
    "x |-> (x || y)",
    "(a && !a) |-> g",
    "a && b |-> a",
    "((a)) || (!(a))",
    "!(a == b) || (a == b)",
    "x == 8'hx || !(x == 8'hx)",
]


@pytest.mark.parametrize("tautology", _P3C_TABLE_POSITIVES)
@pytest.mark.xfail(
    _XFAIL_TAUTOLOGY_OFF,
    strict=True,
    reason="P3-COMPLETE table proofs exist only with MIND3_GATE_FIXES=1",
)
def test_p3c_propositional_tautologies_classify_tautology(tautology: str) -> None:
    """Compound boolean tautologies (truth-table provable, <= 8 variables)
    must classify TAUTOLOGY under the fixes."""
    spec = classify_legacy_property("t", f"assert property (@(posedge clk) {tautology});")
    assert spec.kind == FormalTemplateKind.TAUTOLOGY


_P3C_NEGATIVES = [
    # Falsifiable lookalikes: each has a falsifying assignment and must stay.
    "a || b",
    "x == y",
    "!(a && b) || !a || !b",
    "!(a || b) || !a",
    "a && (b || !b)",
    "!a || !b",
    # Temporal / sliced / narrow forms abstain (conservative, still accepted).
    "a |=> a",
    "req[0] |-> gnt[0]",
    "en |-> (gnt[0] || !gnt[0])",
]


@pytest.mark.parametrize("expr", _P3C_NEGATIVES)
def test_p3c_near_tautologies_not_dropped(expr: str) -> None:
    """Falsifiable or out-of-scope forms must NOT classify TAUTOLOGY."""
    spec = classify_legacy_property("n", f"assert property (@(posedge clk) {expr});")
    assert spec.kind != FormalTemplateKind.TAUTOLOGY


# ── 3. Per-family known-bad mutants ───────────────────────────────────────────
# Each mutant is genuinely invalid under its contract. Caught = formal OR
# coverage (or an earlier gate) rejects with a real (non-mock) verdict. The
# per-gate matrix is asserted exactly where the pipeline is deterministic and
# recorded otherwise; the catch rate is reported in the phase report.

ARBITER_BAD_RTL = (
    "module r3_arb(input clk, input rst_n, input [1:0] req, output reg [1:0] gnt);\n"
    "  always @(posedge clk or negedge rst_n) begin\n"
    "    if (!rst_n) gnt <= 2'b00;\n"
    "    else begin gnt[0] <= req[0]; gnt[1] <= ~req[0] & req[1]; end\n"
    "  end\n"
    "endmodule\n"
)
ARBITER_PORTS = [("clk", "input", 1), ("rst_n", "input", 1), ("req", "input", 2), ("gnt", "output", 2)]
ARBITER_PROPS = ["req[0] |-> gnt[0]", "$onehot0(gnt)"]


@pytest.mark.eda
def test_mutant_registered_arbiter_rejected_by_formal() -> None:
    """Family: arbiters. Registered grant cannot meet same-cycle req->gnt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "r3_arb.sv"
        dut.write_text(ARBITER_BAD_RTL)
        verifier = SiliconSignoffVerifier(
            top_module="r3_arb", contract=_contract("r3_arb", ARBITER_PORTS, ARBITER_PROPS), allow_mock_fallback=False
        )
        res = verifier._run_gate2_formal_sby(LocalBwrapRunner(ws, allow_unsandboxed=True), [dut], ws)
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"
        assert res["simulated"] is False


@pytest.mark.eda
def test_mutant_bad_reset_value_rejected_by_formal() -> None:
    """Family: counters. Reset drives 1s while the contract demands 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "r3_cntrst.sv"
        dut.write_text(
            "module r3_cntrst(input clk, input rst_n, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'hFF;\n"
            "    else q <= q + 1'b1;\n"
            "  end\n"
            "endmodule\n"
        )
        verifier = SiliconSignoffVerifier(
            top_module="r3_cntrst",
            contract=_contract("r3_cntrst", [("clk", "input", 1), ("rst_n", "input", 1), ("q", "output", 8)], ["!rst_n |-> (q == 8'h00)"]),
            allow_mock_fallback=False,
        )
        res = verifier._run_gate2_formal_sby(LocalBwrapRunner(ws, allow_unsandboxed=True), [dut], ws)
        assert res["passed"] is False
        assert res["error_category"] == "FORMAL_INVARIANT_BREACH"
        assert res["simulated"] is False


@pytest.mark.eda
def test_mutant_multidriven_fifo_rejected_before_signoff() -> None:
    """Family: FIFOs. Two processes drive `q`; must not reach signoff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "r3_fifomd.sv"
        dut.write_text(
            "module r3_fifomd(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk) q <= d;\n"
            "  always @(posedge clk) q <= 8'h00;\n"
            "endmodule\n"
        )
        verifier = SiliconSignoffVerifier(
            top_module="r3_fifomd",
            contract=_contract("r3_fifomd", [("clk", "input", 1), ("rst_n", "input", 1), ("d", "input", 8), ("q", "output", 8)], ["q == d"]),
            allow_mock_fallback=False,
        )
        res = verifier.verify(ws, LocalBwrapRunner(ws, allow_unsandboxed=True))
        assert res.passed is False
        assert res.silicon_verified is False
        assert all(g.get("simulated", False) is False for g in res.gate_reports)


@pytest.mark.eda
def test_mutant_latch_rejected_at_gate1() -> None:
    """Family: combinational. Missing else infers a latch; Gate 1 must reject."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "r3_latch.sv"
        dut.write_text(
            "module r3_latch(input [3:0] a, input sel, output reg [3:0] y);\n"
            "  always @(*) begin\n"
            "    if (sel) y = a;\n"
            "  end\n"
            "endmodule\n"
        )
        verifier = SiliconSignoffVerifier(
            top_module="r3_latch",
            contract=_contract("r3_latch", [("a", "input", 4), ("sel", "input", 1), ("y", "output", 4)], ["sel |-> (y == a)"]),
            allow_mock_fallback=False,
        )
        res = verifier._run_gate1_yosys(LocalBwrapRunner(ws, allow_unsandboxed=True), [dut], ws)
        assert res["passed"] is False, f"latch inferred but Gate 1 passed: {res.get('details')}"
        assert res["simulated"] is False


@pytest.mark.eda
def test_mutant_dead_branch_rejected_by_coverage() -> None:
    """Family: coverage. Internally-tied-off debug branch is unreachable; Gate 3
    at default 95/90 thresholds must report COVERAGE_DEFICIT."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        dut = ws / "r3_dbgreg.sv"
        dut.write_text(
            "module r3_dbgreg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  wire dbg = 1'b0;\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else if (dbg) q <= ~d;\n"
            "    else q <= d;\n"
            "  end\n"
            "endmodule\n"
        )
        contract = _contract("r3_dbgreg", [("clk", "input", 1), ("rst_n", "input", 1), ("d", "input", 8), ("q", "output", 8)], ["q == d"])
        (ws / "r3_dbgreg_tb.cpp").write_text(
            VerificationHarnessGenerator.build_verilator_cpp_testbench(contract), encoding="utf-8"
        )
        verifier = SiliconSignoffVerifier(top_module="r3_dbgreg", contract=contract, allow_mock_fallback=False)
        res = verifier._run_gate3_coverage(LocalBwrapRunner(ws, allow_unsandboxed=True), [dut], ws)
        assert res["passed"] is False, f"dead branch passed coverage: {res.get('metrics')}"
        assert res["error_category"] == "COVERAGE_DEFICIT", f"wrong category: {res.get('error_category')}"
        assert res["simulated"] is False


# ── 4. Parser rejects prose-as-RTL ────────────────────────────────────────────

def test_parser_rejects_pure_prose() -> None:
    """A response with no RTL at all must fail closed, never return prose."""
    prose = (
        "Here is my design approach for the counter module. I considered using a "
        "synchronous reset strategy with an enable signal. The implementation follows "
        "standard practices and should synthesize cleanly in most toolchains."
    )
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(prose, default_module_name="counter_4bit")


def test_parser_rejects_explanation_with_junk_code() -> None:
    """Explanatory prose plus a non-module code fragment must fail closed."""
    with pytest.raises(ModelResponseParseError):
        _parse_model_code_response(
            "Sure! The fix is to change the sensitivity list. assign stuff here; always @(posedge clk);",
            default_module_name="counter_4bit",
        )


def test_parser_embedded_module_block_is_documented_recovery() -> None:
    """Pinned current behavior: a fenced module inside prose is recovered (the
    pipeline relies on this for local-model output). This documents, not blesses,
    the recovery path."""
    out = _parse_model_code_response(
        "Here is the fixed design:\n```systemverilog\nmodule doc_rec(input clk, output reg q);\n  always @(posedge clk) q <= 1'b0;\nendmodule\n```\nHope this helps!",
        default_module_name="doc_rec",
    )
    assert "module doc_rec" in out and "endmodule" in out
