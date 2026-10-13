"""S3 H1 gate fixes: tests-first (P3, P5, P6, P7 behind MIND3_GATE_FIXES).

Part 1: per-golden per-property REAL Gate-2 tests + full-contract Gate-2 tests.
  Pre-fix several FAIL (vacuous reset-patterns, counter_04 cover poison,
  undropped tautologies); post-fix all pass except counter_04 (tooling-
  unsupported, excluded by decision).
Part 2: 18 script-generated mutants (tests/golden_mutants/) through the full
  verify() pipeline; every mutant must FAIL at a real (non-env) gate.
Part 3: P3/P5/P6/P7 behavior tests, flag-off equivalence goldens (fifo_01
  harness bytes must equal the committed V1 artifacts with MIND3_GATE_FIXES=0),
  and a verifier-file checksum test.
Results -> results/v4/soundness/h1_results.json (always written).
"""

from __future__ import annotations

import hashlib
import json
import os
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
    Path(__file__).resolve().parents[2] / "results" / "v4" / "soundness" / "h1_results.json"
)
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"
MUTANT_DIR = Path(__file__).resolve().parent.parent / "golden_mutants"
REPO_ROOT = Path(__file__).resolve().parents[2]

GOLDENS = ["counter_04", "arbiter_02", "fifo_01", "fsm_heldout_04", "reset_02", "apb_01"]

FLAG = "MIND3_GATE_FIXES"


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


def _contract_for(task_id: str, prop_index: int | None = None) -> InterfaceContract:
    rec = _dev_record(task_id)
    if prop_index is not None:
        rec = dict(rec, expected_properties=[rec["expected_properties"][prop_index]])
    return contract_from_benchmark_record(rec)


def _gate2(top: str, contract: InterfaceContract, rtl: str, workdir: Path) -> tuple[dict, Path]:
    ws = workdir / top
    ws.mkdir(parents=True, exist_ok=True)
    (ws / f"{top}.sv").write_text(rtl, encoding="utf-8")
    sb = get_local_sandbox(ws)
    runner = LocalBwrapRunner(ws, sandbox=sb)
    verifier = SiliconSignoffVerifier(top_module=top, contract=contract, allow_mock_fallback=False)
    return verifier._run_gate2_formal_sby(runner, [ws / f"{top}.sv"], ws), ws


def _tail(text: str | None, n: int = 6) -> str:
    return "\n".join((text or "").splitlines()[-n:])


RECORDS: list[dict] = []


def _record(entry: dict) -> None:
    RECORDS.append(entry)


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(FLAG, "1")


def test_h1_golden_full_contracts(tmp_path: Path) -> None:
    errors: list[str] = []
    for task_id in GOLDENS:
        if task_id == "counter_04":
            continue
        top = f"h1_{task_id}"
        rtl = (GOLDEN_DIR / f"{task_id}.sv").read_text(encoding="utf-8")
        rtl = rtl.replace(f"module {task_id} (", f"module {top} (", 1)
        contract = _contract_for(task_id)
        object.__setattr__(contract, "module_name", top)
        rep, _ws = _gate2(top, contract, rtl, tmp_path)
        _record({"test": "full_contract", "task": task_id,
                 "passed": rep.get("passed"), "cat": rep.get("error_category"),
                 "dropped": rep.get("dropped_tautologies"),
                 "detail": str(rep.get("details"))[:200]})
        if rep.get("passed") is not True:
            errors.append(f"{task_id}: {rep.get('error_category')}")
    assert not errors, errors


def test_h1_counter04_stays_fail_closed(tmp_path: Path) -> None:
    top = "h1_counter_04"
    rtl = (GOLDEN_DIR / "counter_04.sv").read_text(encoding="utf-8")
    rtl = rtl.replace("module counter_04 (", f"module {top} (", 1)
    contract = _contract_for("counter_04")
    object.__setattr__(contract, "module_name", top)
    rep, _ws = _gate2(top, contract, rtl, tmp_path)
    _record({"test": "counter04_fail_closed", "passed": rep.get("passed"),
             "cat": rep.get("error_category"), "detail": str(rep.get("details"))[:200]})
    assert rep.get("passed") is False
    assert rep.get("error_category") in {"FORMAL_ANALYSIS_FAILED", "UNSUPPORTED_FORMAL_PROPERTY",
                                         "VACUOUS_PROPERTY", "NO_GENUINE_PROPERTY"}


def test_h1_single_property_contracts(tmp_path: Path) -> None:
    errors: list[str] = []
    for task_id in GOLDENS:
        rec = _dev_record(task_id)
        for i, spec_prop in enumerate(rec["expected_properties"]):
            top = f"h1_{task_id}_p{i}"
            rtl = (GOLDEN_DIR / f"{task_id}.sv").read_text(encoding="utf-8")
            rtl = rtl.replace(f"module {task_id} (", f"module {top} (", 1)
            contract = _contract_for(task_id, i)
            object.__setattr__(contract, "module_name", top)
            rep, _ws = _gate2(top, contract, rtl, tmp_path)
            _record({"test": "single_prop", "task": task_id, "prop": spec_prop[:70],
                     "passed": rep.get("passed"), "cat": rep.get("error_category"),
                     "dropped": rep.get("dropped_tautologies")})
            if "== $past" in spec_prop and "[" in spec_prop.split("$past")[1][:12]:
                if rep.get("passed") is not False:
                    errors.append(f"{task_id}[{i}]: expected fail-closed")
            elif spec_prop.strip().endswith("out_data == out_data);"):
                if not (rep.get("passed") is False and rep.get("error_category") == "NO_GENUINE_PROPERTY"):
                    errors.append(f"{task_id}[{i}]: expected NO_GENUINE_PROPERTY, got {rep.get('error_category')}")
            elif rep.get("passed") is not True:
                errors.append(f"{task_id}[{i}]: {rep.get('error_category')}")
    assert not errors, errors


def test_h1_mutants_all_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FLAG, raising=False)
    monkeypatch.setenv(FLAG, "1")
    files = sorted(MUTANT_DIR.glob("*__*.sv"))
    assert len(files) >= 23, f"expected >=23 mutants, found {len(files)}"
    # S3 halt ruling (owner option 1): fsm__halfreset is provably invisible to
    # every stated formal property under approved P5b semantics; recorded but
    # excluded from the exit count.
    excluded = {"fsm_heldout_04__halfreset.sv"}
    survivors: list[str] = []
    for path in files:
        task_id = path.name.split("__")[0]
        ws = tmp_path / path.stem
        ws.mkdir(parents=True, exist_ok=True)
        rtl = path.read_text(encoding="utf-8").replace(f"module {task_id} (", f"module {task_id} (", 1)
        (ws / f"{task_id}.sv").write_text(rtl, encoding="utf-8")
        contract = _contract_for(task_id)
        sb = get_local_sandbox(ws)
        verifier = SiliconSignoffVerifier(top_module=task_id, contract=contract,
                                          allow_mock_fallback=False)
        result = verifier.verify(ws, sb)
        fails = [g for g in (result.gate_reports or [])
                 if g.get("status") == "FAIL" or g.get("passed") is False]
        first_real = next((g for g in fails
                           if g.get("error_category") not in {
                               "ENVIRONMENT_FAILURE", "EDA_BINARY_MISSING", "NOT_RUN"}), None)
        _record({"test": "mutant", "mutant": path.name, "pipeline_passed": result.passed,
                 "pipeline_cat": result.error_category,
                 "first_real_fail": (first_real or {}).get("gate"),
                 "first_real_cat": (first_real or {}).get("error_category"),
                 "exit_excluded": path.name in excluded})
        if path.name in excluded:
            continue
        if result.passed is not False:
            survivors.append(f"{path.name} SURVIVED the gate")
        elif first_real is None:
            survivors.append(f"{path.name} failed only on env/unavailable gates")
    assert not survivors, survivors


def test_h1_p6_late_bug_still_caught(tmp_path: Path) -> None:
    from mind3.core.contracts import PortDefinition, PortDirection, SVAProperty

    top = "h1_latestuck"
    rtl = """module t(input logic clk, input logic rst_n, output logic [1:0] q);
  always_ff @(posedge clk) begin
    if (!rst_n) q <= 2'b00;
    else if (q < 2'b01) q <= q + 2'b01;
  end
endmodule
""".replace("module t(", f"module {top}(", 1)
    contract = InterfaceContract(
        module_name=top, functional_spec="late-stuck counter",
        ports=[PortDefinition(name="clk", direction=PortDirection.INPUT),
               PortDefinition(name="rst_n", direction=PortDirection.INPUT),
               PortDefinition(name="q", direction=PortDirection.OUTPUT, width=2)],
        sva_properties=[SVAProperty(
            name="cnt",
            property_expr="assert property (@(posedge clk) disable iff (!rst_n) q == $past(q) + 2'b01);")],
    )
    rep, _ws = _gate2(top, contract, rtl, tmp_path)
    _record({"test": "p6_late_bug", "passed": rep.get("passed"), "cat": rep.get("error_category")})
    assert rep.get("passed") is False
    assert rep.get("error_category") == "FORMAL_INVARIANT_BREACH"


def test_h1_flag_off_matches_v1_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mind3.core.contracts import VerificationHarnessGenerator, contract_from_benchmark_record

    monkeypatch.setenv(FLAG, "0")
    rec = _dev_record("fifo_01")
    contract = contract_from_benchmark_record(rec)
    sva = VerificationHarnessGenerator.build_sva_bind_module(contract)
    wrap = VerificationHarnessGenerator.build_formal_wrapper(contract)
    sby = VerificationHarnessGenerator.build_sby_config(contract, depth=25, include_sva_file=True)
    v1dir = REPO_ROOT / "results" / "v4" / "soundness" / "v1_fifo01_harness"
    _record({"test": "flag_off_harness",
             "sva_match": sva == (v1dir / "fifo_01_sva.sv").read_text(encoding="utf-8"),
             "wrap_match": wrap == (v1dir / "fifo_01_formal_top.sv").read_text(encoding="utf-8"),
             "sby_match": sby == (v1dir / "fifo_01.sby").read_text(encoding="utf-8")})
    assert sva == (v1dir / "fifo_01_sva.sv").read_text(encoding="utf-8")
    assert wrap == (v1dir / "fifo_01_formal_top.sv").read_text(encoding="utf-8")
    assert sby == (v1dir / "fifo_01.sby").read_text(encoding="utf-8")


def test_h1_flag_on_changes_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    from mind3.core.contracts import VerificationHarnessGenerator, contract_from_benchmark_record

    monkeypatch.setenv(FLAG, "1")
    rec = _dev_record("fifo_01")
    contract = contract_from_benchmark_record(rec)
    sva = VerificationHarnessGenerator.build_sva_bind_module(contract)
    v1dir = REPO_ROOT / "results" / "v4" / "soundness" / "v1_fifo01_harness"
    old = (v1dir / "fifo_01_sva.sv").read_text(encoding="utf-8")
    _record({"test": "flag_on_harness", "differs": sva != old})
    assert sva != old  # P5 reset-antecedent rendering must change fifo_01 output


def test_h1_verifier_files_checksum(tmp_path: Path) -> None:
    targets = ["src/mind3/core/verifier.py", "src/mind3/core/contracts.py",
               "src/mind3/core/formal_templates.py", "src/mind3/core/driver.py"]

    def sums() -> dict[str, str]:
        import hashlib as _hl

        return {t: _hl.sha256((REPO_ROOT / t).read_bytes()).hexdigest() for t in targets}

    before = sums()
    top = "h1_checksum_probe"
    rtl = (GOLDEN_DIR / "reset_02.sv").read_text(encoding="utf-8")
    rtl = rtl.replace("module reset_02 (", f"module {top} (", 1)
    contract = _contract_for("reset_02")
    object.__setattr__(contract, "module_name", top)
    _gate2(top, contract, rtl, tmp_path)
    after = sums()
    _record({"test": "checksum", "stable": before == after})
    assert before == after, "verifier files modified at run time"


@pytest.fixture(scope="module", autouse=True)
def _write_records():
    yield
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(RECORDS, indent=2), encoding="utf-8")
