"""V1 gate completeness + golden designs (test-only; no verifier/template edits).

Part A: regenerate + save the fifo_01 formal harness; assert guard structure.
Part B/C: minimal correct async/sync-reset counters through the REAL Gate 2,
  with stdlib-only VCD decode of any counterexample into cycle tables.
Part D: 6 UNREVIEWED golden designs (tests/golden/, from task specs only)
  through Gates 1,3,2,4,6 + DFT individually and the full verify() pipeline.
Results -> results/v4/soundness/v1_results.json (always written).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    SVAProperty,
    VerificationHarnessGenerator,
    contract_from_benchmark_record,
)
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.platform import get_local_sandbox
from mind3.sandbox.remote_eda import LocalBwrapRunner

RESULTS_PATH = (
    Path(__file__).resolve().parents[2] / "results" / "v4" / "soundness" / "v1_results.json"
)
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"


def _dev_record(task_id: str) -> dict:
    import json as _json

    tasks = [
        _json.loads(line)
        for line in (
            Path(__file__).resolve().parents[2]
            / "benchmarks"
            / "development-20"
            / "tasks.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    task = next(t for t in tasks if t["task_id"] == task_id)
    return {
        "task_id": task["task_id"],
        "natural_language_spec": task["natural_language_spec"],
        "expected_ports": task["expected_ports"],
        "clock_reset_assumptions": task["clock_reset_assumptions"],
        "functional_requirements": task["functional_requirements"],
        "expected_properties": task["expected_properties"],
    }


def _contract_for(task_id: str) -> InterfaceContract:
    return contract_from_benchmark_record(_dev_record(task_id))


# ---------------------------------------------------------------- VCD decode
def _parse_vcd(text: str) -> tuple[dict[str, tuple[str, int]], list[tuple[int, str, str]]]:
    """Minimal stdlib VCD parser: returns (id -> (hier_name, width), changes)."""
    scope: list[str] = []
    variables: dict[str, tuple[str, int]] = {}
    changes: list[tuple[int, str, str]] = []
    now = 0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("$scope"):
            scope.append(line.split()[-2])
        elif line.startswith("$upscope"):
            if scope:
                scope.pop()
        elif line.startswith("$var"):
            parts = line.split()
            try:
                variables[parts[3]] = (".".join(scope + [parts[4]]), int(parts[2]))
            except (IndexError, ValueError):
                continue
        elif line.startswith("#"):
            try:
                now = int(line[1:].split()[0])
            except ValueError:
                continue
        elif line and line[0] in "01xzXZ":
            changes.append((now, line[1:].strip(), line[0]))
        elif line.startswith(("b", "B")):
            body = line[1:].strip().split()
            if len(body) == 2:
                changes.append((now, body[1], body[0]))
    return variables, changes


def _cycle_table(vcd_text: str, watch: list[str], max_cycles: int = 8) -> list[dict]:
    """Sample watched signals just after each clk rising edge."""
    variables, changes = _parse_vcd(vcd_text)
    clk_ids = [vid for vid, (name, _w) in variables.items() if name.split(".")[-1] == "clk"]
    if not clk_ids:
        return [{"error": "no clk signal in VCD"}]
    by_id: dict[str, list[tuple[int, str]]] = {}
    for t, vid, val in changes:
        by_id.setdefault(vid, []).append((t, val))

    def value_at(vid: str, t: int) -> str | None:
        cur = None
        for ct, cv in by_id.get(vid, []):
            if ct <= t:
                cur = cv
            else:
                break
        return cur

    clk_hist = sorted(by_id.get(clk_ids[0], []))
    edges = [t for i, (t, v) in enumerate(clk_hist)
             if v == "1" and i > 0 and clk_hist[i - 1][1] in ("0", "x", "z")]

    def sample(t: int) -> dict:
        row: dict = {"timestep": t}
        for sig in watch:
            matches = [(vid, name, w) for vid, (name, w) in variables.items()
                       if name.split(".")[-1].split("[")[0] == sig]
            bus = [m for m in matches if m[2] > 1]
            bits: dict[int, str] = {}
            for vid, name, _w in matches:
                m = re.search(r"\[(\d+)\]$", name)
                if m:
                    bits[int(m.group(1))] = value_at(vid, t) or "x"
            if bus:
                vid = bus[0][0]
                row[sig] = value_at(vid, t)
            elif bits:
                row[sig] = "".join(bits[i] for i in sorted(bits, reverse=True))
            elif matches:
                # Witness duplication can register the same scalar under
                # several ids; sample the first occurrence.
                row[sig] = value_at(matches[0][0], t)
            else:
                row[sig] = None
        return row

    rows: list[dict] = [sample(0)]
    for t in edges[:max_cycles]:
        rows.append(sample(t))
    return rows


# ---------------------------------------------------------------- helpers
def _run_gate2(top: str, contract: InterfaceContract, rtl: str, workdir: Path) -> tuple[dict, Path]:
    ws = workdir / top
    ws.mkdir(parents=True, exist_ok=True)
    (ws / f"{top}.sv").write_text(rtl, encoding="utf-8")
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    verifier = SiliconSignoffVerifier(top_module=top, contract=contract, allow_mock_fallback=False)
    return verifier._run_gate2_formal_sby(runner, [ws / f"{top}.sv"], ws), ws


def _tail(text: str | None, n: int = 12) -> str:
    return "\n".join((text or "").splitlines()[-n:])


def test_v1_reset_root_cause(tmp_path: Path) -> None:
    records: dict = {"harness": {}, "async_counter": {}, "sync_counter": {}}
    try:
        # -- Part A: exact harness for stateful dev task fifo_01 ---------------
        contract = _contract_for("fifo_01")
        sva = VerificationHarnessGenerator.build_sva_bind_module(contract)
        wrap = VerificationHarnessGenerator.build_formal_wrapper(contract)
        sby = VerificationHarnessGenerator.build_sby_config(contract, depth=25, include_sva_file=True)
        outdir = RESULTS_PATH.parent / "v1_fifo01_harness"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "fifo_01_sva.sv").write_text(sva, encoding="utf-8")
        (outdir / "fifo_01_formal_top.sv").write_text(wrap, encoding="utf-8")
        (outdir / "fifo_01.sby").write_text(sby, encoding="utf-8")
        records["harness"] = {
            "has_init_reg": "reg init = 1'b1;" in sva,
            "has_init_clear": "always @(posedge clk) init <= 1'b0;" in sva,
            "has_initstate": "initstate" in sva.lower(),
            "has_reset_driver": "$anyconst" in sva.lower() or "assume" in sva.lower(),
            "sby_frontend": "read -formal" if "read -formal" in sby else "OTHER",
            "reset_pattern_guard": "if (!init && rst_n) begin\n      if (!rst_n)" in sva,
        }
        assert records["harness"]["has_init_reg"]
        assert records["harness"]["sby_frontend"] == "read -formal"

        # -- Parts B/C: minimal correct counters --------------------------------
        prop = "assert property (@(posedge clk) disable iff (!rst_n) q == $past(q) + 2'b01);"
        ports = [
            PortDefinition(name="clk", direction=PortDirection.INPUT),
            PortDefinition(name="rst_n", direction=PortDirection.INPUT),
            PortDefinition(name="q", direction=PortDirection.OUTPUT, width=2),
        ]

        async_rtl = """module t(input logic clk, input logic rst_n, output logic [1:0] q);
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) q <= 2'b00;
    else q <= q + 2'b01;
  end
endmodule
"""
        sync_rtl = """module t(input logic clk, input logic rst_n, output logic [1:0] q);
  always_ff @(posedge clk) begin
    if (!rst_n) q <= 2'b00;
    else q <= q + 2'b01;
  end
endmodule
"""
        for label, rtl in (("async_counter", async_rtl), ("sync_counter", sync_rtl)):
            top = f"v1_{label}"
            rtl_named = rtl.replace("module t(", f"module {top}(", 1)
            contract2 = InterfaceContract(
                module_name=top, functional_spec=f"V1 {label}",
                ports=ports,
                sva_properties=[SVAProperty(name="cnt", property_expr=prop)],
            )
            rep, ws = _run_gate2(top, contract2, rtl_named, tmp_path)
            entry: dict = {
                "gate_passed": rep.get("passed"),
                "error_category": rep.get("error_category"),
                "details": str(rep.get("details"))[:300],
                "sby_tail": _tail(rep.get("stdout")),
            }
            vcd_text = rep.get("counterexample_trace") or ""
            trace_rel = rep.get("trace_file")
            if trace_rel:
                for cand in (ws / top / trace_rel, ws / trace_rel):
                    if cand.exists() and cand.is_file():
                        vcd_text = cand.read_text(encoding="utf-8", errors="replace")
                        entry["vcd_source"] = str(cand.relative_to(ws))
                        entry["vcd_lines"] = len(vcd_text.splitlines())
                        break
            try:
                entry["failing_step"] = int(str(rep.get("step")))
            except (TypeError, ValueError):
                entry["failing_step"] = None
            if rep.get("passed") is not True and vcd_text:
                table = _cycle_table(vcd_text, ["rst_n", "q"], max_cycles=8)
                entry["cycle_table"] = table
                entry["likely_cause"] = _classify_reset_release(
                    table, entry["failing_step"], uses_past=True
                )
            elif rep.get("passed") is True:
                entry["likely_cause"] = "n/a (passed)"
            else:
                entry["likely_cause"] = "needs-human (no VCD)"
            records[label] = entry
    finally:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        prev = {}
        if RESULTS_PATH.exists():
            prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        prev.update(records)
        RESULTS_PATH.write_text(json.dumps(prev, indent=2), encoding="utf-8")


def _classify_reset_release(table: list[dict], failing_step: int | None, uses_past: bool) -> str:
    """Evidence rule: reset asserted anywhere at/before the failing check of a
    $past property means the $past window spans a reset the guard does not mask
    (the guard only masks the current cycle). A mismatch there is forced by the
    wrapper's missing reset sequencing, not by the design."""
    if not table or "error" in table[0]:
        return "needs-human (VCD unparseable)"
    horizon = failing_step if isinstance(failing_step, int) else len(table)
    window = table[: horizon + 1]
    if uses_past and any(row.get("rst_n") == "0" for row in window):
        first_zero = next(i for i, row in enumerate(window) if row.get("rst_n") == "0")
        return (
            "missing-reset-sequencing (gate): reset asserted in a sampled state "
            f"(row {first_zero}) at/before failing step {failing_step}; the $past "
            "window therefore spans a reset the current-cycle-only guard "
            "(`!init && rst_n`) does not mask, forcing q != $past(q)+1 on a "
            "correct counter. Wrapper drives no reset sequence and assumes no "
            "initial state (no initstate/assume)."
        )
    return "needs-human (no reset assertion before failing step)"


GOLDENS = ["counter_04", "arbiter_02", "fifo_01", "fsm_heldout_04", "reset_02", "apb_01"]


def _gate_label(rep: dict) -> str:
    if rep.get("error_category") in {"EDA_BINARY_MISSING", "ENVIRONMENT_FAILURE"}:
        return "UNAVAILABLE"
    if rep.get("status") == "NOT_RUN" or rep.get("error_category") == "NOT_RUN":
        return "NOT_RUN"
    return "PASS" if rep.get("passed") else "FAIL"


def _rec(rep: dict, extra_keys: tuple[str, ...] = ()) -> dict:
    d: dict = {"verdict": _gate_label(rep), "detail": str(rep.get("details"))[:300]}
    if rep.get("metrics"):
        d["metrics"] = rep["metrics"]
    for key in extra_keys:
        if rep.get(key) is not None:
            d[key] = rep.get(key)
    if d["verdict"] not in {"PASS", "NOT_RUN"}:
        d["stdout"] = str(rep.get("stdout") or "")[-4000:]
        d["stderr"] = str(rep.get("stderr") or "")[-2000:]
    return d


def test_v1_goldens_full_gates(tmp_path: Path) -> None:
    goldens: dict = {}
    try:
        for task_id in GOLDENS:
            rtl = (GOLDEN_DIR / f"{task_id}.sv").read_text(encoding="utf-8")
            assert rtl.startswith("// UNREVIEWED"), f"{task_id} golden missing UNREVIEWED mark"
            contract = _contract_for(task_id)
            entry: dict = {"unreviewed": True, "gates": {}}

            # Pristine pipeline run: golden RTL only, mirroring a real attempt.
            pws = tmp_path / task_id / "pipe"
            pws.mkdir(parents=True, exist_ok=True)
            (pws / f"{task_id}.sv").write_text(rtl, encoding="utf-8")
            psb = get_local_sandbox(pws)
            pver = SiliconSignoffVerifier(
                top_module=task_id, contract=contract, allow_mock_fallback=False
            )
            full = pver.verify(pws, psb)
            entry["pipeline"] = {
                "passed": full.passed,
                "failure_reason": str(full.failure_reason)[:300],
                "error_category": full.error_category,
                "gate_order": [g.get("gate") for g in (full.gate_reports or [])],
                "gate_verdicts": [
                    {"gate": g.get("gate"), "verdict": _gate_label(g)}
                    for g in (full.gate_reports or [])
                ],
            }

            # Individual gates in pipeline order in an isolated workspace so
            # generated harness/cover artifacts cannot pollute sibling gates.
            iws = tmp_path / task_id / "ind"
            iws.mkdir(parents=True, exist_ok=True)
            (iws / f"{task_id}.sv").write_text(rtl, encoding="utf-8")
            isb = get_local_sandbox(iws)
            irunner = LocalBwrapRunner(iws, sandbox=isb)
            iver = SiliconSignoffVerifier(
                top_module=task_id, contract=contract, allow_mock_fallback=False
            )
            from mind3.core.verifier import _select_signoff_sources

            sources = _select_signoff_sources(iws)
            g1 = iver._run_gate1_yosys(irunner, sources, iws)
            entry["gates"]["gate1"] = _rec(g1)
            g3 = iver._run_gate3_coverage(irunner, sources, iws)
            entry["gates"]["gate3"] = _rec(g3)
            g2 = iver._run_gate2_formal_sby(irunner, sources, iws)
            entry["gates"]["gate2"] = _rec(
                g2, extra_keys=("failing_property", "unexercised_properties")
            )
            entry["gates"]["gate2"]["sby_tail"] = _tail(g2.get("stdout"))
            try:
                g4 = iver._run_gate4_timing(irunner, sources, iws)
                entry["gates"]["gate4"] = _rec(g4)
            except (ValueError, OSError) as exc:
                entry["gates"]["gate4"] = {"verdict": "UNAVAILABLE", "detail": f"Timing stage unavailable: {exc}"}
            g6 = iver._run_gate6_cdc_analysis(irunner, sources, iws)
            entry["gates"]["gate6"] = _rec(g6)
            dft = iver._run_dft_scan_audit(irunner, sources, iws)
            entry["gates"]["dft"] = _rec(dft)
            if task_id == "counter_04":
                # Supported-subset probe: drop the legacy UNSUPPORTED $past-slice
                # property; the reset-pattern implication alone remains.
                sub = tmp_path / task_id / "subset"
                sub.mkdir(exist_ok=True)
                (sub / f"{task_id}.sv").write_text(rtl, encoding="utf-8")
                import copy as _copy

                sub_contract = _copy.deepcopy(contract)
                sub_contract.sva_properties.clear()
                v2 = SiliconSignoffVerifier(
                    top_module=task_id, contract=sub_contract, allow_mock_fallback=False
                )
                rep2 = v2._run_gate2_formal_sby(
                    LocalBwrapRunner(sub, sandbox=get_local_sandbox(sub)),
                    [sub / f"{task_id}.sv"], sub,
                )
                entry["counter_04_supported_subset_gate2"] = _rec(
                    rep2, extra_keys=("unexercised_properties",)
                )
            goldens[task_id] = entry
    finally:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        prev = {}
        if RESULTS_PATH.exists():
            prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        prev["goldens"] = goldens
        RESULTS_PATH.write_text(json.dumps(prev, indent=2), encoding="utf-8")
