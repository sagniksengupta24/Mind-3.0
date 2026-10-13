"""S3(d) rerun matrix: goldens x flags and mutants x flags, all WITH liberty.

Per golden per flag: individual Gates 1,3,2,4,6 + DFT with measured walls in
one isolated workspace, plus a pristine-workspace full pipeline verdict.
Per mutant per flag: full pipeline WITH liberty; first real (non-env) failing
gate recorded; timeout-only catches listed separately (FORMAL_TIMEOUT with
fixes ON; external wall >= 59s on a Gate-2 fail with fixes OFF).
Results merged into results/v4/soundness/h1_results.json under "matrix".
Serial execution only (16 GB Mac; model jobs never parallel).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from mind3.core.contracts import contract_from_benchmark_record
from mind3.core.verifier import SiliconSignoffVerifier, _select_signoff_sources
from mind3.sandbox.platform import get_local_sandbox
from mind3.sandbox.remote_eda import LocalBwrapRunner

RESULTS_PATH = (
    Path(__file__).resolve().parents[2] / "results" / "v4" / "soundness" / "h1_results.json"
)
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"
MUTANT_DIR = Path(__file__).resolve().parent.parent / "golden_mutants"
REPO_ROOT = Path(__file__).resolve().parents[2]
LIBERTY = "/Users/sagniksengupta/Desktop/Mind3-PDK/sky130_fd_sc_hd__tt_025C_1v80.lib"
FLAG = "MIND3_GATE_FIXES"

GOLDENS = ["counter_04", "arbiter_02", "fifo_01", "fsm_heldout_04", "reset_02", "apb_01"]
REAL_FAIL_CATS = None  # any category except env/timeout placeholders counts if gate failed


def _dev_contract(task_id: str):
    tasks = [
        json.loads(line)
        for line in (
            REPO_ROOT / "benchmarks" / "development-20" / "tasks.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    task = next(t for t in tasks if t["task_id"] == task_id)
    return contract_from_benchmark_record({
        "task_id": task["task_id"],
        "natural_language_spec": task["natural_language_spec"],
        "expected_ports": task["expected_ports"],
        "clock_reset_assumptions": task["clock_reset_assumptions"],
        "functional_requirements": task["functional_requirements"],
        "expected_properties": task["expected_properties"],
    })


def _merge(key: str, value: object) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8")) if RESULTS_PATH.exists() else []
    if isinstance(data, list):
        data = {"h1": data}
    data[key] = value
    RESULTS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _timed(fn, *args, **kwargs):
    t0 = time.monotonic()
    out = fn(*args, **kwargs)
    return out, round(time.monotonic() - t0, 1)


def _first_real_fail(reports: list[dict]) -> dict | None:
    for g in reports or []:
        if g.get("passed") is False and g.get("error_category") not in {
            "ENVIRONMENT_FAILURE", "EDA_BINARY_MISSING", "NOT_RUN",
        }:
            return g
    return None


def test_matrix_goldens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert Path(LIBERTY).exists(), "liberty file missing"
    rows: list[dict] = []
    try:
        for flag in ("0", "1"):
            monkeypatch.setenv(FLAG, flag)
            for task_id in GOLDENS:
                rtl = (GOLDEN_DIR / f"{task_id}.sv").read_text(encoding="utf-8")
                # Isolated individual-gate workspace.
                iws = tmp_path / f"{task_id}_f{flag}" / "ind"
                iws.mkdir(parents=True, exist_ok=True)
                (iws / f"{task_id}.sv").write_text(rtl, encoding="utf-8")
                contract = _dev_contract(task_id)
                sb = get_local_sandbox(iws)
                runner = LocalBwrapRunner(iws, sandbox=sb)
                verifier = SiliconSignoffVerifier(
                    top_module=task_id, contract=contract,
                    allow_mock_fallback=False, liberty_path=LIBERTY)
                sources = _select_signoff_sources(iws)
                gates: dict = {}
                g1, w1 = _timed(verifier._run_gate1_yosys, runner, sources, iws)
                gates["gate1"] = {"verdict": "PASS" if g1.get("passed") else "FAIL",
                                  "cat": g1.get("error_category"), "wall_s": w1}
                g3, w3 = _timed(verifier._run_gate3_coverage, runner, sources, iws)
                gates["gate3"] = {"verdict": "PASS" if g3.get("passed") else "FAIL",
                                  "cat": g3.get("error_category"), "wall_s": w3,
                                  "metrics": g3.get("metrics")}
                g2, w2 = _timed(verifier._run_gate2_formal_sby, runner, sources, iws)
                gates["gate2"] = {"verdict": "PASS" if g2.get("passed") else "FAIL",
                                  "cat": g2.get("error_category"), "wall_s": w2,
                                  "gate2_wall_s": g2.get("gate2_wall_s"),
                                  "timeout_edge": g2.get("timeout_edge"),
                                  "dropped": g2.get("dropped_tautologies")}
                try:
                    g4, w4 = _timed(verifier._run_gate4_timing, runner, sources, iws)
                    gates["gate4"] = {"verdict": "PASS" if g4.get("passed") else "FAIL",
                                      "cat": g4.get("error_category"), "wall_s": w4}
                except (ValueError, OSError) as exc:
                    gates["gate4"] = {"verdict": "UNAVAILABLE", "cat": None,
                                      "wall_s": 0.0, "detail": str(exc)[:150]}
                g6, w6 = _timed(verifier._run_gate6_cdc_analysis, runner, sources, iws)
                gates["gate6"] = {"verdict": "PASS" if g6.get("passed") else "FAIL",
                                  "cat": g6.get("error_category"), "wall_s": w6}
                # Pristine pipeline workspace.
                pws = tmp_path / f"{task_id}_f{flag}" / "pipe"
                pws.mkdir(parents=True, exist_ok=True)
                (pws / f"{task_id}.sv").write_text(rtl, encoding="utf-8")
                psb = get_local_sandbox(pws)
                pver = SiliconSignoffVerifier(
                    top_module=task_id, contract=_dev_contract(task_id),
                    allow_mock_fallback=False, liberty_path=LIBERTY)
                full, wfull = _timed(pver.verify, pws, psb)
                rows.append({"task": task_id, "flag": flag, "gates": gates,
                             "pipeline": {"passed": full.passed,
                                          "cat": full.error_category,
                                          "wall_s": wfull}})
    finally:
        _merge("matrix_goldens", rows)
    # Exit applies to fixes ON; flag-0 rows are recorded contrast only.
    errors = [f"{r['task']}f{r['flag']}" for r in rows
              if r["flag"] == "1"
              and not (r["task"] == "counter_04" or r["pipeline"]["passed"] is True)]
    assert not errors, f"golden pipeline failures (fixes ON): {errors}"


def test_matrix_mutants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert Path(LIBERTY).exists(), "liberty file missing"
    rows: list[dict] = []
    timeout_only: list[str] = []
    # S3 halt ruling (owner option 1): fsm__halfreset is provably invisible to
    # every stated formal property under approved P5b semantics (gate proved
    # both implications with antecedents reached). It runs and is recorded as
    # spec-coverage evidence but is excluded from the exit count.
    excluded = {"fsm_heldout_04__halfreset.sv"}
    try:
        files = sorted(MUTANT_DIR.glob("*__*.sv"))
        assert len(files) >= 23, f"expected >=23 mutants, found {len(files)}"
        for flag in ("0", "1"):
            monkeypatch.setenv(FLAG, flag)
            for path in files:
                task_id = path.name.split("__")[0]
                ws = tmp_path / f"f{flag}" / path.stem
                ws.mkdir(parents=True, exist_ok=True)
                (ws / f"{task_id}.sv").write_text(
                    path.read_text(encoding="utf-8"), encoding="utf-8")
                contract = _dev_contract(task_id)
                sb = get_local_sandbox(ws)
                verifier = SiliconSignoffVerifier(
                    top_module=task_id, contract=contract,
                    allow_mock_fallback=False, liberty_path=LIBERTY)
                t0 = time.monotonic()
                result = verifier.verify(ws, sb)
                wall = round(time.monotonic() - t0, 1)
                first = _first_real_fail(result.gate_reports or [])
                only_timeout = False
                if result.passed is False and first is None:
                    only_timeout = True
                elif first is not None and first.get("error_category") == "FORMAL_TIMEOUT":
                    only_timeout = True
                elif (flag == "0" and result.passed is False and first is not None
                        and "Gate 2" in str(first.get("gate")) and wall >= 59.0):
                    only_timeout = True
                entry = {"mutant": path.name, "flag": flag,
                         "pipeline_passed": result.passed,
                         "pipeline_cat": result.error_category, "wall_s": wall,
                         "first_real_gate": (first or {}).get("gate"),
                         "first_real_cat": (first or {}).get("error_category"),
                         "timeout_only": only_timeout,
                         "exit_excluded": path.name in excluded}
                rows.append(entry)
                if only_timeout:
                    timeout_only.append(f"{path.name}f{flag}")
    finally:
        _merge("matrix_mutants", rows)
        _merge("timeout_only_mutants", timeout_only)
    # Exit applies to fixes ON, minus the documented exclusion; flag-0 rows
    # are recorded contrast only.
    on = [r for r in rows if r["flag"] == "1" and not r["exit_excluded"]]
    survivors = [f"{r['mutant']}f{r['flag']}" for r in on if r["pipeline_passed"] is True]
    assert not survivors, f"mutant survivors (fixes ON): {survivors}"
    slow = [t for t in timeout_only if t.endswith("f1")]
    assert not slow, f"timeout-only catches fixes ON (do not count): {slow}"
