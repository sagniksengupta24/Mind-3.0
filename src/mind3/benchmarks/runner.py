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
import sys
import tempfile
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core.contracts import InterfaceContract, PortDefinition, PortDirection, SVAProperty, TimingConstraint, contract_from_benchmark_record, validate_contract_consistency
from ..core.driver import PhaseDriver
from ..core.types import PhaseEnum
from ..core.verifier import SiliconSignoffVerifier
from ..sandbox.platform import get_local_sandbox


def _code_provenance(repo_root: Path | None = None) -> dict[str, Any]:
    """Record which code produced a run, so a baseline can never be mislabeled.

    A run is only citable against a commit if that commit is observable in the
    transcript itself. Returns git commit / dirty state plus SHA-256 digests of
    the two files whose behaviour most directly determines verdicts. Every
    field degrades to None/absent instead of raising: provenance recording must
    never break a benchmark run.
    """
    root = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    info: dict[str, Any] = {
        "repo_root": str(root),
        "git_commit": None,
        "git_dirty": None,
        "git_untracked_count": None,
        "file_sha256": {},
    }
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if commit.returncode == 0:
            info["git_commit"] = commit.stdout.strip() or None
        # Tracked modifications only: untracked scratch files cannot change the
        # code that was imported for this run, but they are counted separately.
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if status.returncode == 0:
            info["git_dirty"] = bool(status.stdout.strip())
        untracked = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if untracked.returncode == 0:
            info["git_untracked_count"] = sum(
                1 for line in untracked.stdout.splitlines() if line.startswith("??")
            )
    except (OSError, subprocess.SubprocessError) as exc:
        info["git_error"] = str(exc)
    for rel in ("src/mind3/core/driver.py", "src/mind3/core/verifier.py", "src/mind3/benchmarks/runner.py"):
        path = root / rel
        if path.is_file():
            info["file_sha256"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return info


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
    raw_repair_response: str | None = None
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
    raw_initial_response: str | None = None
    raw_initial_responses: list[str] = Field(default_factory=list)
    decode: dict[str, Any] = Field(default_factory=dict)
    gate_failure_category: str | None = None
    repair_attempts: list[RepairTurnRecord] = Field(default_factory=list)
    final_outcome: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    duration_seconds: float | None = None
    environment: dict[str, Any] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    # R2 harness fields (runner-side only; verifier untouched).
    # env_blocked marks tool/environment failures so reports do not attribute
    # them to the model. cdc_backend records which Gate-6 backend produced the
    # result ("structural-only" when the structural fallback ran).
    env_blocked: bool = False
    cdc_backend: str | None = None


class BenchmarkBaseline(BaseModel):
    """Baseline measured on the exact same task-set hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    task_set_sha256: str = Field(min_length=64, max_length=64)
    real_task_count: int = Field(ge=1)
    functional_pass_rate: float = Field(ge=0.0, le=1.0)
    full_verified_pass_rate: float = Field(ge=0.0, le=1.0)
    source: str = Field(min_length=1)


def generate_caveat(
    evidence_tier: str,
    live_provenance: bool,
    actual_real_transcripts: int,
    required_min_tasks: int,
    diagnostic_flag: bool = False,
) -> str:
    """Generate an honest, derived human-readable caveat explaining run provenance and evidence tier."""
    if not live_provenance or actual_real_transcripts == 0:
        return (
            f"Diagnostic evidence only: run contains {actual_real_transcripts} real model transcripts "
            f"(schema-validation fixtures or mock providers only; zero live model inferences). "
            f"Not eligible for release claims."
        )
    if diagnostic_flag:
        return (
            f"Diagnostic evidence only: run was explicitly executed in diagnostic mode "
            f"with {actual_real_transcripts} real transcripts (required_min_tasks={required_min_tasks}). "
            f"Not eligible for release claims."
        )
    if actual_real_transcripts < 100:
        return (
            f"Diagnostic evidence only: evaluated {actual_real_transcripts} real model transcripts, "
            f"which does not satisfy the mandatory release threshold of at least 100 real tasks "
            f"(required_min_tasks={required_min_tasks}). Not eligible for release claims."
        )
    if required_min_tasks < 100:
        return (
            f"Diagnostic evidence only: required_min_tasks={required_min_tasks} is below the "
            f"mandatory 100-task release floor. Not eligible for release claims."
        )
    return (
        f"Release-eligible evaluation: evaluated {actual_real_transcripts} real non-mock transcripts "
        f"meeting the 100+ task threshold (required_min_tasks={required_min_tasks}). "
        f"Metrics represent measured empirical model performance."
    )


class BenchmarkRunSummary(BaseModel):
    """Machine-readable benchmark evaluation summary."""

    model_config = ConfigDict(extra="forbid")

    generated_at: str
    task_set_path: str
    task_set_sha256: str
    transcript_count: int
    real_transcript_count: int
    fixture_count: int
    live_provenance: bool = False
    required_min_tasks: int = 100
    actual_real_transcripts: int = 0
    evidence_tier: Literal["diagnostic", "release-eligible"] = "diagnostic"
    caveat: str = ""
    performance_claim_valid: bool = False
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
    # R2 harness fields: count of env-blocked transcripts and per-backend counts
    # for Gate-6 CDC results.
    env_blocked_count: int = 0
    cdc_backend_counts: dict[str, int] = Field(default_factory=dict)
    # Token accounting aggregates (summed over real transcripts whose decode
    # block carries model_usage_known=True). Zero + False when unknown.
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    token_usage_known: bool = False


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
        # C2: raw repair bytes pair with RepairTurnRecords in order. Failed
        # model invocations append no raw and emit no record, so a FIFO queue
        # stays aligned: each record consumes the next successful call's raw.
        raw_repair_queue: deque[str] = deque(
            [r for r in getattr(driver, "_raw_repair_responses", []) if isinstance(r, str)]
        )
        initial_raws: list[str] = [
            r for r in getattr(driver, "_raw_initial_responses", []) if isinstance(r, str)
        ]

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
            elif phase == PhaseEnum.EXECUTE and payload.get("role") in {"Targeted RTL Repair Loop", "Independent RTL Verification Repair Engineer"}:
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
                            raw_repair_response=raw_repair_queue.popleft() if raw_repair_queue else None,
                            passed=v_passed,
                            error_category=str(v_cat) if v_cat else None,
                            failure_reason=str(v_reason) if v_reason else None,
                            gate_reports=payload.get("gate_reports", []),
                        )
                    )
                    # Consume the EXECUTE payload so a later VERIFY without a
                    # preceding repair EXECUTE (e.g. parse failure) cannot
                    # reuse stale RTL from an earlier turn.
                    current_repaired_rtl = None
            elif phase == PhaseEnum.REPAIR_OR_FINISH:
                final_outcome = dict(payload)
                final_outcome["passed"] = final_passed

        environment = {
            "python": subprocess.run(["python3", "--version"], capture_output=True, text=True, check=False).stdout.strip(),
            "eda_versions": getattr(driver.verifier, "detected_versions", {}),
            "sandbox": type(driver.sandbox).__name__,
            "parser_mode": getattr(driver, "parser_mode", "strict"),
            "code_provenance": _code_provenance(),
        }
        # C2: decode provenance block. Defensive isinstance guards keep this
        # working with test doubles (MagicMock drivers) as well as live ones.
        decode_events: list[dict[str, Any]] = [
            e for e in (getattr(driver, "_decode_events", []) or []) if isinstance(e, dict)
        ]
        raw_decode_config = driver.decode_config() if hasattr(driver, "decode_config") else {}
        decode_block: dict[str, Any] = dict(raw_decode_config) if isinstance(raw_decode_config, dict) else {}
        decode_block["calls_observed"] = len(decode_events)
        decode_block["any_output_truncated"] = any(e.get("output_truncated") for e in decode_events)
        decode_block["any_prompt_overflow"] = any(e.get("prompt_overflow") for e in decode_events)
        # Token accounting: driver totals accumulated from Ollama
        # prompt_eval_count / eval_count metadata. Defensive guards keep this
        # working with test doubles (MagicMock drivers) as well as live ones;
        # unknown usage stays explicit via model_usage_known=False.
        raw_prompt_tokens = getattr(driver, "total_prompt_tokens", 0)
        raw_completion_tokens = getattr(driver, "total_completion_tokens", 0)
        prompt_tokens = raw_prompt_tokens if isinstance(raw_prompt_tokens, int) else 0
        completion_tokens = raw_completion_tokens if isinstance(raw_completion_tokens, int) else 0
        decode_block["prompt_tokens"] = max(0, prompt_tokens)
        decode_block["completion_tokens"] = max(0, completion_tokens)
        decode_block["total_tokens"] = decode_block["prompt_tokens"] + decode_block["completion_tokens"]
        decode_block["model_usage_known"] = bool(getattr(driver, "model_usage_known", False))
        raw_parse_attempts = getattr(driver, "_parse_attempts", 0)
        decode_block["parse_attempts"] = raw_parse_attempts if isinstance(raw_parse_attempts, int) else 0
        environment["decode"] = decode_block
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
            raw_initial_response=initial_raws[0] if initial_raws else None,
            raw_initial_responses=initial_raws,
            decode=decode_block,
            gate_failure_category=initial_failure_category,
            repair_attempts=repair_attempts,
            final_outcome=final_outcome,
            duration_seconds=None,
            environment=environment,
            artifact_hashes=artifact_hashes,
            env_blocked=is_env_blocked_outcome(final_outcome),
            cdc_backend=cdc_backend_of(environment),
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
        parser_mode: str = "strict",
        decode_temperature: float = 0.0,
        decode_seed: int | None = None,
        decode_num_predict: int = 4096,
        decode_num_ctx: int = 8192,
        generation_format: str = "json",
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
            parser_mode=parser_mode,
            decode_temperature=decode_temperature,
            decode_seed=decode_seed,
            decode_num_predict=decode_num_predict,
            decode_num_ctx=decode_num_ctx,
            generation_format=generation_format,
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
                env_blocked=True,
                cdc_backend=cdc_backend_of({"eda_versions": verifier.detected_versions}),
            )
        finally:
            driver.close()
        transcript.duration_seconds = round(time.monotonic() - start, 3)
        return transcript

    def evaluate_transcripts(
        self,
        transcripts: Iterable[BenchmarkTranscript],
        required_min_tasks: int = 100,
        diagnostic: bool = False,
        parser_mode: str = "strict",
    ) -> BenchmarkRunSummary:
        if parser_mode not in ("strict", "lenient"):
            raise ValueError(
                f"Unknown parser_mode {parser_mode!r}. Expected 'strict' or 'lenient'."
            )
        rows = list(transcripts)
        real = [t for t in rows if not t.is_schema_validation_fixture and getattr(t, "provider", "") != "mock"]
        fixtures = [t for t in rows if t.is_schema_validation_fixture]
        actual_real_transcripts = len(real)
        live_provenance = actual_real_transcripts > 0

        is_release_eligible = (
            live_provenance
            and actual_real_transcripts >= 100
            and required_min_tasks >= 100
            and not diagnostic
        )
        evidence_tier: Literal["diagnostic", "release-eligible"] = (
            "release-eligible" if is_release_eligible else "diagnostic"
        )
        caveat = generate_caveat(
            evidence_tier=evidence_tier,
            live_provenance=live_provenance,
            actual_real_transcripts=actual_real_transcripts,
            required_min_tasks=required_min_tasks,
            diagnostic_flag=diagnostic,
        )

        initial_pass = [t for t in real if _initial_passed(t)]
        functional = [t for t in real if _functional_passed(t)]
        verified = [t for t in real if bool(t.final_outcome.get("passed")) and bool(t.final_outcome.get("silicon_verified"))]
        repaired = [t for t in real if bool(t.final_outcome.get("passed")) and not _initial_passed(t)]
        turns = [int(v) for t in real if isinstance((v := t.final_outcome.get("turns_taken")), int)]
        # R2: tool/environment problems are reported as "env-blocked" so they are
        # never attributed to the model. This only re-labels transcripts whose
        # final outcome already records an environment failure category.
        failure_categories = Counter(
            "env-blocked" if t.env_blocked else (t.gate_failure_category or str(t.final_outcome.get("error_category") or "NONE"))
            for t in real
        )
        env_blocked_count = sum(1 for t in real if t.env_blocked)
        cdc_backend_counts = dict(Counter(t.cdc_backend if t.cdc_backend else "not-recorded" for t in real))
        # Token accounting: sum transcript decode blocks whose usage is known.
        # Unknown on every real transcript stays explicit (False), never zero-passed.
        known_token_rows = [
            t for t in real
            if isinstance(t.decode, dict) and t.decode.get("model_usage_known") is True
        ]
        total_prompt_tokens = sum(
            t.decode.get("prompt_tokens", 0) for t in known_token_rows
            if isinstance(t.decode.get("prompt_tokens"), int)
        )
        total_completion_tokens = sum(
            t.decode.get("completion_tokens", 0) for t in known_token_rows
            if isinstance(t.decode.get("completion_tokens"), int)
        )
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
            live_provenance=live_provenance,
            required_min_tasks=required_min_tasks,
            actual_real_transcripts=actual_real_transcripts,
            evidence_tier=evidence_tier,
            caveat=caveat,
            performance_claim_valid=is_release_eligible,
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
            env_blocked_count=env_blocked_count,
            cdc_backend_counts=cdc_backend_counts,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
            token_usage_known=len(known_token_rows) == n and n > 0,
            methodology={
                "initial_pass": "final result passes on turn 0 without repair",
                "functional_pass": "final Gate 3 coverage succeeds as part of the signoff chain",
                "full_verified_pass": "final_outcome.passed and silicon_verified are both true",
                "repair_success": "final success occurred after at least one repair turn",
                "confidence_interval": "95% Wilson binomial interval",
                "fixtures_excluded_from_metrics": True,
                "env_blocked": "transcripts whose final outcome records a tool/environment failure are counted as env-blocked, never attributed to the model",
                "cdc_backend": "Gate-6 results are labeled structural-only when the pinned structural fallback ran",
                "minimum_claim_tasks": 100,
                "specialist_thresholds": {"functional": 0.70, "full_verified": 0.40},
                "strong_thresholds": {"functional": 0.80, "full_verified": 0.60},
                "9_of_10_target_thresholds": {"functional": 0.85, "full_verified": 0.70},
                "parser_mode": parser_mode,
                "parser_mode_note": "Benchmarks run with parser_mode='lenient' are not equivalent to parser_mode='strict' runs: lenient mode permits bounded recovery of malformed local-model output.",
                "observed_parser_modes": sorted({str(t.environment.get("parser_mode", "unknown")) for t in rows}),
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
            f"- Evidence tier: **{summary.evidence_tier}**",
            f"- Live provenance: **{summary.live_provenance}**",
            f"- Transcripts observed: {summary.transcript_count}",
            f"- Real generation outputs included in metrics: {summary.actual_real_transcripts}",
            f"- Fixtures excluded: {summary.fixture_count}",
            f"- Env-blocked (tool/environment, not model): {summary.env_blocked_count}",
            "",
            "## Gate-6 CDC backends",
            f"- {', '.join(f'`{k}`: {v}' for k, v in sorted(summary.cdc_backend_counts.items())) if summary.cdc_backend_counts else 'no CDC backend records'}",
            "",
            f"- Required minimum tasks: {summary.required_min_tasks}",
            f"- Caveat: *{summary.caveat}*",
            "",
            "## Metrics",
            "| Metric | Count | Rate | 95% CI |",
            "|---|---:|---:|---:|",
            f"| Initial success (Pass@1) | {summary.initial_pass_count}/{summary.actual_real_transcripts} | {summary.initial_pass_rate:.1%} | {_fmt_ci(summary.initial_pass_ci95)} |",
            f"| Functional success | {summary.functional_pass_count}/{summary.actual_real_transcripts} | {summary.functional_pass_rate:.1%} | {_fmt_ci(summary.functional_pass_ci95)} |",
            f"| Full verified success | {summary.full_verified_pass_count}/{summary.actual_real_transcripts} | {summary.full_verified_pass_rate:.1%} | {_fmt_ci(summary.full_verified_pass_ci95)} |",
            f"| Repair success | {summary.repair_success_count}/{summary.actual_real_transcripts} | {summary.repair_success_rate:.1%} | — |",
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
            ("Initial success (Pass@1)", f"{summary.initial_pass_count}/{summary.actual_real_transcripts}", f"{summary.initial_pass_rate:.1%}", _fmt_ci(summary.initial_pass_ci95)),
            ("Functional success", f"{summary.functional_pass_count}/{summary.actual_real_transcripts}", f"{summary.functional_pass_rate:.1%}", _fmt_ci(summary.functional_pass_ci95)),
            ("Full verified success", f"{summary.full_verified_pass_count}/{summary.actual_real_transcripts}", f"{summary.full_verified_pass_rate:.1%}", _fmt_ci(summary.full_verified_pass_ci95)),
            ("Repair success", f"{summary.repair_success_count}/{summary.actual_real_transcripts}", f"{summary.repair_success_rate:.1%}", "—"),
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
<p>Evidence tier: <b>{esc(summary.evidence_tier)}</b> | Live provenance: <b>{esc(summary.live_provenance)}</b></p>
<p>Observed transcripts: <b>{summary.transcript_count}</b>; real generation outputs used for metrics: <b>{summary.actual_real_transcripts}</b>; fixtures excluded: <b>{summary.fixture_count}</b>; required min tasks: <b>{summary.required_min_tasks}</b>; env-blocked (tool/environment, not model): <b>{summary.env_blocked_count}</b>.</p>
<p><em>{esc(summary.caveat)}</em></p>
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


# ── R2 harness helpers: holdout seal + result-field classification ────────────
# Runner/CLI-side only. Verifier code, thresholds, and gate semantics are untouched.

class HoldoutSealError(RuntimeError):
    """Raised when a holdout task path is used without a valid explicit unseal."""


def is_holdout_path(path: Path | str) -> bool:
    """True if any component of the resolved path names a holdout set.

    Name-based only (no file contents are read), so the seal itself can never
    leak heldout task details. Matches `heldout`, `heldout-v2`, etc.
    """
    try:
        parts = Path(path).resolve().parts
    except OSError:
        parts = Path(path).parts
    return any("heldout" in part.lower() for part in parts)


def _seal_tasks_file(tasks_path: Path) -> Path:
    """Resolve the tasks JSONL file for a --tasks/--suite path."""
    p = tasks_path.resolve()
    if p.is_file():
        return p
    candidate = p / "tasks.jsonl"
    if candidate.is_file():
        return candidate
    raise HoldoutSealError(f"holdout seal: tasks file not found under {tasks_path}")


def check_holdout_seal(tasks_path: Path | str | None, *, unseal: bool) -> dict[str, Any]:
    """Fail-closed guard for holdout task sets. Returns a seal record dict.

    - Non-holdout paths: always allowed, no manifest consulted (dev path untouched).
    - Holdout paths: refused unless `unseal` is True AND a `manifest.json` next to
      the tasks file records a SHA-256 (`tasks_sha256` or `task_set_sha256`) that
      exactly matches the tasks file. Missing/mismatched/unreadable manifest refuses.
    """
    if tasks_path is None:
        return {"holdout": False, "sealed": False, "unsealed": False}
    if not is_holdout_path(tasks_path):
        return {"holdout": False, "sealed": False, "unsealed": False}
    if not unseal:
        raise HoldoutSealError(
            f"refusing holdout task path without explicit --unseal: {tasks_path}"
        )
    tasks_file = _seal_tasks_file(Path(tasks_path))
    base = tasks_file.parent
    manifest_path = base / "manifest.json"
    if not manifest_path.is_file():
        raise HoldoutSealError(
            f"refusing unsealed holdout run: manifest.json missing next to {tasks_file}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HoldoutSealError(f"refusing unsealed holdout run: unreadable manifest: {exc}")
    recorded = manifest.get("tasks_sha256") or manifest.get("task_set_sha256")
    actual = sha256_file(tasks_file)
    if not recorded or recorded != actual:
        raise HoldoutSealError(
            "refusing unsealed holdout run: manifest hash mismatch "
            f"(recorded={recorded!r} actual={actual!r})"
        )
    return {"holdout": True, "sealed": True, "unsealed": True, "task_set_sha256": actual}


_ENV_BLOCKED_ERROR_CATEGORIES = frozenset({"ENVIRONMENT_FAILURE"})


def is_env_blocked_outcome(final_outcome: dict[str, Any]) -> bool:
    """True when a final outcome records a tool/environment failure (not the model)."""
    if not isinstance(final_outcome, dict):
        return False
    return str(final_outcome.get("error_category", "")) in _ENV_BLOCKED_ERROR_CATEGORIES


def cdc_backend_of(environment: dict[str, Any] | None) -> str | None:
    """Classify which Gate-6 CDC backend produced a result.

    Returns "structural-only" when the pinned structural fallback ran, "external"
    when an external CDC tool version is recorded, else None (Gate 6 not reached
    or backend unrecorded). Read from runner-side environment metadata only.
    """
    if not isinstance(environment, dict):
        return None
    versions = environment.get("eda_versions")
    if not isinstance(versions, dict):
        return None
    marker = str(versions.get("cdc", ""))
    if not marker:
        return None
    if "structural" in marker.lower():
        return "structural-only"
    return "external"


# Files whose silent modification during a run must fail loudly (rule 5):
# verifier code, gate configs/thresholds, and the holdout seal inputs.
# Recorded per baseline run (R4/R10); generator/repair/template code must never
# write to these paths.
VERIFIER_PINNED_PATHS = (
    "src/mind3/core/verifier.py",
    "src/mind3/core/formal_templates.py",
    "src/mind3/core/contracts.py",
)


def verifier_checksum_snapshot(repo_root: Path | str | None = None) -> dict[str, str]:
    """SHA-256 over the pinned verifier/config files. Missing files are recorded
    with a 'missing:' prefix (fail-closed signal for the caller), never silently skipped."""
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    snapshot: dict[str, str] = {}
    for rel in VERIFIER_PINNED_PATHS:
        path = root / rel
        if path.is_file():
            snapshot[rel] = sha256_file(path)
        else:
            snapshot[rel] = f"missing:{rel}"
    return snapshot


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
    parser.add_argument("--diagnostic", action="store_true", help="Explicitly mark run as diagnostic/development mode (not release-eligible)")
    parser.add_argument("--min-tasks", type=int, default=None, help="Minimum real tasks required for an evidence-complete report (default: 100 for release, or task count in diagnostic mode)")
    parser.add_argument("--evaluate-existing", action="store_true")
    parser.add_argument("--baselines", type=Path, default=None, help="JSON array of baselines measured on the exact same task-set hash")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--require-live", action="store_true")
    parser.add_argument("--unseal", action="store_true", help="Explicitly permit a holdout task path (requires a matching manifest hash; dev paths are unaffected)")
    parser.add_argument("--parser-mode", choices=("strict", "lenient"), default="strict", help="Model-response parser mode: strict (default) accepts only WriteFileAction, fenced blocks, repair patches, or exactly one module; lenient additionally permits bounded recovery of malformed local-model output and is recorded in traces and summaries")
    parser.add_argument("--decode-temperature", type=float, default=0.0, help="Ollama sampling temperature (default 0.0, deterministic)")
    parser.add_argument("--decode-seed", type=int, default=None, help="Ollama sampling seed (default None = server default; supply 42/43/44 for pinned multi-seed runs)")
    parser.add_argument("--decode-num-predict", type=int, default=4096, help="Ollama max completion tokens (anti-truncation guard)")
    parser.add_argument("--decode-num-ctx", type=int, default=8192, help="Ollama context window (anti-prompt-truncation guard)")
    parser.add_argument("--generation-format", choices=("json", "text", "json-schema"), default="json", help="Ollama format for generation/repair calls: json (default, current behavior), text (Track F, no constraint), json-schema (Track J, WriteFileAction schema)")
    args = parser.parse_args()

    try:
        check_holdout_seal(args.tasks, unseal=args.unseal)
    except HoldoutSealError as exc:
        print(f"HOLDOUT_SEAL_REFUSAL: {exc}", file=sys.stderr)
        return 2

    runner = BenchmarkRunner(tasks_file=args.tasks, transcripts_dir=args.transcripts)
    tasks = runner.load_tasks()
    if args.limit is not None:
        tasks = tasks[: args.limit]

    if args.diagnostic:
        required_min_tasks = args.min_tasks if args.min_tasks is not None else len(tasks)
        is_diagnostic = True
    else:
        if args.min_tasks is not None and args.min_tasks < 100:
            required_min_tasks = args.min_tasks
            is_diagnostic = True
        elif len(tasks) < 100:
            required_min_tasks = args.min_tasks if args.min_tasks is not None else min(100, len(tasks))
            is_diagnostic = True
        else:
            required_min_tasks = args.min_tasks if args.min_tasks is not None else 100
            is_diagnostic = False

    if args.evaluate_existing:
        transcripts = runner.load_transcripts(args.transcripts)
    elif args.dry_run:
        missing = check_live_prerequisites()
        print(json.dumps({
            "tasks": len(tasks),
            "required_min_tasks": required_min_tasks,
            "evidence_tier": "diagnostic" if is_diagnostic else "release-eligible",
            "missing_live_prerequisites": missing,
            "parser_mode": args.parser_mode
        }, indent=2))
        return 0 if not args.require_live or not missing else 2
    else:
        missing = check_live_prerequisites()
        if missing and args.require_live:
            raise SystemExit(f"LIVE_BENCHMARK_PREREQUISITES_MISSING: {', '.join(missing)}")
        from mind3.core.verifier import describe_cdc_implementation, run_cdc_preflight
        print(describe_cdc_implementation(), flush=True)
        preflight_failures = run_cdc_preflight()
        if preflight_failures:
            for failure in preflight_failures:
                print(f"CDC_PREFLIGHT_FAIL: {failure}", flush=True)
            raise SystemExit("CDC_PREFLIGHT_FAILED: structural CDC checker is broken; refusing live run.")
        transcripts = []
        work_root = runner.transcripts_dir.parent / "run_workspaces"
        work_root.mkdir(parents=True, exist_ok=True)
        for index, task in enumerate(tasks, 1):
            print(f"[{index}/{len(tasks)}] {task.task_id}", flush=True)
            transcript = runner.run_live_task(task, model=args.model, provider=args.provider, max_repairs=args.max_repairs, liberty_path=args.liberty, api_key=args.api_key, base_url=args.base_url, workspace_root=work_root, parser_mode=args.parser_mode, decode_temperature=args.decode_temperature, decode_seed=args.decode_seed, decode_num_predict=args.decode_num_predict, decode_num_ctx=args.decode_num_ctx, generation_format=args.generation_format)
            runner.persist_transcript(transcript)
            transcripts.append(transcript)

    summary = runner.evaluate_transcripts(transcripts, required_min_tasks=required_min_tasks, diagnostic=is_diagnostic, parser_mode=args.parser_mode)
    if args.baselines is not None:
        summary = runner.attach_baselines(summary, runner.load_baselines(args.baselines, summary.task_set_sha256))
    summary_path, report_path, html_path = runner.write_report(summary, args.report_dir)
    print(summary_path)
    print(report_path)
    print(html_path)
    if summary.actual_real_transcripts < required_min_tasks:
        print(f"EVIDENCE_INSUFFICIENT: {summary.actual_real_transcripts} real tasks < required {required_min_tasks}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
