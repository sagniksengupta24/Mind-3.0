"""P8 Gate-2 timeout: tests-first (must fail on pre-P8 code, then pass).

- A deliberately heavy design (fifo_01 golden, ~111s BMC) must yield
  FORMAL_TIMEOUT, never FORMAL_INVARIANT_BREACH (pre-P8: exit-124 timeout
  misreports as BREACH T=unknown).
- Flag-0 path keeps the old label (60s limit + BREACH mislabel): passes both
  pre- and post-P8 (rule-3 equivalence), proving flag-off == prior behavior.
Results -> results/v4/soundness/p8_results.json (always written).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mind3.core.contracts import contract_from_benchmark_record
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.platform import get_local_sandbox
from mind3.sandbox.remote_eda import LocalBwrapRunner

RESULTS_PATH = (
    Path(__file__).resolve().parents[2] / "results" / "v4" / "soundness" / "p8_results.json"
)
REPO_ROOT = Path(__file__).resolve().parents[2]
FLAG = "MIND3_GATE_FIXES"

RECORDS: list[dict] = []


@pytest.fixture(scope="module", autouse=True)
def _write_records():
    yield
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(RECORDS, indent=2), encoding="utf-8")


def _fifo_contract():
    tasks = [
        json.loads(line)
        for line in (
            REPO_ROOT / "benchmarks" / "development-20" / "tasks.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    task = next(t for t in tasks if t["task_id"] == "fifo_01")
    return contract_from_benchmark_record({
        "task_id": task["task_id"],
        "natural_language_spec": task["natural_language_spec"],
        "expected_ports": task["expected_ports"],
        "clock_reset_assumptions": task["clock_reset_assumptions"],
        "functional_requirements": task["functional_requirements"],
        "expected_properties": task["expected_properties"],
    })


def _run_fifo_gate2(top: str, workdir: Path) -> dict:
    ws = workdir / top
    ws.mkdir(parents=True, exist_ok=True)
    rtl = (REPO_ROOT / "tests" / "golden" / "fifo_01.sv").read_text(encoding="utf-8")
    rtl = rtl.replace("module fifo_01 (", f"module {top} (", 1)
    (ws / f"{top}.sv").write_text(rtl, encoding="utf-8")
    contract = _fifo_contract()
    object.__setattr__(contract, "module_name", top)
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    verifier = SiliconSignoffVerifier(top_module=top, contract=contract,
                                      allow_mock_fallback=False)
    rep, _ = verifier._run_gate2_formal_sby(runner, [ws / f"{top}.sv"], ws), ws
    return rep


def test_p8_timeout_is_formal_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 5s limit forces a deterministic timeout: fifo BMC needs 18s+ in any form.
    monkeypatch.setenv(FLAG, "1")
    monkeypatch.setenv("MIND3_SBY_TIMEOUT_S", "5")
    rep = _run_fifo_gate2("p8_heavy", tmp_path)
    RECORDS.append({"test": "timeout_category", "passed": rep.get("passed"),
                    "cat": rep.get("error_category"),
                    "detail": str(rep.get("details"))[:200],
                    "wall": rep.get("gate2_wall_s")})
    assert rep.get("passed") is False
    assert rep.get("error_category") == "FORMAL_TIMEOUT", rep.get("error_category")
    assert "formal check did not finish; no counterexample" in str(rep.get("details"))
    assert "counterexample_trace" not in rep
    assert "trace_file" not in rep
    assert isinstance(rep.get("gate2_wall_s"), float)


def test_p8_flag_off_keeps_old_limits_and_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mind3.core.verifier import _gate2_timeout_sec

    # Unit level: timeout selection matrix (deterministic, instant).
    monkeypatch.setenv(FLAG, "0")
    monkeypatch.setenv("MIND3_SBY_TIMEOUT_S", "5")
    assert _gate2_timeout_sec() == 60
    monkeypatch.setenv(FLAG, "1")
    assert _gate2_timeout_sec() == 5
    monkeypatch.delenv("MIND3_SBY_TIMEOUT_S", raising=False)
    assert _gate2_timeout_sec() == 240
    monkeypatch.setenv("MIND3_SBY_TIMEOUT_S", "9999")
    assert _gate2_timeout_sec() == 240
    monkeypatch.setenv("MIND3_SBY_TIMEOUT_S", "bogus")
    assert _gate2_timeout_sec() == 240

    # Report level: flag off carries none of the P3/P8 reporting keys on a
    # real (fast) BREACH verdict, preserving the V0/V1 report shape exactly.
    monkeypatch.setenv(FLAG, "0")
    monkeypatch.delenv("MIND3_SBY_TIMEOUT_S", raising=False)
    ws = tmp_path / "p8_off_shape"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "p8q.sv").write_text(
        "module p8q(input logic clk, input logic a, output logic b);\n"
        "  assign b = ~a;\nendmodule\n",
        encoding="utf-8",
    )
    from mind3.core.contracts import (
        ClockContract,
        InterfaceContract,
        PortDefinition,
        PortDirection,
        SVAProperty,
    )

    contract = InterfaceContract(
        module_name="p8q", functional_spec="combinational inverter probe",
        ports=[PortDefinition(name="clk", direction=PortDirection.INPUT),
               PortDefinition(name="a", direction=PortDirection.INPUT),
               PortDefinition(name="b", direction=PortDirection.OUTPUT)],
        clock=ClockContract(name="clk"),
        reset=None,
        sva_properties=[SVAProperty(
            name="eq", property_expr="assert property (@(posedge clk) b == a);")],
    )
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    verifier = SiliconSignoffVerifier(top_module="p8q", contract=contract,
                                      allow_mock_fallback=False)
    rep = verifier._run_gate2_formal_sby(runner, [ws / "p8q.sv"], ws)
    RECORDS.append({"test": "flag_off_label", "passed": rep.get("passed"),
                    "cat": rep.get("error_category"),
                    "new_keys": sorted(k for k in
                                       ("gate2_wall_s", "dropped_tautologies", "timeout_edge")
                                       if k in rep)})
    assert rep.get("passed") is False
    assert rep.get("error_category") == "FORMAL_INVARIANT_BREACH", rep.get("error_category")
    for key in ("gate2_wall_s", "dropped_tautologies", "timeout_edge"):
        assert key not in rep, key
