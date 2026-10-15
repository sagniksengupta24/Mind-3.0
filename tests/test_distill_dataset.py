"""Tests for scripts/distill_mind3_dataset.py (fast: no live EDA, no model).

Covers: anti-contamination guards, dedup, row schemas, flag-ON evidence
construction against the real VCD fixture, NOT_RUN reselection parity with
the driver loop, and transcript harvesting on synthetic workspaces.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import distill_mind3_dataset as miner  # noqa: E402


def test_blocked_path_detection() -> None:
    assert miner.is_blocked_path("benchmarks/heldout/tasks.jsonl") is True
    assert miner.is_blocked_path("benchmarks/heldout-v2/tasks.jsonl") is True
    assert miner.is_blocked_path("results/v4/heldout/run_001/ws") is True
    assert miner.is_blocked_path("results/v4/runs/x/.mind/transcript.jsonl") is False
    # The dev task family fsm_heldout_04 is NOT a sealed suite.
    assert (
        miner.is_blocked_path("tests/golden_mutants/fsm_heldout_04__halfreset.sv")
        is False
    )
    with pytest.raises(ValueError):
        miner.require_not_heldout("benchmarks/heldout/tasks.jsonl")
    with pytest.raises(ValueError):
        miner.require_not_heldout("runs/heldout-v2/ws/.mind/transcript.jsonl")


def test_provider_guard() -> None:
    with pytest.raises(ValueError):
        miner.require_allowed_provider("mock")
    with pytest.raises(ValueError):
        miner.require_allowed_provider(None)
    with pytest.raises(ValueError):
        miner.require_allowed_provider("")
    assert miner.require_allowed_provider("ollama") == "ollama"


def test_holdout_ids_overlap_documented() -> None:
    """Dev-20 IDs are a subset of holdout IDs (verified identical specs), so
    the transcript filter blocks holdout-ONLY IDs; path refusal covers suites."""
    holdout = miner.load_holdout_ids(REPO_ROOT)
    dev = miner.load_dev_ids(REPO_ROOT)
    assert len(dev) == 20
    assert dev <= holdout
    blocked = miner.blocked_task_ids(REPO_ROOT)
    assert len(blocked) == 100
    assert "arbiter_02" not in blocked
    assert "adapters_01" in blocked


def _breach_stub(trace_path: str) -> SimpleNamespace:
    gate_reports = [
        {"gate": "Gate 1: Yosys Elaboration & Latch Trap", "passed": True, "error_category": None},
        {"gate": "Gate 3: Verilator Coverage Signoff", "passed": True, "error_category": None},
        {
            "gate": "Gate 2: SymbiYosys Formal Property Verification",
            "passed": False,
            "error_category": "FORMAL_INVARIANT_BREACH",
            "details": "Formal invariant violated at cycle step T=2.",
            "failing_property": "req[0] |-> gnt[0]",
            "step": "2",
            "trace_file": trace_path,
            "counterexample_trace": "raw vcd ascii (must be replaced by decode)",
        },
        {"gate": "Gate 6: Yosys CDC Static Analysis", "passed": False, "error_category": "NOT_RUN"},
        {"gate": "DFT Scan Audit (Advisory)", "passed": False, "error_category": "NOT_RUN"},
    ]
    return SimpleNamespace(
        gate_reports=gate_reports,
        error_category="FORMAL_INVARIANT_BREACH",
        failure_reason="formal failed",
        stdout="",
        stderr="",
        timing_metrics={},
        hold_metrics={},
        netlist_path=None,
    )


def test_select_failed_report_skips_not_run_stubs() -> None:
    """Parity with the driver loop: the trailing DFT NOT_RUN stub must never
    be selected as the failure report."""
    stub = _breach_stub("x.vcd")
    picked = miner.select_failed_report(stub.gate_reports)
    assert "Formal" in str(picked.get("gate"))
    assert picked.get("error_category") == "FORMAL_INVARIANT_BREACH"


def test_miner_evidence_decodes_real_vcd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MIND3_EVIDENCE_V2", "1")
    contract = miner.load_contract(REPO_ROOT, "arbiter_02")
    fixture = str(REPO_ROOT / "tests" / "fixtures" / "vcd" / "arbiter_02_formal_breach.vcd")
    evidence = miner.build_miner_evidence(contract, _breach_stub(fixture), tmp_path)
    assert evidence.category == "FORMAL_INVARIANT_BREACH"
    assert evidence.cycle == 2
    assert evidence.trace_file == fixture
    assert evidence.counterexample_trace is not None
    assert "Decoded counterexample" in evidence.counterexample_trace
    assert "raw vcd ascii" not in evidence.counterexample_trace
    assert evidence.relevant_signals.get("req") == "0000"
    assert evidence.relevant_signals.get("gnt") == "0000"
    system, user = miner.build_miner_prompt(contract, "module arbiter_02(); endmodule", evidence)
    assert "EVIDENCE-V2 REPAIR GUARD" in system
    assert "Decoded counterexample" in user


def test_miner_evidence_without_trace_keeps_legacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MIND3_EVIDENCE_V2", "1")
    contract = miner.load_contract(REPO_ROOT, "arbiter_02")
    stub = _breach_stub(None)  # type: ignore[arg-type]
    evidence = miner.build_miner_evidence(contract, stub, tmp_path)
    assert evidence.cycle is None
    assert evidence.counterexample_trace == "raw vcd ascii (must be replaced by decode)"


def test_mapped_property_preferred_over_witness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A verifier-resolved mapped_property yields the exact invariant with
    no uncertain fallback, even though the raw witness matches nothing."""
    monkeypatch.setenv("MIND3_EVIDENCE_V2", "1")
    contract = miner.load_contract(REPO_ROOT, "arbiter_02")
    stub = _breach_stub(None)  # type: ignore[arg-type]
    stub.gate_reports = [dict(g) for g in stub.gate_reports]
    for report in stub.gate_reports:
        if report.get("error_category") == "FORMAL_INVARIANT_BREACH":
            report["failing_property"] = (
                "arbiter_02_formal_top.sva._witness_"
                ".check_assert_arbiter_02_sva_sv_19_5"
            )
            report["mapped_property"] = "contract_property_1"
    evidence = miner.build_miner_evidence(contract, stub, tmp_path)
    assert evidence.failing_property is not None
    assert "check_assert" in evidence.failing_property
    assert evidence.property_source == "req[0] |-> gnt[0]"
    assert evidence.expected_behavior is not None
    assert evidence.expected_behavior.startswith("contract_property_1:")
    assert "uncertain" not in evidence.expected_behavior


def test_miner_evidence_matches_driver_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Miner-built evidence must equal driver-built evidence for identical
    inputs (all fields except the loop's repair_history). Any driver drift
    fails here instead of silently poisoning the dataset."""
    import json as _json

    from test_mind3 import MockSandbox

    from mind3.core.contracts import VerificationRepairer as _Repairer
    from mind3.core.driver import PhaseDriver
    from mind3.core.types import VerificationDomain, VerificationResult
    from mind3.core.verifier import SiliconSignoffVerifier

    monkeypatch.setenv("MIND3_EVIDENCE_V2", "1")
    contract = miner.load_contract(REPO_ROOT, "arbiter_02")
    ws = tmp_path / "ws"
    ws.mkdir()
    trace_dir = ws / "arbiter_02" / "engine_0"
    trace_dir.mkdir(parents=True)
    (trace_dir / "trace.vcd").write_text(
        (REPO_ROOT / "tests" / "fixtures" / "vcd" / "arbiter_02_formal_breach.vcd").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    stub_reports = _breach_stub("arbiter_02/engine_0/trace.vcd").gate_reports
    stub_reports = [dict(g) for g in stub_reports]
    breach = VerificationResult(
        passed=False,
        domain=VerificationDomain.RTL,
        exit_code=2,
        failure_reason="formal failed",
        error_category="FORMAL_INVARIANT_BREACH",
        gate_reports=stub_reports,
    )

    class BreachOnceVerifier(SiliconSignoffVerifier):
        def __init__(self) -> None:
            super().__init__(top_module="arbiter_02", allow_mock_fallback=True)
            self.calls = 0

        def verify(self, workspace, sandbox):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return breach
            return VerificationResult(
                passed=True,
                domain=VerificationDomain.RTL,
                exit_code=0,
                silicon_verified=True,
            )

    verifier = BreachOnceVerifier()
    driver = PhaseDriver(
        session_id="parity-probe",
        workspace=ws,
        verifier=verifier,
        max_repairs=3,
        sandbox=MockSandbox(ws),  # type: ignore[arg-type]
    )
    rtl = (
        "module arbiter_02(input logic clk, input logic rst_n, "
        "input logic [3:0] req, output logic [3:0] gnt);\n"
        "  always_ff @(posedge clk) begin\n"
        "    if (!rst_n) gnt <= 4'b0000;\n"
        "    else gnt <= req;\n"
        "  end\nendmodule"
    )
    contract_json = _json.dumps(contract.model_dump(mode="json"))
    queries = iter([contract_json, rtl, rtl])
    monkeypatch.setattr(driver, "_query_model", lambda messages: next(queries))
    captured: dict = {}
    original_build = _Repairer.build_prompt

    def spy_build(contract_arg, rtl_arg, evidence_arg, **kwargs):  # type: ignore[no-untyped-def]
        captured["evidence"] = evidence_arg
        captured["kwargs"] = kwargs
        return original_build(contract_arg, rtl_arg, evidence_arg, **kwargs)

    monkeypatch.setattr(_Repairer, "build_prompt", staticmethod(spy_build))
    assert driver.run_silicon_pipeline("probe", contract_override=contract) is True
    assert captured["kwargs"].get("evidence_v2") is True
    driver_dump = captured["evidence"].model_dump(mode="json")
    miner_evidence = miner.build_miner_evidence(contract, breach, ws)
    miner_dump = miner_evidence.model_dump(mode="json")
    driver_dump.pop("repair_history")
    miner_dump.pop("repair_history")
    assert driver_dump == miner_dump


def _write_workspace(
    runs_root: Path,
    name: str,
    sibling: dict,
    turns: list[tuple[str | None, bool, str]],
    guidances: list[str],
) -> None:
    ws = runs_root / name
    mind = ws / ".mind"
    mind.mkdir(parents=True)
    lines = []
    for candidate, passed, category in turns:
        if candidate is not None:
            lines.append(
                json.dumps({"phase": "EXECUTE", "event": {"payload": {"content": candidate}}})
            )
        lines.append(
            json.dumps(
                {
                    "phase": "VERIFY",
                    "event": {"payload": {"passed": passed, "error_category": category}},
                }
            )
        )
    (mind / "transcript.jsonl").write_text("\n".join(lines), encoding="utf-8")
    sibling = dict(sibling)
    sibling["repair_attempts"] = [{"guidance": g} for g in guidances]
    (runs_root / "transcripts").mkdir(parents=True, exist_ok=True)
    (runs_root / "transcripts" / f"{name}.json").write_text(
        json.dumps(sibling), encoding="utf-8"
    )


def test_transcript_mining_harvests_dpo_and_sft(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "out"
    golden = (REPO_ROOT / "tests" / "golden" / "arbiter_02.sv").read_text(encoding="utf-8")
    _write_workspace(
        runs,
        "arbiter_02",
        {"task_id": "arbiter_02", "provider": "ollama", "model": "qwen2.5-coder:7b"},
        turns=[
            ("module bad1(); endmodule", False, "FORMAL_INVARIANT_BREACH"),
            ("module bad2(); endmodule", False, "FORMAL_INVARIANT_BREACH"),
            ("module good(); endmodule", True, ""),
        ],
        guidances=["GUIDANCE-ONE", "GUIDANCE-TWO", "GUIDANCE-THREE"],
    )
    counts = miner.mine_transcripts(runs, REPO_ROOT, out, set())
    assert counts["dpo_rows"] == 2
    assert counts["sft_rows"] == 1
    dpo = [json.loads(line) for line in (out / "mind3_dpo_repair.jsonl").read_text().splitlines()]
    assert set(dpo[0]) == {"prompt", "chosen", "rejected", "error_category", "failing_gate"}
    assert dpo[0]["rejected"] == "module bad1(); endmodule"
    assert dpo[0]["chosen"] == golden
    assert dpo[0]["error_category"] == "FORMAL_INVARIANT_BREACH"
    assert "GUIDANCE-ONE" in dpo[0]["prompt"]
    assert dpo[1]["rejected"] == "module bad2(); endmodule"
    assert "GUIDANCE-TWO" in dpo[1]["prompt"]
    sft = [json.loads(line) for line in (out / "mind3_sft_repair.jsonl").read_text().splitlines()]
    assert [m["role"] for m in sft[0]["messages"]] == ["system", "user", "assistant"]
    assert sft[0]["messages"][2]["content"] == "module good(); endmodule"
    assert "GUIDANCE-THREE" in sft[0]["messages"][1]["content"]


def test_transcript_mining_blocks_mock_and_heldout(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "out"
    holdout_only_id = "adapters_01"
    assert holdout_only_id in miner.blocked_task_ids(REPO_ROOT)
    _write_workspace(
        runs,
        "mocked",
        {"task_id": "arbiter_02", "provider": "mock"},
        turns=[("module bad(); endmodule", False, "FORMAL_INVARIANT_BREACH")],
        guidances=["G"],
    )
    _write_workspace(
        runs,
        "held",
        {"task_id": holdout_only_id, "provider": "ollama"},
        turns=[("module bad(); endmodule", False, "FORMAL_INVARIANT_BREACH")],
        guidances=["G"],
    )
    counts = miner.mine_transcripts(runs, REPO_ROOT, out, set())
    assert counts["dpo_rows"] == 0
    assert counts["sft_rows"] == 0


def test_gate_for_category_mapping() -> None:
    assert miner.gate_for_category("FORMAL_INVARIANT_BREACH").startswith("Gate 2")
    assert miner.gate_for_category("COVERAGE_BUILD_FAILURE").startswith("Gate 3")
    assert miner.gate_for_category("COVERAGE_DEFICIT").startswith("Gate 3")
    assert miner.gate_for_category("INCOMPLETE_RESET").startswith("Gate 1")
    assert miner.gate_for_category("CLOCK_RESET_ERROR").startswith("Gate 1")
    assert miner.gate_for_category("TIMING_SETUP_VIOLATION").startswith("Gate 4")
    assert miner.gate_for_category("SOME_UNKNOWN_FUTURE_CAT") == ""
    assert miner.gate_for_category("") == ""


def test_dedup_shared_across_modes(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    out = tmp_path / "out"
    seen: set[tuple[str, str, str]] = set()
    _write_workspace(
        runs,
        "dup",
        {"task_id": "arbiter_02", "provider": "ollama"},
        turns=[("module bad(); endmodule", False, "FORMAL_INVARIANT_BREACH")],
        guidances=["SAME-GUIDANCE"],
    )
    first = miner.mine_transcripts(runs, REPO_ROOT, out, seen)
    assert first["dpo_rows"] == 1
    second = miner.mine_transcripts(runs, REPO_ROOT, out, seen)
    assert second["dpo_rows"] == 0
