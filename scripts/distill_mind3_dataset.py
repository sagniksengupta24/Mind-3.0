"""Mine SFT/DPO repair datasets for qwen2.5-coder distillation (read-only inputs).

Modes (outputs go to untracked ``results/v4/runs/distilled/``):
  --from-soundness    Pair the 23 soundness mutants with their verified
                      goldens. Each mutant is verified live (real gates, no
                      model); the exact flag-ON repair prompt is built with
                      the R5 decoded VCD table for Gate-2 failures and exact
                      Gate-1 diagnostics otherwise.
  --from-transcripts  Harvest benchmark run workspaces: passing runs yield
                      SFT rows; failed repair turns yield DPO rows against
                      verified goldens.

Anti-contamination (fail fast, never poison output):
  - any heldout / heldout-v2 path or task ID -> ValueError,
  - any mock-provider (or unknown-provider) transcript -> ValueError,
  - identical (prompt, chosen, rejected) triples deduplicated by sha256.

Row schemas (exact keys, JSONL):
  SFT: {"messages": [{"role": "system", ...}, {"role": "user", ...},
                     {"role": "assistant", ...}]}
  DPO: {"prompt", "chosen", "rejected", "error_category", "failing_gate"}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from mind3.core.contracts import (  # noqa: E402
    InterfaceContract,
    VerificationFailureEvidence,
    VerificationRepairer,
    contract_from_benchmark_record,
)
from mind3.core.vcd_evidence import (  # noqa: E402
    VCD_MAX_CHARS,
    decode_counterexample,
    evidence_v2_enabled,
    property_signal_names,
)

HELDOUT_SUITES = ("heldout", "heldout-v2")
MOCK_PROVIDER = "mock"


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def is_blocked_path(path: str | Path) -> bool:
    """True only when a path *component* names a sealed suite.

    Substring matching would false-positive on the dev task family
    `fsm_heldout_04` (verified dev-20 member, not a sealed suite).
    """
    return any(
        part.lower() in ("heldout", "heldout-v2")
        for part in Path(str(path)).parts
    )


def require_not_heldout(path_or_task: str) -> None:
    if is_blocked_path(path_or_task):
        raise ValueError(f"heldout-contaminated input refused: {path_or_task}")


def load_holdout_ids(repo_root: Path) -> set[str]:
    """Task IDs sealed in holdout suites (includes the dev-20 subset).

    NOTE: dev-20 task IDs are a subset of the holdout IDs (verified: all 20
    dev IDs appear in both holdout suites with identical specs). A bare
    task-ID block would therefore refuse every dev run, including the
    sanctioned Step-C arbiter_02 transcript. Use `blocked_task_ids` (holdout
    IDs minus dev-20 IDs) for transcript filtering; path-based refusal
    (`require_not_heldout`) still applies to any holdout path.
    """
    ids: set[str] = set()
    for suite in HELDOUT_SUITES:
        tasks_file = repo_root / "benchmarks" / suite / "tasks.jsonl"
        if not tasks_file.is_file():
            continue
        for line in tasks_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(str(json.loads(line).get("task_id", "")))
            except (ValueError, AttributeError):
                continue
    return ids - {""}


def load_dev_ids(repo_root: Path) -> set[str]:
    """Sanctioned development-20 task IDs (harvestable, never sealed)."""
    ids: set[str] = set()
    tasks_file = repo_root / "benchmarks" / "development-20" / "tasks.jsonl"
    if not tasks_file.is_file():
        return ids
    for line in tasks_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(str(json.loads(line).get("task_id", "")))
        except (ValueError, AttributeError):
            continue
    return ids - {""}


def blocked_task_ids(repo_root: Path) -> set[str]:
    """Holdout-only task IDs: sealed tasks outside the dev-20 subset."""
    return load_holdout_ids(repo_root) - load_dev_ids(repo_root)


def gate_for_category(category: str) -> str:
    """Deterministic category -> failing-gate label for transcript rows.

    Categories are gate-specific by construction (each is emitted by exactly
    one gate), so this is labeling, not invention. Unknown categories yield
    "" rather than a guessed gate.
    """
    if not category:
        return ""
    if "FORMAL" in category or category in {"UNSUPPORTED_FORMAL_PROPERTY", "EMPTY_FORMAL_PROPERTY_SET"}:
        return "Gate 2: SymbiYosys Formal Property Verification"
    if category.startswith("SIMULATION") or category.startswith("COVERAGE") or category == "MISSING_VERIFICATION_ARTIFACT":
        return "Gate 3: Verilator Coverage Signoff"
    if category in {"SYNTAX_ERROR", "INTERFACE_ERROR", "TYPE_WIDTH_ERROR", "CLOCK_RESET_ERROR", "LATCH_INFERRED", "INCOMPLETE_RESET", "COMBINATIONAL_LOOP", "RTL_SYNTAX_ERROR", "RTL_SEMANTIC_ERROR", "RESPONSE_PARSE_FAILURE", "EDA_BINARY_MISSING"}:
        return "Gate 1: Yosys Elaboration & Latch Trap"
    if "TIMING" in category:
        return "Gate 4: OpenSTA Multi-Corner Timing Signoff"
    return ""


def require_allowed_provider(provider: str | None) -> str:
    if provider is None or str(provider).strip().lower() in ("", MOCK_PROVIDER):
        raise ValueError(f"non-live provider refused: {provider!r}")
    return str(provider)


def load_contract(repo_root: Path, task_id: str) -> InterfaceContract:
    tasks_file = repo_root / "benchmarks" / "development-20" / "tasks.jsonl"
    for line in tasks_file.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
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
    raise KeyError(f"dev task not found: {task_id}")


def select_failed_report(gate_reports: list[dict]) -> dict:
    """Mirror of the driver loop: last failed non-NOT_RUN gate report."""
    failed = [
        g
        for g in (gate_reports or [])
        if isinstance(g, dict)
        and g.get("passed") is False
        and g.get("error_category") not in ("NOT_RUN",)
        and not g.get("skipped", False)
    ]
    if failed:
        return failed[-1]
    reports = [g for g in (gate_reports or []) if isinstance(g, dict)]
    return reports[-1] if reports else {}


def classify_stage(category: str, last_report: dict) -> str:
    """Repair-stage mapping mirrored exactly from the driver loop
    (including its `or`/`and` precedence on the simulation branch)."""
    if category in {"SYNTAX_ERROR", "INTERFACE_ERROR", "TYPE_WIDTH_ERROR", "CLOCK_RESET_ERROR", "LATCH_INFERRED", "COMBINATIONAL_LOOP", "RTL_SYNTAX_ERROR", "RTL_SEMANTIC_ERROR", "RESPONSE_PARSE_FAILURE", "EDA_BINARY_MISSING"}:
        return "compile"
    elif category.startswith("SIMULATION") or category.startswith("COVERAGE") or category in {"MISSING_VERIFICATION_ARTIFACT"} and "Gate 3" in str(last_report.get("gate", "")):
        return "simulation"
    elif "FORMAL" in category or category in {"UNSUPPORTED_FORMAL_PROPERTY", "EMPTY_FORMAL_PROPERTY_SET"}:
        return "formal"
    elif "TIMING" in category:
        return "timing"
    else:
        return "other"


def build_miner_evidence(
    contract: InterfaceContract,
    v_result: object,
    workspace: Path,
) -> VerificationFailureEvidence:
    """Assemble repair evidence exactly like the driver loop (flag-ON path).

    A cross-check unit test proves byte-equality with driver-built evidence
    for the same inputs; any driver drift fails that test instead of silently
    poisoning the dataset.
    """
    gate_reports = list(getattr(v_result, "gate_reports", []) or [])
    last_report = select_failed_report(gate_reports)
    category = str(getattr(v_result, "error_category", "") or "UNKNOWN_ERROR")
    diagnostic = last_report.get("diagnostic", {}) if isinstance(last_report, dict) else {}
    compile_diag = diagnostic if isinstance(diagnostic, dict) else {}
    file_name = compile_diag.get("file")
    line = compile_diag.get("line")
    column = compile_diag.get("column")
    source_context = compile_diag.get("source_context", "")
    stage_key = classify_stage(category, last_report)
    tool_value = str(
        last_report.get("compile_tool")
        or compile_diag.get("tool")
        or ("sby" if stage_key == "formal" else "verilator" if stage_key == "simulation" else "")
    )
    property_source = None
    matched_contract_prop: str | None = None
    if last_report.get("failing_property"):
        prop_name = str(last_report.get("failing_property"))
        for prop in [*contract.formal_properties, *contract.sva_properties]:
            pname = getattr(prop, "name", "")
            if pname == prop_name or prop_name in pname:
                property_source = getattr(prop, "expression", None) or getattr(prop, "property_expr", None)
                matched_contract_prop = pname
                break
    if contract.clock is not None:
        clock_state_value: str | None = f"{contract.clock.name} {contract.clock.edge}"
    else:
        clock_state_value = None
    if contract.reset is not None:
        sync_word = "synchronous" if contract.reset.synchronous else "asynchronous"
        reset_state_value: str | None = f"{contract.reset.name} {contract.reset.polarity} {sync_word}"
    else:
        reset_state_value = "none - no reset port in contract"
    if matched_contract_prop is not None and property_source:
        expected_value: str | None = f"{matched_contract_prop}: {property_source}"
    else:
        required_bits = [b for b in [*contract.behavior, *contract.invariants] if str(b).strip()]
        joined = "; ".join(str(b).strip() for b in required_bits)[:1500]
        expected_value = f"Contract requires: {joined}" if joined else None
        if last_report.get("failing_property") and matched_contract_prop is None and expected_value:
            expected_value += (
                " (failing-property mapping uncertain: witness name "
                f"{last_report.get('failing_property')} did not match a contract property; "
                "raw evidence preserved)"
            )
    observed_value: str | None = str(
        last_report.get("details") or getattr(v_result, "failure_reason", "") or "verification failed"
    )[:2000]
    if last_report.get("failing_property") or last_report.get("step") is not None:
        observed_value = (
            f"Property {last_report.get('failing_property')} failed "
            f"at step {last_report.get('step')}: {observed_value}"
        )[:2000]
    markdown: str | None = None
    cycle_value: int | None = None
    relevant: dict[str, str] | None = None
    if evidence_v2_enabled() and category == "FORMAL_INVARIANT_BREACH":
        t_raw = last_report.get("cycle")
        t_fail: int | None = _t_raw if isinstance((_t_raw := t_raw), int) else None
        if t_fail is None:
            try:
                t_fail = int(str(last_report.get("step")))
            except (TypeError, ValueError):
                t_fail = None
        trace_text: str | None = None
        trace_path = last_report.get("trace_file")
        if trace_path:
            try:
                trace_file = Path(trace_path)
                if not trace_file.is_absolute():
                    trace_file = (workspace / trace_file).resolve()
                if trace_file.is_file() and trace_file.stat().st_size <= VCD_MAX_CHARS:
                    trace_text = trace_file.read_text(encoding="utf-8", errors="replace")[:VCD_MAX_CHARS]
            except OSError:
                trace_text = None
        if trace_text:
            port_names = [str(getattr(p, "name", "")) for p in contract.ports or []]
            clock_name = contract.clock.name if contract.clock is not None else "clk"
            reset_name, reset_active_low = ("rst_n", True)
            if contract.reset is not None:
                reset_name = str(contract.reset.name)
                reset_active_low = str(contract.reset.polarity) == "active_low"
            decoded = decode_counterexample(
                trace_text,
                port_names=[n for n in port_names if n],
                extra_names=property_signal_names(property_source),
                t_fail=t_fail,
                clock_name=clock_name,
                reset_name=reset_name,
                reset_active_low=reset_active_low,
                failing_assertion=str(last_report.get("failing_property"))
                if last_report.get("failing_property")
                else None,
                source=str(trace_path),
            )
            markdown = decoded["markdown"]
            if isinstance(decoded.get("t_fail"), int):
                cycle_value = decoded["t_fail"]
            rows = decoded.get("rows", [])
            if rows:
                relevant = {
                    str(k): ("" if v is None else str(v))
                    for k, v in rows[-1].items()
                    if k != "step"
                }
    return VerificationFailureEvidence(
        gate=str(last_report.get("gate", "verification gate")),
        category=category,
        stage=stage_key,
        tool=tool_value,
        error=str(last_report.get("details") or getattr(v_result, "failure_reason", "") or "verification failed"),
        file=str(file_name) if file_name else None,
        line=int(line) if isinstance(line, int) else (int(line) if isinstance(line, str) and line.isdigit() else None),
        column=int(column) if isinstance(column, int) else (int(column) if isinstance(column, str) and column.isdigit() else None),
        source_context=str(source_context or ""),
        stdout_tail=(getattr(v_result, "stdout", "") or "")[-4000:],
        stderr_tail=(getattr(v_result, "stderr", "") or "")[-4000:],
        failing_property=str(last_report.get("failing_property")) if last_report.get("failing_property") else None,
        failing_step=str(last_report.get("step")) if last_report.get("step") is not None else None,
        trace_file=str(last_report.get("trace_file")) if last_report.get("trace_file") else None,
        metrics={k: v for k, v in {**getattr(v_result, "timing_metrics", {}), **getattr(v_result, "hold_metrics", {})}.items() if isinstance(v, (int, float))},
        artifact_paths=[str(p) for p in [getattr(v_result, "netlist_path", None), last_report.get("trace_file")] if p],
        contract=contract.model_dump(mode="json"),
        attempt=1,
        failing_test=str(last_report.get("failing_test")) if last_report.get("failing_test") else None,
        cycle=cycle_value if cycle_value is not None else None,
        expected_behavior=expected_value,
        observed_behavior=observed_value,
        relevant_signals=relevant if relevant else {},
        reset_state=reset_state_value,
        clock_state=clock_state_value,
        property_source=property_source,
        counterexample_trace=markdown
        if markdown is not None
        else (str(last_report.get("counterexample_trace")) if last_report.get("counterexample_trace") else None),
        repair_history=[],
    )


def build_miner_prompt(
    contract: InterfaceContract, current_rtl: str, evidence: VerificationFailureEvidence
) -> tuple[str, str]:
    prompt = VerificationRepairer.build_prompt(
        contract, current_rtl, evidence, evidence_v2=True
    )
    return prompt["system"], prompt["user"]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def mine_soundness(
    repo_root: Path,
    out_dir: Path,
    liberty: str | None,
    seen: set[tuple[str, str, str]] | None = None,
) -> dict[str, int]:
    """Verify every soundness mutant live; emit SFT/DPO rows. Returns counts."""
    from mind3.core.verifier import SiliconSignoffVerifier
    from mind3.sandbox.platform import get_local_sandbox

    seen = seen if seen is not None else set()
    sft_rows: list[dict] = []
    dpo_rows: list[dict] = []
    by_gate: dict[str, int] = {}
    skipped: list[str] = []
    mutant_files = sorted((repo_root / "tests" / "golden_mutants").glob("*__*.sv"))
    for mutant_path in mutant_files:
        require_not_heldout(str(mutant_path))
        task_id = mutant_path.name.split("__")[0]
        golden_path = repo_root / "tests" / "golden" / f"{task_id}.sv"
        if not golden_path.is_file():
            skipped.append(f"{mutant_path.name}: no golden")
            continue
        contract = load_contract(repo_root, task_id)
        tmp = Path(tempfile.mkdtemp(prefix="distill_"))
        try:
            (tmp / f"{task_id}.sv").write_text(
                mutant_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
            verifier = SiliconSignoffVerifier(
                top_module=task_id,
                contract=contract,
                allow_mock_fallback=False,
                liberty_path=[liberty] if liberty else None,
            )
            sandbox = get_local_sandbox(tmp)
            v_result = verifier.verify(tmp, sandbox)
            if bool(getattr(v_result, "passed", False)):
                skipped.append(f"{mutant_path.name}: unexpectedly passed")
                continue
            evidence = build_miner_evidence(contract, v_result, tmp)
            system, user = build_miner_prompt(
                contract, mutant_path.read_text(encoding="utf-8"), evidence
            )
            chosen = golden_path.read_text(encoding="utf-8")
            rejected = mutant_path.read_text(encoding="utf-8")
            prompt_text = system + "\n\n" + user
            key = (sha16(prompt_text), sha16(chosen), sha16(rejected))
            if key in seen:
                continue
            seen.add(key)
            sft_rows.append(
                {
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                        {"role": "assistant", "content": chosen},
                    ]
                }
            )
            failed = select_failed_report(list(getattr(v_result, "gate_reports", []) or []))
            dpo_rows.append(
                {
                    "prompt": prompt_text,
                    "chosen": chosen,
                    "rejected": rejected,
                    "error_category": str(getattr(v_result, "error_category", "")),
                    "failing_gate": str(failed.get("gate", "")),
                }
            )
            by_gate[str(getattr(v_result, "error_category", ""))] = (
                by_gate.get(str(getattr(v_result, "error_category", "")), 0) + 1
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    write_jsonl(out_dir / "mind3_sft_repair.jsonl", sft_rows)
    write_jsonl(out_dir / "mind3_dpo_repair.jsonl", dpo_rows)
    return {
        "mutants": len(mutant_files),
        "sft_rows": len(sft_rows),
        "dpo_rows": len(dpo_rows),
        "skipped": len(skipped),
        "sft": sft_rows,
        "dpo": dpo_rows,
    }


def _sibling_transcript(run_workspace: Path) -> dict | None:
    """Benchmark transcript.json sibling (provider/task/final RTL source)."""
    run_root = run_workspace
    for _ in range(6):
        candidate_dir = run_root / "transcripts"
        if candidate_dir.is_dir():
            files = sorted(candidate_dir.glob("*.json"))
            if files:
                try:
                    return json.loads(files[0].read_text(encoding="utf-8"))
                except ValueError:
                    return None
        run_root = run_root.parent
    return None


def mine_transcripts(
    runs_root: Path,
    repo_root: Path,
    out_dir: Path,
    seen: set[tuple[str, str, str]] | None = None,
) -> dict[str, int]:
    """Harvest passing SFT trajectories and failed-turn DPO pairs."""
    seen = seen if seen is not None else set()
    blocked_ids = blocked_task_ids(repo_root)
    sft_rows: list[dict] = []
    dpo_rows: list[dict] = []
    by_gate: dict[str, int] = {}
    workspaces = sorted(runs_root.rglob(".mind/transcript.jsonl"))
    for mind_file in workspaces:
        ws = mind_file.parent.parent
        if is_blocked_path(str(mind_file)):
            continue
        sibling = _sibling_transcript(ws)
        if sibling is None:
            continue
        try:
            require_allowed_provider(sibling.get("provider"))
        except ValueError:
            continue
        task_id = str(sibling.get("task_id", ""))
        if not task_id or task_id in blocked_ids or is_blocked_path(task_id):
            continue
        try:
            contract = load_contract(repo_root, task_id)
        except KeyError:
            continue
        golden_path = repo_root / "tests" / "golden" / f"{task_id}.sv"
        if not golden_path.is_file():
            continue
        turns: list[dict] = []
        current_candidate: str | None = None
        try:
            entries = [
                json.loads(line)
                for line in mind_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except ValueError:
            continue
        # repair_attempts[i].guidance is the flag-ON repair prompt built FROM
        # the i-th failure, so VERIFY#(i+1) pairs with guidance[i] in order.
        guidance_queue: list[str] = [
            str(attempt.get("guidance"))
            for attempt in sibling.get("repair_attempts", []) or []
            if isinstance(attempt.get("guidance"), str) and attempt.get("guidance")
        ]
        for entry in entries:
            payload = entry.get("event", {}).get("payload", {})
            phase = entry.get("phase")
            if phase == "EXECUTE" and isinstance(payload, dict) and payload.get("content"):
                current_candidate = str(payload["content"])
            elif phase == "VERIFY" and isinstance(payload, dict):
                guidance = guidance_queue.pop(0) if guidance_queue else None
                turns.append(
                    {
                        "candidate": current_candidate,
                        "passed": bool(payload.get("passed")),
                        "category": str(payload.get("error_category") or ""),
                        "guidance": guidance,
                    }
                )
        system, _ = build_miner_prompt(
            contract,
            "",
            VerificationFailureEvidence(gate="mining", category="mining"),
        )
        system_only = system
        chosen = golden_path.read_text(encoding="utf-8")
        # Failed turns -> DPO (rejected = failed candidate, user = the
        # recorded flag-ON repair prompt for that turn).
        for turn in turns:
            if turn["passed"] or not turn["candidate"]:
                continue
            user = turn["guidance"]
            if user is None:
                continue
            prompt_text = system_only + "\n\n" + user
            key = (sha16(prompt_text), sha16(chosen), sha16(turn["candidate"]))
            if key in seen:
                continue
            seen.add(key)
            dpo_rows.append(
                {
                    "prompt": prompt_text,
                    "chosen": chosen,
                    "rejected": turn["candidate"],
                    "error_category": turn["category"],
                    "failing_gate": gate_for_category(turn["category"]),
                }
            )
            by_gate[turn["category"]] = by_gate.get(turn["category"], 0) + 1
        # Passing final -> SFT (assistant = final candidate, user = the
        # recorded flag-ON repair prompt that produced it).
        if turns and turns[-1]["passed"] and turns[-1]["candidate"]:
            user = turns[-1]["guidance"]
            if user is not None:
                prompt_text = system_only + "\n\n" + user
                key = (sha16(prompt_text), sha16(turns[-1]["candidate"] or ""), sha16(""))
                if key not in seen:
                    seen.add(key)
                    sft_rows.append(
                        {
                            "messages": [
                                {"role": "system", "content": system_only},
                                {"role": "user", "content": user},
                                {"role": "assistant", "content": turns[-1]["candidate"] or ""},
                            ]
                        }
                    )
    write_jsonl(out_dir / "mind3_sft_repair.jsonl", sft_rows)
    write_jsonl(out_dir / "mind3_dpo_repair.jsonl", dpo_rows)
    return {
        "workspaces": len(workspaces),
        "sft_rows": len(sft_rows),
        "dpo_rows": len(dpo_rows),
        "sft": sft_rows,
        "dpo": dpo_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-soundness", action="store_true")
    parser.add_argument("--from-transcripts", action="store_true")
    parser.add_argument("--runs-root", type=Path, default=REPO_ROOT / "results" / "v4" / "runs")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "results" / "v4" / "runs" / "distilled")
    parser.add_argument(
        "--liberty",
        default="/Users/sagniksengupta/Desktop/Mind3-PDK/sky130_fd_sc_hd__tt_025C_1v80.lib",
    )
    args = parser.parse_args(argv)
    if not args.from_soundness and not args.from_transcripts:
        parser.error("nothing to do: pass --from-soundness and/or --from-transcripts")
    os.environ["MIND3_EVIDENCE_V2"] = "1"
    from mind3.core.vcd_evidence import evidence_v2_enabled

    assert evidence_v2_enabled(), "miner requires the flag-ON pipeline"
    seen: set[tuple[str, str, str]] = set()
    out_dir = args.out_dir
    merged_sft: list[dict] = []
    merged_dpo: list[dict] = []
    per_mode: dict[str, dict] = {}
    if args.from_soundness:
        counts = mine_soundness(REPO_ROOT, out_dir, args.liberty, seen)
        per_mode["soundness"] = {
            k: v for k, v in counts.items() if k in ("mutants", "sft_rows", "dpo_rows", "skipped")
        }
        merged_sft.extend(counts.pop("sft"))
        merged_dpo.extend(counts.pop("dpo"))
        print(f"soundness: {json.dumps(per_mode['soundness'], sort_keys=True)}")
    if args.from_transcripts:
        counts = mine_transcripts(args.runs_root, REPO_ROOT, out_dir, seen)
        per_mode["transcripts"] = {
            k: v for k, v in counts.items() if k in ("workspaces", "sft_rows", "dpo_rows")
        }
        merged_sft.extend(counts.pop("sft"))
        merged_dpo.extend(counts.pop("dpo"))
        print(f"transcripts: {json.dumps(per_mode['transcripts'], sort_keys=True)}")
    # Single merged write: modes share `seen`, so no cross-mode duplicates.
    write_jsonl(out_dir / "mind3_sft_repair.jsonl", merged_sft)
    write_jsonl(out_dir / "mind3_dpo_repair.jsonl", merged_dpo)
    manifest = {
        "sft_rows": len(merged_sft),
        "dpo_rows": len(merged_dpo),
        "modes": per_mode,
    }
    (out_dir / "mind3_distill_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"manifest: {json.dumps(manifest, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
