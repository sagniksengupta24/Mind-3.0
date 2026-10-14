"""V0 formal-gate soundness audit (test-only; no verifier/template edits).

For each SVA property form, a correct design and a deliberately wrong design
are run through the REAL Gate 2 (`SiliconSignoffVerifier._run_gate2_formal_sby`,
seatbelt-sandboxed real `sby`, same code path as the pipeline).

Verdicts per form: CAUGHT / MISSED / ERROR / SILENTLY-IGNORED / FAIL_CLOSED.
Results (with SBY evidence) are written to results/v4/soundness/v0_results.json
even when assertions fail, so a MISS is preserved as evidence, not just red.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

# Real SBY soundness matrix; excluded from the fast loop.
pytestmark = pytest.mark.eda

from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    SVAProperty,
)
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.platform import get_local_sandbox
from mind3.sandbox.remote_eda import LocalBwrapRunner

RESULTS_PATH = (
    Path(__file__).resolve().parents[2] / "results" / "v4" / "soundness" / "v0_results.json"
)


def _writable_results_path() -> Path:
    """Run-output target: tracked file only with MIND3_WRITE_RESULTS=1.

    Default (standard pytest): untracked runs/ mirror, so SBY timestamp
    churn never dirties tracked result files.
    """
    import os

    if os.environ.get("MIND3_WRITE_RESULTS") == "1":
        return RESULTS_PATH
    alt = RESULTS_PATH.parent.parent / "runs" / RESULTS_PATH.name
    alt.parent.mkdir(parents=True, exist_ok=True)
    return alt


def _ports(specs: list[tuple[str, int]]) -> list[PortDefinition]:
    out = []
    for name, width in specs:
        d = PortDirection.INPUT if name in {"clk", "rst_n", "req", "a", "d", "en", "req0", "req1"} else PortDirection.OUTPUT
        out.append(PortDefinition(name=name, direction=d, width=width))
    return out


def _run_gate(top: str, port_specs: list[tuple[str, int]], props: list[tuple[str, str]],
              rtl: str, workdir: Path) -> tuple[dict, Path]:
    ws = workdir / top
    ws.mkdir(parents=True, exist_ok=True)
    rtl = rtl.replace("module t(", f"module {top}(", 1)
    (ws / f"{top}.sv").write_text(rtl, encoding="utf-8")
    contract = InterfaceContract(
        module_name=top,
        functional_spec=f"V0 soundness probe {top}",
        ports=_ports(port_specs),
        sva_properties=[SVAProperty(name=n, property_expr=e) for n, e in props],
    )
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    verifier = SiliconSignoffVerifier(
        top_module=top, contract=contract, allow_mock_fallback=False
    )
    report = verifier._run_gate2_formal_sby(runner, [ws / f"{top}.sv"], ws)
    return report, ws


def _expected_asserts(ws: Path, top: str) -> int | None:
    p = ws / f"{top}_sva.sv"
    if not p.exists():
        return None
    return len(re.findall(r"assert\s*\(", p.read_text(encoding="utf-8")))


def _registered_asserts(ws: Path, top: str) -> int | None:
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    proc = runner.run(
        ["yosys", "-p",
         f"read -formal {top}.sv; read -formal {top}_sva.sv; "
         f"read -formal {top}_formal_top.sv; prep -top {top}_formal_top; "
         "select -count t:$check"],
        timeout_sec=60,
    )
    if proc.returncode != 0:
        return None
    m = re.findall(r"(\d+)\s+objects\.", proc.stdout)
    return int(m[-1]) if m else None


def _tail(text: str | None, n: int = 25) -> str:
    if not text:
        return ""
    return "\n".join(text.splitlines()[-n:])


CASES: list[dict] = [
    {
        "form": "boolean",
        "props": [("addeq", "assert property (@(posedge clk) disable iff (!rst_n) q == a + b);")],
        "ports": [("clk", 1), ("rst_n", 1), ("a", 2), ("b", 2), ("q", 2)],
        "correct": """module t(input logic clk, input logic rst_n, input logic [1:0] a, input logic [1:0] b, output logic [1:0] q);
  assign q = a + b;
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, input logic [1:0] a, input logic [1:0] b, output logic [1:0] q);
  assign q = a + b + 2'd1;
endmodule
""",
    },
    {
        "form": "same_cycle_implication",
        "props": [("fwd", "assert property (@(posedge clk) disable iff (!rst_n) req |-> gnt);")],
        "ports": [("clk", 1), ("rst_n", 1), ("req", 1), ("gnt", 1)],
        "correct": """module t(input logic clk, input logic rst_n, input logic req, output logic gnt);
  assign gnt = req;
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, input logic req, output logic gnt);
  assign gnt = 1'b0;
endmodule
""",
    },
    {
        "form": "next_cycle_implication",
        "props": [("dly", "assert property (@(posedge clk) disable iff (!rst_n) d |=> q);")],
        "ports": [("clk", 1), ("rst_n", 1), ("d", 1), ("q", 1)],
        "correct": """module t(input logic clk, input logic rst_n, input logic d, output logic q);
  logic qq;
  always_ff @(posedge clk) begin
    qq <= d;
  end
  assign q = qq;
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, input logic d, output logic q);
  assign q = 1'b0;
endmodule
""",
    },
    {
        "form": "onehot0",
        "props": [("oh", "assert property (@(posedge clk) $onehot0(gnt));")],
        "ports": [("clk", 1), ("rst_n", 1), ("req", 1), ("gnt", 2)],
        "correct": """module t(input logic clk, input logic rst_n, input logic req, output logic [1:0] gnt);
  assign gnt = req ? 2'b01 : 2'b00;
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, input logic req, output logic [1:0] gnt);
  assign gnt = 2'b11;
endmodule
""",
    },
    {
        "form": "past_expression",
        "props": [("cnt", "assert property (@(posedge clk) disable iff (!rst_n) q == $past(q) + 2'b01);")],
        "ports": [("clk", 1), ("rst_n", 1), ("q", 2)],
        "correct": """module t(input logic clk, input logic rst_n, output logic [1:0] q);
  always_ff @(posedge clk) begin
    q <= q + 2'b01;
  end
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, output logic [1:0] q);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 2'b00;
    else q <= q;
  end
endmodule
""",
    },
    {
        "form": "delayed_implication_##1",
        "props": [("d1", "assert property (@(posedge clk) disable iff (!rst_n) req |-> ##1 gnt);")],
        "ports": [("clk", 1), ("rst_n", 1), ("req", 1), ("gnt", 1)],
        "correct": """module t(input logic clk, input logic rst_n, input logic req, output logic gnt);
  assign gnt = req;
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, input logic req, output logic gnt);
  assign gnt = 1'b0;
endmodule
""",
    },
    {
        "form": "rose_fell",
        "props": [("re", "assert property (@(posedge clk) disable iff (!rst_n) $rose(req) |-> gnt);")],
        "ports": [("clk", 1), ("rst_n", 1), ("req", 1), ("gnt", 1)],
        "correct": """module t(input logic clk, input logic rst_n, input logic req, output logic gnt);
  assign gnt = req;
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, input logic req, output logic gnt);
  assign gnt = 1'b0;
endmodule
""",
    },
    {
        "form": "bare_immediate_assert",
        "props": [("b", "assert (q <= 2'b11);")],
        "ports": [("clk", 1), ("rst_n", 1), ("q", 2)],
        "correct": """module t(input logic clk, input logic rst_n, output logic [1:0] q);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 2'b00;
    else q <= q + 2'b01;
  end
endmodule
""",
        "wrong": """module t(input logic clk, input logic rst_n, output logic [1:0] q);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 2'b00;
    else q <= q;
  end
endmodule
""",
    },
]


def _classify_report(rep: dict) -> tuple[str, str]:
    if rep.get("passed") is True:
        return "PASS", str(rep.get("error_category") or "")
    return "FAIL", str(rep.get("error_category") or "")


def test_v0_soundness_matrix(tmp_path: Path) -> None:
    records: list[dict] = []
    try:
        for case in CASES:
            form = case["form"]
            for variant in ("correct", "wrong"):
                top = f"v0_{form}_{variant}"
                try:
                    rep, ws = _run_gate(
                        top, case["ports"], case["props"], case[variant], tmp_path
                    )
                except Exception as exc:  # harness-level error, never verifier edits
                    records.append({
                        "form": form, "variant": variant,
                        "verdict": "ERROR",
                        "detail": f"gate raised {type(exc).__name__}: {str(exc)[:300]}",
                    })
                    continue
                outcome, cat = _classify_report(rep)
                exp = _expected_asserts(ws, top)
                reg = _registered_asserts(ws, top) if outcome == "PASS" and variant == "wrong" else None
                if reg is None and (ws / f"{top}_sva.sv").exists():
                    reg = _registered_asserts(ws, top)
                rec = {
                    "form": form, "variant": variant,
                    "gate_passed": rep.get("passed"),
                    "error_category": cat,
                    "expected_asserts": exp,
                    "registered_asserts": reg,
                    "sby_tail": _tail(rep.get("stdout")),
                }
                if variant == "correct":
                    if outcome == "PASS":
                        rec["verdict"] = "PASS"
                    elif cat in {
                        "UNSUPPORTED_FORMAL_PROPERTY", "EMPTY_FORMAL_PROPERTY_SET",
                        "MISSING_VERIFICATION_ARTIFACT", "FORMAL_ANALYSIS_FAILED",
                    }:
                        rec["verdict"] = "FAIL_CLOSED"
                    else:
                        rec["verdict"] = f"UNEXPECTED_FAIL({cat})"
                else:
                    if outcome == "FAIL" and cat == "FORMAL_INVARIANT_BREACH":
                        rec["verdict"] = "CAUGHT"
                    elif outcome == "FAIL" and cat in {
                        "UNSUPPORTED_FORMAL_PROPERTY", "EMPTY_FORMAL_PROPERTY_SET",
                        "MISSING_VERIFICATION_ARTIFACT", "FORMAL_ANALYSIS_FAILED",
                    }:
                        rec["verdict"] = "FAIL_CLOSED"
                    elif outcome == "PASS":
                        if exp is not None and reg is not None and reg < exp:
                            rec["verdict"] = "SILENTLY-IGNORED"
                        else:
                            rec["verdict"] = "MISSED"
                    else:
                        rec["verdict"] = f"ERROR({cat})"
                records.append(rec)

        vacuity_cases = [            {
                "name": "never_firing_antecedent",
                "props": [("v", "assert property (@(posedge clk) disable iff (!rst_n) flag |-> gnt);")],
                "ports": [("clk", 1), ("rst_n", 1), ("flag", 1), ("gnt", 1)],
                "rtl": """module t(input logic clk, input logic rst_n, output logic flag, output logic gnt);
  assign flag = 1'b0;
  assign gnt = 1'b1;
endmodule
""",
            },
            {
                "name": "tautology_out_eq_out",
                "props": [("tprop", "assert property (@(posedge clk) disable iff (!rst_n) out_data == out_data);")],
                "ports": [("clk", 1), ("rst_n", 1), ("out_data", 8)],
                "rtl": """module t(input logic clk, input logic rst_n, output logic [7:0] out_data);
  assign out_data = 8'hA5;
endmodule
""",
            },
            {
                "name": "const_true_consequent",
                "props": [("c", "assert property (@(posedge clk) disable iff (!rst_n) req |-> 1'b1);")],
                "ports": [("clk", 1), ("rst_n", 1), ("req", 1), ("gnt", 1)],
                "rtl": """module t(input logic clk, input logic rst_n, input logic req, output logic gnt);
  assign gnt = req;
endmodule
""",
            },
        ]
        for vc in vacuity_cases:
            top = f"v0_vac_{vc['name']}"
            rtl = vc["rtl"]
            try:
                rep, ws = _run_gate(top, vc["ports"], vc["props"], rtl, tmp_path)
            except Exception as exc:
                records.append({
                    "form": f"vacuity:{vc['name']}", "variant": "probe",
                    "verdict": "ERROR",
                    "detail": f"gate raised {type(exc).__name__}: {str(exc)[:300]}",
                })
                continue
            outcome, cat = _classify_report(rep)
            records.append({
                "form": f"vacuity:{vc['name']}", "variant": "probe",
                "gate_passed": rep.get("passed"),
                "error_category": cat,
                "verdict": f"GATE_{outcome}({cat})",
                "sby_tail": _tail(rep.get("stdout")),
                "details": str(rep.get("details"))[:400],
            })
        extra_props = [("ohb", "assert property (@(posedge clk) $onehot0({gnt1, gnt0}));")]
        extra_ports = [("clk", 1), ("rst_n", 1), ("gnt1", 1), ("gnt0", 1)]
        extra_rtl = """module t(input logic clk, input logic rst_n, input logic gnt1, input logic gnt0);
  // brace-concatenation onehot0 operand (outside the bounded template grammar)
endmodule
"""
        try:
            rep, ws = _run_gate("v0_brace_onehot0", extra_ports, extra_props, extra_rtl, tmp_path)
            outcome, cat = _classify_report(rep)
            records.append({
                "form": "onehot0_brace_concat", "variant": "probe",
                "gate_passed": rep.get("passed"), "error_category": cat,
                "verdict": f"GATE_{outcome}({cat})",
                "sby_tail": _tail(rep.get("stdout")),
            })
        except Exception as exc:
            records.append({
                "form": "onehot0_brace_concat", "variant": "probe",
                "verdict": "ERROR",
                "detail": f"gate raised {type(exc).__name__}: {str(exc)[:300]}",
            })
    finally:
        _writable_results_path().write_text(json.dumps(records, indent=2), encoding="utf-8")

    bad = [r for r in records
           if r.get("form") != "onehot0_brace_concat"  # documented robustness probe, reported below
           and (r.get("verdict") in {"MISSED", "SILENTLY-IGNORED"}
                or str(r.get("verdict", "")).startswith("UNEXPECTED_FAIL")
                or str(r.get("verdict", "")).startswith("ERROR"))]
    assert not bad, f"soundness failures: {json.dumps(bad, indent=2)[:3000]}"
