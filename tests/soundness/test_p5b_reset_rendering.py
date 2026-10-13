"""P5b reset-antecedent rendering: tests-first (must fail on P5 code, then pass).

- Sync contract + correct sync golden + reset-antecedent property through the
  REAL Gate 2 must PASS (P5 same-cycle form fails it: demonstrated BREACH).
- Async-reset design on a sync contract is still rejected by Gate 1.
- Async contract keeps the same-cycle rendered form (rendered-SV diff test).
- fifo_01 before/after rendered SystemVerilog is printed and must differ.
Results -> results/v4/soundness/p5b_results.json (always written).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mind3.core.contracts import (
    InterfaceContract,
    contract_from_benchmark_record,
)
from mind3.core.verifier import SiliconSignoffVerifier
from mind3.sandbox.platform import get_local_sandbox
from mind3.sandbox.remote_eda import LocalBwrapRunner

RESULTS_PATH = (
    Path(__file__).resolve().parents[2] / "results" / "v4" / "soundness" / "p5b_results.json"
)
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"
REPO_ROOT = Path(__file__).resolve().parents[2]
FLAG = "MIND3_GATE_FIXES"

RECORDS: list[dict] = []


@pytest.fixture(scope="module", autouse=True)
def _write_records():
    yield
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(RECORDS, indent=2), encoding="utf-8")


def _dev_record(task_id: str) -> dict:
    tasks = [
        json.loads(line)
        for line in (
            REPO_ROOT / "benchmarks" / "development-20" / "tasks.jsonl"
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


def _gate2(top: str, contract: InterfaceContract, rtl: str, workdir: Path) -> tuple[dict, Path]:
    ws = workdir / top
    ws.mkdir(parents=True, exist_ok=True)
    (ws / f"{top}.sv").write_text(rtl, encoding="utf-8")
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    verifier = SiliconSignoffVerifier(top_module=top, contract=contract, allow_mock_fallback=False)
    return verifier._run_gate2_formal_sby(runner, [ws / f"{top}.sv"], ws), ws


def test_p5b_sync_goldens_pass(tmp_path: Path) -> None:
    errors: list[str] = []
    for task_id in ("reset_02", "apb_01", "fifo_01", "fsm_heldout_04"):
        top = f"p5b_{task_id}"
        rtl = (GOLDEN_DIR / f"{task_id}.sv").read_text(encoding="utf-8")
        rtl = rtl.replace(f"module {task_id} (", f"module {top} (", 1)
        rec = _dev_record(task_id)
        contract = contract_from_benchmark_record(rec)
        assert contract.reset is not None and contract.reset.synchronous is True
        object.__setattr__(contract, "module_name", top)
        rep, _ws = _gate2(top, contract, rtl, tmp_path)
        RECORDS.append({"test": "sync_pass", "task": task_id,
                        "passed": rep.get("passed"), "cat": rep.get("error_category"),
                        "detail": str(rep.get("details"))[:200]})
        if rep.get("passed") is not True:
            errors.append(f"{task_id}: {rep.get('error_category')}")
    assert not errors, errors


def test_p5b_async_design_rejected_by_gate1(tmp_path: Path) -> None:
    ws = tmp_path / "p5b_async_g1"
    ws.mkdir(parents=True, exist_ok=True)
    rtl = (GOLDEN_DIR / "reset_02.sv").read_text(encoding="utf-8")
    rtl = rtl.replace("module reset_02 (", "module p5b_async (", 1)
    rtl = rtl.replace("always_ff @(posedge clk) begin",
                      "always_ff @(posedge clk or negedge rst_n) begin", 1)
    (ws / "p5b_async.sv").write_text(rtl, encoding="utf-8")
    contract = contract_from_benchmark_record(_dev_record("reset_02"))
    object.__setattr__(contract, "module_name", "p5b_async")
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    verifier = SiliconSignoffVerifier(top_module="p5b_async", contract=contract,
                                      allow_mock_fallback=False)
    from mind3.core.verifier import _select_signoff_sources

    rep = verifier._run_gate1_yosys(runner, _select_signoff_sources(ws), ws)
    RECORDS.append({"test": "async_gate1", "passed": rep.get("passed"),
                    "cat": rep.get("error_category")})
    assert rep.get("passed") is False
    assert rep.get("error_category") == "CLOCK_RESET_ERROR"


def test_p5b_async_contract_same_cycle_render() -> None:
    from mind3.core.contracts import (
        ClockContract,
        PortDefinition,
        PortDirection,
        ResetContract,
    )
    from mind3.core.formal_templates import FormalTemplateKind, FormalPropertySpec

    spec = FormalPropertySpec(
        name="r", kind=FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        clock="clk", reset="rst_n:active_low",
        antecedent="!rst_n", consequent="out_data == 8'h00",
    )
    contract = InterfaceContract(
        module_name="m", functional_spec="async reset check",
        ports=[PortDefinition(name="clk", direction=PortDirection.INPUT),
               PortDefinition(name="rst_n", direction=PortDirection.INPUT),
               PortDefinition(name="out_data", direction=PortDirection.OUTPUT, width=8)],
        clock=ClockContract(name="clk"),
        reset=ResetContract(name="rst_n", polarity="active_low", synchronous=False),
        formal_properties=[spec],
    )
    from mind3.core.contracts import VerificationHarnessGenerator

    sva = VerificationHarnessGenerator.build_sva_bind_module(contract)
    RECORDS.append({"test": "async_render",
                    "same_cycle": "if (!rst_n) assert (out_data == 8'h00);" in sva,
                    "no_past": "$past(!rst_n)" not in sva})
    assert "if (!rst_n) assert (out_data == 8'h00);" in sva
    assert "$past(!rst_n)" not in sva


def test_p5b_fifo01_render_diff() -> None:
    from mind3.core.contracts import VerificationHarnessGenerator

    contract = contract_from_benchmark_record(_dev_record("fifo_01"))
    assert contract.reset is not None and contract.reset.synchronous is True
    sva = VerificationHarnessGenerator.build_sva_bind_module(contract)
    old = (REPO_ROOT / "results" / "v4" / "soundness" / "v1_fifo01_harness"
           / "fifo_01_sva.sv").read_text(encoding="utf-8")
    print("===BEFORE (V1 committed) reset-property block===")
    for line in old.splitlines():
        if "rst_n) assert" in line or "if (!init" in line:
            print("   ", line)
    print("===AFTER (P5b) reset-property block===")
    for line in sva.splitlines():
        if "rst_n) assert" in line or "if (!init" in line or "$past(!rst_n)" in line:
            print("   ", line)
    RECORDS.append({"test": "fifo_render_diff", "differs": sva != old,
                    "has_past_reset": "$past(!rst_n)" in sva})
    assert "$past(!rst_n)" in sva
    assert sva != old
