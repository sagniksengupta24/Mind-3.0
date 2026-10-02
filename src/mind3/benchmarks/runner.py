"""Live benchmark execution, transcript persistence, and evidence-based reporting.

The checked-in 50-task corpus is a smoke/schema-validation set. Performance claims are
only valid for externally supplied, immutable holdout sets with real model outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from ..core.contracts import InterfaceContract, PortDefinition, PortDirection, SVAProperty, TimingConstraint, contract_from_benchmark_record, validate_contract_consistency
from ..core.driver import PhaseDriver
from ..core.types import PhaseEnum
from ..core.verifier import SiliconSignoffVerifier
from ..sandbox.platform import get_local_sandbox


class BenchmarkTask(BaseModel):
    """Specification of one benchmark task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    name: str = Field(min_length=1)
    natural_language_spec: str = Field(min_length=1)
    expected_ports: list[dict[str, Any]] = Field(min_length=2)
    sva_properties: list[str] = Field(min_length=2, max_length=5)
    benchmark_origin: str = Field(min_length=1)
    clock_reset_assumptions: str = Field(default="")
    functional_requirements: list[str] = Field(default_factory=list)
    verification_requirements: list[str] = Field(default_factory=list)
    expected_properties: list[str] = Field(default_factory=list)
    difficulty: str = Field(default="medium")
    is_adversarial: bool = Field(default=False)
    adversarial_type: str | None = Field(default=None)


class RepairTurnRecord(BaseModel):
    """Record of an individual repair turn."""

    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    guidance: str = Field(default="")
    repaired_rtl: str | None = None
    passed: bool
    error_category: str | None = None
    failure_reason: str | None = None
    gate_reports: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkTranscript(BaseModel):
    """Auditable end-to-end benchmark tuple."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    name: str = Field(min_length=1)
    natural_language_spec: str = Field(min_length=1)
    is_schema_validation_fixture: bool = False
    label: str = "real generation output"
    model: str
    provider: str
    max_repairs: int = 10
    contract: dict[str, Any] | None = None
    generated_rtl: str | None = None
    gate_failure_category: str | None = None
    repair_attempts: list[RepairTurnRecord] = Field(default_factory=list)
    final_outcome: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    duration_seconds: float | None = None
    environment: dict[str, Any] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)


class BenchmarkBaseline(BaseModel):
    """Baseline measured on the exact same task-set hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    task_set_sha256: str = Field(min_length=64, max_length=64)
    real_task_count: int = Field(ge=1)
    functional_pass_rate: float = Field(ge=0.0, le=1.0)
    full_verified_pass_rate: float = Field(ge=0.0, le=1.0)
    source: str = Field(min_length=1)


class BenchmarkRunSummary(BaseModel):
    """Machine-readable benchmark evaluation summary."""

    model_config = ConfigDict(extra="forbid")

    generated_at: str
    task_set_path: str
    task_set_sha256: str
    transcript_count: int
    real_transcript_count: int
    fixture_count: int
    initial_pass_count: int
    functional_pass_count: int
    full_verified_pass_count: int
    repair_success_count: int
    initial_pass_rate: float
    functional_pass_rate: float
    full_verified_pass_rate: float
    repair_success_rate: float
    initial_pass_ci95: list[float]
    functional_pass_ci95: list[float]
    full_verified_pass_ci95: list[float]
    mean_turns_taken: float | None
    p50_turns_taken: float | None
    failure_categories: dict[str, int]
    model_counts: dict[str, int]
    provider_counts: dict[str, int]
    tool_versions: dict[str, str]
    baseline_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    methodology: dict[str, Any]


class BenchmarkRunner:
    """Orchestrates benchmark runs and evidence generation."""

    def __init__(
        self,
        tasks_file: Path | str | None = None,
        transcripts_dir: Path | str | None = None,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self.tasks_file = Path(tasks_file).resolve() if tasks_file is not None else root / "benchmarks" / "tasks.jsonl"
        self.transcripts_dir = Path(transcripts_dir).resolve() if transcripts_dir is not None else root / "benchmarks" / "transcripts"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

    def load_tasks(self) -> list[BenchmarkTask]:
        if not self.tasks_file.exists():
            raise FileNotFoundError(f"Benchmark tasks file not found: {self.tasks_file}")
        tasks: list[BenchmarkTask] = []
        with self.tasks_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    tasks.append(BenchmarkTask.model_validate_json(line))
        ids = [t.task_id for t in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("Benchmark task set contains duplicate task_id values")
        return tasks

    @staticmethod
    def build_task_prompt(task: BenchmarkTask) -> str:
        port_lines = [
            f"  - {p['name']}: {p['direction']} [{p['width']} bit(s)] - {p.get('description', '')}"
            for p in task.expected_ports
        ]
        sva_lines = [f"  - {s}" for s in task.sva_properties]
        return (
            f"Benchmark Task ID: {task.task_id}\n"
            f"Module Name MUST equal: {task.task_id}\n"
            f"Specification: {task.natural_language_spec}\n"
            f"Expected Interface Ports:\n" + "\n".join(port_lines) + "\n"
            f"Key Verification Properties to Satisfy:\n" + "\n".join(sva_lines) + "\n"
            "Return synthesizable SystemVerilog only. The independent verifier is authoritative."
        )

    def extract_transcript_tuple(self, task: BenchmarkTask, driver: PhaseDriver, final_passed: bool) -> BenchmarkTranscript:
        contract_dict: dict[str, Any] | None = None
        initial_rtl: str | None = None
        initial_failure_category: str | None = None
        repair_attempts: list[RepairTurnRecord] = []
        final_outcome: dict[str, Any] = {"passed": final_passed}
        current_guidance = ""
        current_repaired_rtl: str | None = None

        for rec in driver.transcript:
            phase = rec.phase
            payload = rec.event.payload
            if phase == PhaseEnum.PARSE and payload.get("role") == "Lead Silicon Architect":
                raw_contract = payload.get("contract")
                if isinstance(raw_contract, dict):
                    contract_dict = raw_contract
                elif "ports" in payload:
                    contract_dict = payload
            elif phase == PhaseEnum.EXECUTE and payload.get("role") == "Principal RTL Design Engineer":
                raw_rtl = payload.get("content") or payload.get("rtl_file")
                if isinstance(raw_rtl, str):
                    initial_rtl = raw_rtl
                elif raw_rtl is not None:
                    initial_rtl = json.dumps(raw_rtl)
            elif phase == PhaseEnum.MODEL_CALL and payload.get("role") in {"Targeted RTL Repair Loop", "Independent RTL Verification Repair Engineer"}:
                current_guidance = str(payload.get("guidance", ""))
            elif phase == PhaseEnum.EXECUTE and payload.get("role") == "Targeted RTL Repair Loop":
                raw_rep = payload.get("content") or payload.get("rtl_file")
                current_repaired_rtl = raw_rep if isinstance(raw_rep, str) else (json.dumps(raw_rep) if raw_rep is not None else None)
            elif phase == PhaseEnum.VERIFY:
                v_passed = bool(payload.get("passed", False))
                v_cat = payload.get("error_category")
                v_reason = payload.get("failure_reason")
                if rec.event.turn == 0:
                    if not v_passed:
                        initial_failure_category = str(v_cat) if v_cat else None
                else:
                    repair_attempts.append(
                        RepairTurnRecord(
                            turn=rec.event.turn,
                            guidance=current_guidance,
                            repaired_rtl=current_repaired_rtl,
                            passed=v_passed,
                            error_category=str(v_cat) if v_cat else None,
                            failure_reason=str(v_reason) if v_reason else None,
                            gate_reports=payload.get("gate_reports", []),
                        )
                    )
            elif phase == PhaseEnum.REPAIR_OR_FINISH:
                final_outcome = dict(payload)
                final_outcome["passed"] = final_passed

        environment = {
            "python": subprocess.run(["python3", "--version"], capture_output=True, text=True, check=False).stdout.strip(),
            "eda_versions": getattr(driver.verifier, "detected_versions", {}),
            "sandbox": type(driver.sandbox).__name__,
        }
        artifact_hashes: dict[str, str] = {}
        for candidate in (
            driver.workspace / f"{task.task_id}.sv" if isinstance(getattr(driver, "workspace", None), Path) else None,
            driver.transcript_file if isinstance(getattr(driver, "transcript_file", None), Path) else None,
        ):
            if candidate is not None and candidate.exists() and candidate.is_file():
                artifact_hashes[candidate.name] = sha256_file(candidate)

        return BenchmarkTranscript(
            task_id=task.task_id,
            category=task.category,
            name=task.name,
            natural_language_spec=task.natural_language_spec,
            is_schema_validation_fixture=False,
            label="real generation output",
            model=driver.model,
            provider=driver.provider,
            max_repairs=driver.max_repairs,
            contract=contract_dict,
            generated_rtl=initial_rtl,
            gate_failure_category=initial_failure_category,
            repair_attempts=repair_attempts,
            final_outcome=final_outcome,
            duration_seconds=None,
            environment=environment,
            artifact_hashes=artifact_hashes,
        )

    def persist_transcript(self, transcript: BenchmarkTranscript) -> Path:
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        dest = self.transcripts_dir / f"{transcript.task_id}.json"
        dest.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
        return dest

    def run_live_task(
        self,
        task: BenchmarkTask,
        *,
        model: str,
        provider: str,
        max_repairs: int,
        liberty_path: str | list[str] | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        workspace_root: Path | None = None,
    ) -> BenchmarkTranscript:
        """Run one task through the real, fail-closed PhaseDriver pipeline."""
        ws_root = Path(workspace_root).resolve() if workspace_root else Path(tempfile.mkdtemp(prefix=f"mind3_{task.task_id}_"))
        ws_root.mkdir(parents=True, exist_ok=True)
        task_ws = ws_root / task.task_id
        if task_ws.exists():
            shutil.rmtree(task_ws)
        task_ws.mkdir(parents=True, exist_ok=True)
        sandbox = get_local_sandbox(task_ws)
        try:
            contract = contract_from_benchmark_record(task.model_dump(mode="json"))
        except Exception as exc:
            return BenchmarkTranscript(
                task_id=task.task_id,
                category=task.category,
                name=task.name,
                natural_language_spec=task.natural_language_spec,
                is_schema_validation_fixture=False,
                label="real generation output - invalid immutable contract",
                model=model,
                provider=provider,
                max_repairs=max_repairs,
                contract={},
                final_outcome={"passed": False, "status": "CONTRACT_BUILD_FAILURE", "error": str(exc), "error_category": "SPECIFICATION_ERROR"},
                environment={"contract_error": str(exc)},
            )
        consistency_errors = validate_contract_consistency(contract)
        if consistency_errors:
            return BenchmarkTranscript(
                task_id=task.task_id,
                category=task.category,
                name=task.name,
                natural_language_spec=task.natural_language_spec,
                is_schema_validation_fixture=False,
                label="real generation output - inconsistent immutable contract",
                model=model,
                provider=provider,
                max_repairs=max_repairs,
                contract=contract.model_dump(mode="json"),
                final_outcome={"passed": False, "status": "CONTRACT_CONSISTENCY_FAILURE", "error_category": "SPECIFICATION_ERROR", "violations": consistency_errors},
                environment={"contract_validation": "failed"},
            )
        verifier = SiliconSignoffVerifier(
            top_module=task.task_id,
            contract=contract,
            allow_mock_fallback=False,
            require_formal=True,
            require_coverage=True,
            require_cdc=True,
            liberty_path=liberty_path,
        )
        start = time.monotonic()
        driver = PhaseDriver(
            session_id=f"benchmark_{task.task_id}_{int(time.time())}",
            workspace=task_ws,
            verifier=verifier,
            sandbox=sandbox,
            model=model,
            provider=provider,
            max_repairs=max_repairs,
            api_key=api_key,
            base_url=base_url,
        )
        try:
            passed = driver.run_silicon_pipeline(self.build_task_prompt(task), liberty_path=liberty_path, contract_override=contract)
            transcript = self.extract_transcript_tuple(task, driver, passed)
        except Exception as exc:
            transcript = BenchmarkTranscript(
                task_id=task.task_id,
                category=task.category,
                name=task.name,
                natural_language_spec=task.natural_language_spec,
                is_schema_validation_fixture=False,
                label="real generation output - run error",
                model=model,
                provider=provider,
                max_repairs=max_repairs,
                contract=contract.model_dump(mode="json"),
                final_outcome={"passed": False, "status": "RUN_EXCEPTION", "error": str(exc), "error_category": "ENVIRONMENT_FAILURE"},
                environment={"eda_versions": verifier.detected_versions, "exception_type": type(exc).__name__},
            )
        finally:
            driver.close()
        transcript.duration_seconds = round(time.monotonic() - start, 3)
        return transcript

    def evaluate_transcripts(self, transcripts: Iterable[BenchmarkTranscript]) -> BenchmarkRunSummary:
        rows = list(transcripts)
        real = [t for t in rows if not t.is_schema_validation_fixture and t.provider != "mock"]
        fixtures = [t for t in rows if t.is_schema_validation_fixture]
        initial_pass = [t for t in real if _initial_passed(t)]
        functional = [t for t in real if _functional_passed(t)]
        verified = [t for t in real if bool(t.final_outcome.get("passed")) and bool(t.final_outcome.get("silicon_verified"))]
        repaired = [t for t in real if bool(t.final_outcome.get("passed")) and not _initial_passed(t)]
        turns = [int(t.final_outcome.get("turns_taken")) for t in real if isinstance(t.final_outcome.get("turns_taken"), int)]
        failure_categories = Counter(t.gate_failure_category or str(t.final_outcome.get("error_category") or "NONE") for t in real)
        tool_versions: dict[str, str] = {}
        for t in real:
            versions = t.environment.get("eda_versions", {})
            if isinstance(versions, dict):
                for key, value in versions.items():
                    tool_versions[str(key)] = str(value)

        n = len(real)
        def rate(count: int) -> float:
            return round(count / n, 4) if n else 0.0

        task_set_hash = sha256_file(self.tasks_file) if self.tasks_file.exists() else "missing"
        return BenchmarkRunSummary(
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            task_set_path=str(self.tasks_file),
            task_set_sha256=task_set_hash,
            transcript_count=len(rows),
            real_transcript_count=n,
            fixture_count=len(fixtures),
            initial_pass_count=len(initial_pass),
            functional_pass_count=len(functional),
            full_verified_pass_count=len(verified),
            repair_success_count=len(repaired),
            initial_pass_rate=rate(len(initial_pass)),
            functional_pass_rate=rate(len(functional)),
            full_verified_pass_rate=rate(len(verified)),
            repair_success_rate=rate(len(repaired)),
            initial_pass_ci95=list(_wilson_ci95(len(initial_pass), n)),
            functional_pass_ci95=list(_wilson_ci95(len(functional), n)),
            full_verified_pass_ci95=list(_wilson_ci95(len(verified), n)),
            mean_turns_taken=round(statistics.mean(turns), 3) if turns else None,
            p50_turns_taken=round(statistics.median(turns), 3) if turns else None,
            failure_categories=dict(failure_categories),
            model_counts=dict(Counter(t.model for t in real)),
            provider_counts=dict(Counter(t.provider for t in real)),
            tool_versions=tool_versions,
            methodology={
                "initial_pass": "final result passes on turn 0 without repair",
                "functional_pass": "final Gate 3 coverage succeeds as part of the signoff chain",
                "full_verified_pass": "final_outcome.passed and silicon_verified are both true",
                "repair_success": "final success occurred after at least one repair turn",
                "confidence_interval": "95% Wilson binomial interval",
                "fixtures_excluded_from_metrics": True,
                "minimum_claim_tasks": 100,
                "specialist_thresholds": {"functional": 0.70, "full_verified": 0.40},
                "strong_thresholds": {"functional": 0.80, "full_verified": 0.60},
                "9_of_10_target_thresholds": {"functional": 0.85, "full_verified": 0.70},
            },
        )

    def load_baselines(self, path: Path | str, task_set_sha256: str) -> list[BenchmarkBaseline]:
        source = Path(path).resolve()
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Baseline file must contain a JSON array")
        baselines = [BenchmarkBaseline.model_validate(item) for item in raw]
        for baseline in baselines:
            if baseline.task_set_sha256 != task_set_sha256:
                raise ValueError(f"Baseline {baseline.name!r} uses a different task-set SHA-256")
        return baselines

    @staticmethod
    def attach_baselines(summary: BenchmarkRunSummary, baselines: Iterable[BenchmarkBaseline]) -> BenchmarkRunSummary:
        comparisons: list[dict[str, Any]] = []
        for baseline in baselines:
            comparisons.append({
                "name": baseline.name,
                "real_task_count": baseline.real_task_count,
                "functional_pass_rate": baseline.functional_pass_rate,
                "full_verified_pass_rate": baseline.full_verified_pass_rate,
                "functional_delta_vs_mind3": round(summary.functional_pass_rate - baseline.functional_pass_rate, 4),
                "full_verified_delta_vs_mind3": round(summary.full_verified_pass_rate - baseline.full_verified_pass_rate, 4),
                "source": baseline.source,
            })
        return summary.model_copy(update={"baseline_comparisons": comparisons})

    def write_report(self, summary: BenchmarkRunSummary, output_dir: Path | str) -> tuple[Path, Path, Path]:
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        summary_path = out / "benchmark_summary.json"
        markdown_path = out / "benchmark_report.md"
        html_path = out / "benchmark_report.html"
        summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        method = summary.methodology
        md = [
            "# Mind 3.0 Benchmark Report",
            "",
            f"Generated: `{summary.generated_at}`",
            f"Task-set SHA-256: `{summary.task_set_sha256}`",
            "",
            "## Evidence scope",
            f"- Transcripts observed: {summary.transcript_count}",
            f"- Real generation outputs included in metrics: {summary.real_transcript_count}",
            f"- Fixtures excluded: {summary.fixture_count}",
            "",
            "## Metrics",
            "| Metric | Count | Rate | 95% CI |",
            "|---|---:|---:|---:|",
            f"| Initial success (Pass@1) | {summary.initial_pass_count}/{summary.real_transcript_count} | {summary.initial_pass_rate:.1%} | {_fmt_ci(summary.initial_pass_ci95)} |",
            f"| Functional success | {summary.functional_pass_count}/{summary.real_transcript_count} | {summary.functional_pass_rate:.1%} | {_fmt_ci(summary.functional_pass_ci95)} |",
            f"| Full verified success | {summary.full_verified_pass_count}/{summary.real_transcript_count} | {summary.full_verified_pass_rate:.1%} | {_fmt_ci(summary.full_verified_pass_ci95)} |",
            f"| Repair success | {summary.repair_success_count}/{summary.real_transcript_count} | {summary.repair_success_rate:.1%} | — |",
            "",
            "## Guardrails",
            f"- Performance claims require at least {method['minimum_claim_tasks']} real holdout tasks.",
            "- Schema-validation fixtures and mock-provider runs are never counted as benchmark evidence.",
            "- Full verified means the configured signoff pipeline passed; this is not foundry tapeout signoff.",
            "",
            "## Failure categories",
        ]
        for k, v in sorted(summary.failure_categories.items(), key=lambda kv: (-kv[1], kv[0])):
            md.append(f"- `{k}`: {v}")
        md += ["", "## Baselines"]
        if summary.baseline_comparisons:
            md += ["| Baseline | Tasks | Functional | Full verified | Δ Functional | Δ Full verified |", "|---|---:|---:|---:|---:|---:|"]
            for row in summary.baseline_comparisons:
                md.append(f"| {row['name']} | {row['real_task_count']} | {row['functional_pass_rate']:.1%} | {row['full_verified_pass_rate']:.1%} | {row['functional_delta_vs_mind3']:+.1%} | {row['full_verified_delta_vs_mind3']:+.1%} |")
        else:
            md.append("No same-task-set baselines were supplied.")
        md += ["", "## Tool versions"]
        for k, v in sorted(summary.tool_versions.items()):
            md.append(f"- `{k}`: `{v}`")
        markdown_path.write_text("\n".join(md) + "\n", encoding="utf-8")

        def esc(value: object) -> str:
            text = str(value)
            return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

        rows = [
            ("Initial success (Pass@1)", f"{summary.initial_pass_count}/{summary.real_transcript_count}", f"{summary.initial_pass_rate:.1%}", _fmt_ci(summary.initial_pass_ci95)),
            ("Functional success", f"{summary.functional_pass_count}/{summary.real_transcript_count}", f"{summary.functional_pass_rate:.1%}", _fmt_ci(summary.functional_pass_ci95)),
            ("Full verified success", f"{summary.full_verified_pass_count}/{summary.real_transcript_count}", f"{summary.full_verified_pass_rate:.1%}", _fmt_ci(summary.full_verified_pass_ci95)),
            ("Repair success", f"{summary.repair_success_count}/{summary.real_transcript_count}", f"{summary.repair_success_rate:.1%}", "—"),
        ]
        html_rows = "\n".join(
            f"<tr><td>{esc(metric)}</td><td>{esc(count)}</td><td>{esc(rate)}</td><td>{esc(ci)}</td></tr>"
            for metric, count, rate, ci in rows
        )
        failure_rows = "\n".join(
            f"<tr><td><code>{esc(k)}</code></td><td>{v}</td></tr>"
            for k, v in sorted(summary.failure_categories.items(), key=lambda kv: (-kv[1], kv[0]))
        ) or '<tr><td colspan="2">No real-run failures recorded.</td></tr>'
        html = f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Mind 3.0 Benchmark Report</title>
<style>body{{font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;max-width:1000px;margin:40px auto;padding:0 20px}}table{{border-collapse:collapse;width:100%;margin:16px 0 28px}}th,td{{border:1px solid #ccc;padding:8px;text-align:left}}code{{font-family:ui-monospace,monospace}}.muted{{color:#666}}</style></head>
<body>
<h1>Mind 3.0 Benchmark Report</h1>
<p class=\"muted\">Generated: <code>{esc(summary.generated_at)}</code><br>Task-set SHA-256: <code>{esc(summary.task_set_sha256)}</code></p>
<h2>Evidence scope</h2>
<p>Observed transcripts: <b>{summary.transcript_count}</b>; real generation outputs used for metrics: <b>{summary.real_transcript_count}</b>; fixtures excluded: <b>{summary.fixture_count}</b>.</p>
<h2>Metrics</h2>
<table><thead><tr><th>Metric</th><th>Count</th><th>Rate</th><th>95% CI</th></tr></thead><tbody>{html_rows}</tbody></table>
<h2>Guardrails</h2>
<ul><li>Performance claims require at least {method['minimum_claim_tasks']} real holdout tasks.</li><li>Schema-validation fixtures and mock-provider runs are excluded.</li><li>Full verified is pipeline evidence, not foundry tapeout signoff.</li></ul>
<h2>Failure categories</h2>
<table><thead><tr><th>Category</th><th>Count</th></tr></thead><tbody>{failure_rows}</tbody></table>
<h2>Baselines</h2>
{(
    "<table><thead><tr><th>Baseline</th><th>Tasks</th><th>Functional</th><th>Full verified</th><th>Δ Functional</th><th>Δ Full verified</th></tr></thead><tbody>" +
    "".join(f"<tr><td>{esc(r['name'])}</td><td>{r['real_task_count']}</td><td>{r['functional_pass_rate']:.1%}</td><td>{r['full_verified_pass_rate']:.1%}</td><td>{r['functional_delta_vs_mind3']:+.1%}</td><td>{r['full_verified_delta_vs_mind3']:+.1%}</td></tr>" for r in summary.baseline_comparisons) +
    "</tbody></table>"
    ) if summary.baseline_comparisons else "<p>No same-task-set baselines were supplied.</p>"}
<h2>Tool versions</h2>
<ul>{''.join(f'<li><code>{esc(k)}</code>: <code>{esc(v)}</code></li>' for k,v in sorted(summary.tool_versions.items())) or '<li>No live tool versions recorded.</li>'}</ul>
</body></html>
"""
        html_path.write_text(html, encoding="utf-8")
        return summary_path, markdown_path, html_path

    def load_transcripts(self, directory: Path | str | None = None) -> list[BenchmarkTranscript]:
        src = Path(directory).resolve() if directory else self.transcripts_dir
        results: list[BenchmarkTranscript] = []
        for path in sorted(src.glob("*.json")):
            results.append(BenchmarkTranscript.model_validate_json(path.read_text(encoding="utf-8")))
        return results

    # Existing schema fixture helpers are intentionally retained for unit tests.
    def create_schema_validation_fixture(self, task: BenchmarkTask, simulated_initial_pass: bool = False, simulated_converged: bool = True) -> BenchmarkTranscript:
        ports = [PortDefinition(name=p["name"], direction=PortDirection(p["direction"]), width=p["width"], description=p.get("description", "")) for p in task.expected_ports]
        sva = [SVAProperty(name=f"chk_prop_{i}", property_expr=task.sva_properties[i], description=f"Formal property {i}") for i in range(len(task.sva_properties))]
        contract = InterfaceContract(module_name=task.task_id, functional_spec=task.natural_language_spec, ports=ports, sva_properties=sva, timing=TimingConstraint(clock_name="clk", period_ns=10.0))
        mock_rtl = "// [SCHEMA-VALIDATION FIXTURE - NOT REAL GENERATION OUTPUT]\nmodule " + task.task_id + " (\n" + ",\n".join(f"  {p.to_verilog_declaration()}" for p in ports) + "\n);\nendmodule\n"
        repair_attempts: list[RepairTurnRecord] = []
        if simulated_initial_pass:
            init_cat = None
            final_outcome = {"passed": True, "status": "SILICON_VERIFIED", "turns_taken": 1, "silicon_verified": True}
        elif simulated_converged:
            init_cat = "FORMAL_INVARIANT_BREACH"
            repair_attempts.append(RepairTurnRecord(turn=1, guidance="GATE 2 SIGN-OFF FAILURE: Formal SVA invariant breached in SymbiYosys BMC.", repaired_rtl=mock_rtl, passed=True))
            final_outcome = {"passed": True, "status": "SILICON_VERIFIED", "turns_taken": 2, "silicon_verified": True}
        else:
            init_cat = "TIMING_SLACK_VIOLATION"
            final_outcome = {"passed": False, "status": "REPAIR_EXHAUSTED", "turns_taken": 10, "silicon_verified": False}
        return BenchmarkTranscript(task_id=task.task_id, category=task.category, name=task.name, natural_language_spec=task.natural_language_spec, is_schema_validation_fixture=True, label="schema-validation fixture, not real generation output", model="mock-fixture-generator", provider="mock", max_repairs=10, contract=contract.model_dump(mode="json"), generated_rtl=mock_rtl, gate_failure_category=init_cat, repair_attempts=repair_attempts, final_outcome=final_outcome)

    def persist_all_fixtures(self, tasks: list[BenchmarkTask] | None = None) -> list[Path]:
        if tasks is None:
            tasks = self.load_tasks()
        paths: list[Path] = []
        for i, task in enumerate(tasks):
            paths.append(self.persist_transcript(self.create_schema_validation_fixture(task, simulated_initial_pass=(i % 3 == 0), simulated_converged=(i % 3 != 2))))
        return paths


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _initial_passed(t: BenchmarkTranscript) -> bool:
    if t.gate_failure_category is not None:
        return False
    return int(t.final_outcome.get("turns_taken", 1)) <= 1 and bool(t.final_outcome.get("passed"))


def _functional_passed(t: BenchmarkTranscript) -> bool:
    reports = t.final_outcome.get("gate_reports", [])
    if not isinstance(reports, list):
        return False
    gate3 = [r for r in reports if isinstance(r, dict) and "Gate 3" in str(r.get("gate", ""))]
    if gate3:
        return bool(gate3[-1].get("passed"))
    return bool(t.final_outcome.get("passed")) and bool(t.final_outcome.get("silicon_verified"))


def _wilson_ci95(successes: int, total: int) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    z = 1.959963984540054
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt((phat * (1 - phat) / total) + (z * z / (4 * total * total))) / denom
    return round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)


def _fmt_ci(ci: list[float]) -> str:
    return f"[{ci[0]:.1%}, {ci[1]:.1%}]"


def _required_eda_commands() -> list[str]:
    return ["yosys", "sby", "verilator", "sta/opensta"]


def check_live_prerequisites() -> list[str]:
    """Check only prerequisites that are local to the selected execution mode."""
    if os.getenv("EDA_REMOTE_HOST", "").strip():
        # Remote mode delegates EDA execution and sandboxing to the remote Linux host.
        return []

    missing: list[str] = []
    if os.uname().sysname == "Darwin":
        if shutil.which("sandbox-exec") is None:
            missing.append("sandbox-exec")
    elif shutil.which("bwrap") is None:
        missing.append("bwrap")

    for binary in ("yosys", "sby", "verilator"):
        if shutil.which(binary) is None:
            missing.append(binary)
    if shutil.which("sta") is None and shutil.which("opensta") is None:
        missing.append("sta/opensta")
    return missing


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run or evaluate Mind 3.0 RTL benchmarks.")
    parser.add_argument("--tasks", type=Path, default=None, help="Task JSONL path (default: benchmarks/tasks.jsonl)")
    parser.add_argument("--transcripts", type=Path, default=None, help="Transcript directory")
    parser.add_argument("--report-dir", type=Path, default=Path("artifacts/benchmark_report"))
    parser.add_argument("--model", default=os.getenv("MIND_MODEL", "qwen2.5-coder:7b"))
    parser.add_argument("--provider", choices=("ollama", "openrouter"), default=os.getenv("MIND_PROVIDER", "ollama"))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--liberty", action="append", default=None)
    parser.add_argument("--max-repairs", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-tasks", type=int, default=None, help="Minimum real tasks required for an evidence-complete report (default: min(100, selected task count))")
    parser.add_argument("--evaluate-existing", action="store_true")
    parser.add_argument("--baselines", type=Path, default=None, help="JSON array of baselines measured on the exact same task-set hash")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-live", action="store_true")
    args = parser.parse_args()

    runner = BenchmarkRunner(tasks_file=args.tasks, transcripts_dir=args.transcripts)
    tasks = runner.load_tasks()
    if args.limit is not None:
        tasks = tasks[: args.limit]
    required_min_tasks = args.min_tasks if args.min_tasks is not None else min(100, len(tasks))

    if args.evaluate_existing:
        transcripts = runner.load_transcripts(args.transcripts)
    elif args.dry_run:
        missing = check_live_prerequisites()
        print(json.dumps({"tasks": len(tasks), "required_min_tasks": required_min_tasks, "missing_live_prerequisites": missing}, indent=2))
        return 0 if not args.require_live or not missing else 2
    else:
        missing = check_live_prerequisites()
        if missing and args.require_live:
            raise SystemExit(f"LIVE_BENCHMARK_PREREQUISITES_MISSING: {', '.join(missing)}")
        transcripts = []
        work_root = runner.transcripts_dir.parent / "run_workspaces"
        work_root.mkdir(parents=True, exist_ok=True)
        for index, task in enumerate(tasks, 1):
            print(f"[{index}/{len(tasks)}] {task.task_id}", flush=True)
            transcript = runner.run_live_task(task, model=args.model, provider=args.provider, max_repairs=args.max_repairs, liberty_path=args.liberty, api_key=args.api_key, base_url=args.base_url, workspace_root=work_root)
            runner.persist_transcript(transcript)
            transcripts.append(transcript)

    summary = runner.evaluate_transcripts(transcripts)
    if args.baselines is not None:
        summary = runner.attach_baselines(summary, runner.load_baselines(args.baselines, summary.task_set_sha256))
    summary_path, report_path, html_path = runner.write_report(summary, args.report_dir)
    print(summary_path)
    print(report_path)
    print(html_path)
    if summary.real_transcript_count < required_min_tasks:
        print(f"EVIDENCE_INSUFFICIENT: {summary.real_transcript_count} real tasks < required {required_min_tasks}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
