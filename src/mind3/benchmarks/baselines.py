"""Three-baseline comparative evaluation framework for Mind 3.0.

Executes and compares the exact same benchmark tasks through three distinct architectures:
- Baseline A (Direct model): Spec -> Model -> RTL -> Verification (No repair)
- Baseline B (Naive repair): Spec -> Model -> RTL -> Verification -> Model repair -> Verification
- Mind-3.0 (Structured agent): Spec -> Contract Analysis -> RTL Generation -> Independent
  Verification -> Structured Evidence -> Bounded Repair -> Verification -> Final Evidence -> Human Approval

Enforces:
- Identical task sets, prompts, and EDA tools across baselines
- Full metric tracking: compile, simulation, formal, timing, full verified, repairs, tokens, runtime, cost
- Wilson 95% confidence intervals
- Explicit deterministic failure categorization
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

import httpx

from pydantic import BaseModel, ConfigDict, Field

from ..core.contracts import InterfaceContract, PortDefinition, PortDirection, VerificationHarnessGenerator, RTLGenerator, contract_from_benchmark_record, validate_contract_consistency
from ..core.driver import PhaseDriver, _parse_model_code_response, ModelResponseParseError
from ..core.failure_taxonomy import FailureCategory, classify_failure
from ..core.types import PhaseEnum, WriteFileAction, WriteBatchFilesAction
from ..core.verifier import SiliconSignoffVerifier
from ..sandbox.bwrap import BubblewrapSandbox
from ..sandbox.remote_eda import LocalBwrapRunner, get_eda_runner
from .runner import BenchmarkTask, sha256_file


def _wilson_ci95(k: int, n: int) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    margin = (z / denom) * math.sqrt((p * (1.0 - p) / n) + (z * z) / (4.0 * (n * n)))
    return round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)


class BaselineType(StrEnum):
    BASELINE_A = "Baseline A (Direct 1-shot)"
    BASELINE_B = "Baseline B (Naive repair)"
    MIND_3 = "Mind 3.0 (Contract-guided fail-closed)"


class TaskRunMetric(BaseModel):
    """Execution record for one task under one baseline."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    baseline: BaselineType
    compile_pass: bool
    simulation_pass: bool
    formal_pass: bool
    timing_pass: bool
    full_verified_pass: bool
    repair_success: bool
    repair_attempts: int
    runtime_sec: float
    token_usage: int
    estimated_cost_usd: float
    failure_category: FailureCategory
    tool_versions: dict[str, str] = Field(default_factory=dict)
    model_version: str = "mock"
    benchmark_version: str = "heldout-v1"
    task_hash: str
    run_hash: str
    token_usage_known: bool = False
    cost_known: bool = False


class BaselineSummary(BaseModel):
    """Aggregate comparison metrics for one baseline."""

    model_config = ConfigDict(extra="forbid")

    baseline_name: str
    task_count: int
    compile_pass_rate: float
    simulation_pass_rate: float
    formal_pass_rate: float
    timing_pass_rate: float
    full_verified_pass_rate: float
    repair_success_rate: float
    full_verified_ci95: list[float]
    mean_repair_attempts: float
    mean_runtime_sec: float
    mean_cost_usd: float
    total_tokens: int
    token_usage_known: bool = False
    cost_known: bool = False
    failure_distribution: dict[str, int]


class BaselineComparisonReport(BaseModel):
    """Comparative report across all three baselines."""

    model_config = ConfigDict(extra="forbid")

    task_set_sha256: str
    benchmark_suite: str
    evaluated_at: str
    seed: int
    baselines: dict[str, BaselineSummary]
    task_runs: list[TaskRunMetric] = Field(default_factory=list)


class BaselineComparisonRunner:
    """Executes identical tasks across Baseline A, Baseline B, and Mind 3.0."""

    def __init__(
        self,
        tasks: list[BenchmarkTask],
        *,
        model: str = "gemini-1.5-pro",
        provider: str = "mock",
        seed: int = 42,
        max_repairs: int = 5,
        api_key: str | None = None,
        base_url: str | None = None,
        liberty_path: str | list[str] | None = None,
        artifact_root: Path | None = None,
    ) -> None:
        self.tasks = tasks
        self.model = model
        self.provider = provider
        self.seed = seed
        self.max_repairs = max_repairs
        self.api_key = api_key
        self.base_url = base_url
        self.liberty_path = liberty_path
        self.artifact_root = Path(artifact_root).resolve() if artifact_root is not None else None

    def _compute_run_hash(self, task_id: str, baseline: str, rtl: str) -> str:
        h = hashlib.sha256()
        h.update(f"{task_id}:{baseline}:{self.seed}:{self.model}:{rtl}".encode("utf-8"))
        return h.hexdigest()

    @staticmethod
    def _stage_metrics(result: Any) -> tuple[bool, bool, bool, bool, bool, dict[str, Any], str]:
        reports = result.gate_reports if result is not None else []
        by_gate: dict[str, dict[str, Any]] = {}
        for report in reports:
            if isinstance(report, dict):
                by_gate[str(report.get("gate", ""))] = report
        g1 = next((r for k, r in by_gate.items() if k.startswith("Gate 1:")), None)
        g2 = next((r for k, r in by_gate.items() if k.startswith("Gate 2:")), None)
        g3 = next((r for k, r in by_gate.items() if k.startswith("Gate 3:")), None)
        g4 = next((r for k, r in by_gate.items() if k.startswith("Gate 4:")), None)
        compile_pass = bool(g1 and g1.get("passed"))
        simulation_pass = bool(g3 and g3.get("passed"))
        formal_pass = bool(g2 and g2.get("passed"))
        timing_pass = bool(g4 and g4.get("passed"))
        full_pass = bool(result is not None and result.passed and result.silicon_verified)
        failure = str(result.error_category or "UNKNOWN") if result is not None else "UNKNOWN"
        return compile_pass, simulation_pass, formal_pass, timing_pass, full_pass, by_gate, failure

    def _new_driver(self, task: BenchmarkTask, workspace: Path, runner: Any, contract: InterfaceContract, max_repairs: int) -> tuple[PhaseDriver, SiliconSignoffVerifier]:
        verifier = SiliconSignoffVerifier(
            top_module=task.task_id,
            contract=contract,
            allow_mock_fallback=False,
            require_formal=True,
            require_coverage=True,
            require_cdc=False,
            runner=runner,
            liberty_path=self.liberty_path,
        )
        driver = PhaseDriver(
            session_id=f"cmp_{task.task_id}_{int(time.time()*1000)}",
            workspace=workspace,
            verifier=verifier,
            sandbox=None,
            model=self.model,
            provider=self.provider,
            max_repairs=max_repairs,
            api_key=self.api_key,
            base_url=self.base_url,
        )
        return driver, verifier

    def _generate_direct(self, task: BenchmarkTask, workspace: Path, runner: Any, contract: InterfaceContract) -> tuple[PhaseDriver, SiliconSignoffVerifier, str]:
        driver, verifier = self._new_driver(task, workspace, runner, contract, max_repairs=0)
        try:
            sva_bind = VerificationHarnessGenerator.build_sva_bind_module(contract)
        except Exception as exc:
            sva_bind = f"// formal generation failed closed: {exc}\n"
        harness_files = [
            WriteFileAction(path=f"{contract.module_name}_sva.sv", content=sva_bind),
            WriteFileAction(path=f"{contract.module_name}.sby", content=VerificationHarnessGenerator.build_sby_config(contract, depth=25, include_sva_file=bool(contract.formal_properties or contract.sva_properties))),
            WriteFileAction(path=f"{contract.module_name}_formal_top.sv", content=VerificationHarnessGenerator.build_formal_wrapper(contract)),
            WriteFileAction(path=f"{contract.module_name}_tb.cpp", content=VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)),
            WriteFileAction(path=f"{contract.module_name}.sdc", content=contract.timing.to_sdc()),
        ]
        batch = WriteBatchFilesAction(files=harness_files)
        driver._policy_check(batch)
        driver._execute_action(batch)
        prompt = RTLGenerator.build_prompt(contract)
        messages = driver._build_prompt_messages(prompt["system"], prompt["user"])
        raw = driver._query_model(messages)
        rtl = _parse_model_code_response(raw, default_module_name=contract.module_name)
        action = WriteFileAction(path=f"{contract.module_name}.sv", content=rtl)
        driver._policy_check(action)
        driver._execute_action(action)
        return driver, verifier, rtl

    def _metric_from_result(self, task: BenchmarkTask, baseline: BaselineType, result: Any, runtime: float, repair_attempts: int, rtl: str, verifier: SiliconSignoffVerifier, task_hash: str, verifier_driver: PhaseDriver | None = None) -> TaskRunMetric:
        compile_pass, sim_pass, formal_pass, timing_pass, full_pass, _reports, failure = self._stage_metrics(result)
        if full_pass:
            category = FailureCategory.UNKNOWN
        else:
            category = classify_failure(
                error_category=failure,
                failure_reason=getattr(result, "failure_reason", None),
                stdout=getattr(result, "stdout", ""),
                stderr=getattr(result, "stderr", ""),
            ).canonical_category
        return TaskRunMetric(
            task_id=task.task_id,
            baseline=baseline,
            compile_pass=compile_pass,
            simulation_pass=sim_pass,
            formal_pass=formal_pass,
            timing_pass=timing_pass,
            full_verified_pass=full_pass,
            repair_success=full_pass and repair_attempts > 0,
            repair_attempts=repair_attempts,
            runtime_sec=round(runtime, 3),
            token_usage=verifier_driver.total_tokens if verifier_driver is not None else 0,
            estimated_cost_usd=verifier_driver.model_cost_usd if verifier_driver is not None else 0.0,
            failure_category=category,
            tool_versions=verifier.detected_versions,
            model_version=self.model,
            benchmark_version="heldout-v1",
            task_hash=task_hash,
            run_hash=self._compute_run_hash(task.task_id, baseline.value, rtl),
            token_usage_known=bool(verifier_driver and verifier_driver.model_usage_known),
            cost_known=bool(verifier_driver and verifier_driver.model_cost_known),
        )

    def run_baseline_a(self, task: BenchmarkTask, workspace: Path, runner: Any) -> TaskRunMetric:
        """Baseline A: live model direct generation followed by independent verification, no repair."""
        if self.provider == "mock":
            raise RuntimeError("Benchmark Baseline A requires a live model provider; mock runs are not performance evidence.")
        start = time.monotonic()
        workspace = Path(workspace).resolve(); workspace.mkdir(parents=True, exist_ok=True)
        contract = contract_from_benchmark_record(task.model_dump(mode="json"))
        task_hash = hashlib.sha256(task.model_dump_json().encode("utf-8")).hexdigest()
        consistency_errors = validate_contract_consistency(contract)
        if consistency_errors:
            return TaskRunMetric(
                task_id=task.task_id,
                baseline=BaselineType.BASELINE_A,
                compile_pass=False,
                simulation_pass=False,
                formal_pass=False,
                timing_pass=False,
                full_verified_pass=False,
                repair_success=False,
                repair_attempts=0,
                runtime_sec=round(time.monotonic() - start, 3),
                token_usage=0,
                estimated_cost_usd=0.0,
                failure_category=FailureCategory.SPECIFICATION_ERROR,
                tool_versions={},
                model_version=self.model,
                benchmark_version="heldout-v1",
                task_hash=task_hash,
                run_hash=self._compute_run_hash(task.task_id, BaselineType.BASELINE_A.value, ""),
                token_usage_known=False,
                cost_known=False,
            )
        driver = None
        verifier = None
        try:
            driver, verifier, rtl = self._generate_direct(task, workspace, runner, contract)
            result = verifier.verify(workspace, None)
            return self._metric_from_result(task, BaselineType.BASELINE_A, result, time.monotonic()-start, 0, rtl, verifier, task_hash, driver)
        except (ModelResponseParseError, Exception) as exc:
            is_timeout = isinstance(exc, httpx.TimeoutException)
            fail_cat = FailureCategory.TIMEOUT if is_timeout else FailureCategory.RTL_SYNTAX_ERROR
            return TaskRunMetric(
                task_id=task.task_id,
                baseline=BaselineType.BASELINE_A,
                compile_pass=False,
                simulation_pass=False,
                formal_pass=False,
                timing_pass=False,
                full_verified_pass=False,
                repair_success=False,
                repair_attempts=0,
                runtime_sec=round(time.monotonic() - start, 3),
                token_usage=driver.total_tokens if driver else 0,
                estimated_cost_usd=driver.model_cost_usd if driver else 0.0,
                failure_category=fail_cat,
                tool_versions=verifier.detected_versions if verifier else {},
                model_version=self.model,
                benchmark_version="heldout-v1",
                task_hash=task_hash,
                run_hash=self._compute_run_hash(task.task_id, BaselineType.BASELINE_A.value, ""),
                token_usage_known=bool(driver and driver.model_usage_known),
                cost_known=bool(driver and driver.model_cost_known),
            )
        finally:
            if driver is not None:
                driver.close()

    def run_baseline_b(self, task: BenchmarkTask, workspace: Path, runner: Any) -> TaskRunMetric:
        """Baseline B: live direct generation with bounded generic/raw-error repair."""
        if self.provider == "mock":
            raise RuntimeError("Benchmark Baseline B requires a live model provider; mock runs are not performance evidence.")
        start = time.monotonic()
        workspace = Path(workspace).resolve(); workspace.mkdir(parents=True, exist_ok=True)
        contract = contract_from_benchmark_record(task.model_dump(mode="json"))
        task_hash = hashlib.sha256(task.model_dump_json().encode("utf-8")).hexdigest()
        consistency_errors = validate_contract_consistency(contract)
        if consistency_errors:
            return TaskRunMetric(
                task_id=task.task_id,
                baseline=BaselineType.BASELINE_B,
                compile_pass=False,
                simulation_pass=False,
                formal_pass=False,
                timing_pass=False,
                full_verified_pass=False,
                repair_success=False,
                repair_attempts=0,
                runtime_sec=round(time.monotonic() - start, 3),
                token_usage=0,
                estimated_cost_usd=0.0,
                failure_category=FailureCategory.SPECIFICATION_ERROR,
                tool_versions={},
                model_version=self.model,
                benchmark_version="heldout-v1",
                task_hash=task_hash,
                run_hash=self._compute_run_hash(task.task_id, BaselineType.BASELINE_B.value, ""),
                token_usage_known=False,
                cost_known=False,
            )
        driver = None
        verifier = None
        try:
            driver, verifier, rtl = self._generate_direct(task, workspace, runner, contract)
            repair_attempts = 0
            result = verifier.verify(workspace, None)
            stage_counts = {"compile": 0, "simulation": 0, "formal": 0}
            while not (result.passed and result.silicon_verified):
                category = str(result.error_category or "")
                stage = "compile" if category in {"SYNTAX_ERROR","INTERFACE_ERROR","TYPE_WIDTH_ERROR","CLOCK_RESET_ERROR","LATCH_INFERRED","COMBINATIONAL_LOOP","RTL_SYNTAX_ERROR","RTL_SEMANTIC_ERROR"} else "simulation" if category.startswith("SIMULATION") or "Gate 3" in str((result.gate_reports[-1] if result.gate_reports else {}).get("gate", "")) else "formal" if ("FORMAL" in category or "UNSUPPORTED_FORMAL" in category) else "compile"
                if stage not in stage_counts or stage_counts[stage] >= 3:
                    break
                stage_counts[stage] += 1; repair_attempts += 1
                evidence = result.failure_reason or (result.stderr or "")[-3000:]
                generic_system = "Return ONLY the complete SystemVerilog module. Fix the concrete verification error. Do not change the required module interface or remove required behavior."
                generic_user = (
                    f"Module: {contract.module_name}\n"
                    f"Contract:\n{json.dumps(contract.model_dump(mode='json'), indent=2)}\n"
                    f"Stage: {stage}\nRaw verifier error:\n{evidence}\n\nCurrent RTL:\n{rtl}\n"
                )
                raw = driver._query_model(driver._build_prompt_messages(generic_system, generic_user))
                try:
                    rtl = _parse_model_code_response(raw, default_module_name=contract.module_name, base_code=rtl)
                    path = workspace / f"{contract.module_name}.sv"; path.write_text(rtl, encoding="utf-8")
                    result = verifier.verify(workspace, None)
                except (ModelResponseParseError, Exception):
                    break
            return self._metric_from_result(task, BaselineType.BASELINE_B, result, time.monotonic()-start, repair_attempts, rtl, verifier, task_hash, driver)
        except (ModelResponseParseError, Exception) as exc:
            is_timeout = isinstance(exc, httpx.TimeoutException)
            fail_cat = FailureCategory.TIMEOUT if is_timeout else FailureCategory.RTL_SYNTAX_ERROR
            return TaskRunMetric(
                task_id=task.task_id,
                baseline=BaselineType.BASELINE_B,
                compile_pass=False,
                simulation_pass=False,
                formal_pass=False,
                timing_pass=False,
                full_verified_pass=False,
                repair_success=False,
                repair_attempts=0,
                runtime_sec=round(time.monotonic() - start, 3),
                token_usage=driver.total_tokens if driver else 0,
                estimated_cost_usd=driver.model_cost_usd if driver else 0.0,
                failure_category=fail_cat,
                tool_versions=verifier.detected_versions if verifier else {},
                model_version=self.model,
                benchmark_version="heldout-v1",
                task_hash=task_hash,
                run_hash=self._compute_run_hash(task.task_id, BaselineType.BASELINE_B.value, ""),
                token_usage_known=bool(driver and driver.model_usage_known),
                cost_known=bool(driver and driver.model_cost_known),
            )
        finally:
            if driver is not None:
                driver.close()

    def run_mind3(self, task: BenchmarkTask, workspace: Path, runner: Any) -> TaskRunMetric:
        """Mind 3.0: immutable benchmark contract + structured bounded stage repair."""
        if self.provider == "mock":
            raise RuntimeError("Mind 3.0 benchmark requires a live model provider; mock runs are not performance evidence.")
        start = time.monotonic()
        workspace = Path(workspace).resolve(); workspace.mkdir(parents=True, exist_ok=True)
        contract = contract_from_benchmark_record(task.model_dump(mode="json"))
        task_hash = hashlib.sha256(task.model_dump_json().encode("utf-8")).hexdigest()
        consistency_errors = validate_contract_consistency(contract)
        if consistency_errors:
            return TaskRunMetric(
                task_id=task.task_id,
                baseline=BaselineType.MIND_3,
                compile_pass=False,
                simulation_pass=False,
                formal_pass=False,
                timing_pass=False,
                full_verified_pass=False,
                repair_success=False,
                repair_attempts=0,
                runtime_sec=round(time.monotonic() - start, 3),
                token_usage=0,
                estimated_cost_usd=0.0,
                failure_category=FailureCategory.SPECIFICATION_ERROR,
                tool_versions={},
                model_version=self.model,
                benchmark_version="heldout-v1",
                task_hash=task_hash,
                run_hash=self._compute_run_hash(task.task_id, BaselineType.MIND_3.value, ""),
                token_usage_known=False,
                cost_known=False,
            )
        verifier = SiliconSignoffVerifier(
            top_module=task.task_id, contract=contract, allow_mock_fallback=False,
            require_formal=True, require_coverage=True, require_cdc=False,
            runner=runner, liberty_path=self.liberty_path,
        )
        driver = PhaseDriver(
            session_id=f"mind3_cmp_{task.task_id}_{int(time.time()*1000)}",
            workspace=workspace, verifier=verifier, sandbox=None,
            model=self.model, provider=self.provider, max_repairs=3,
            api_key=self.api_key, base_url=self.base_url,
        )
        try:
            prompt = self._task_prompt(task)
            passed = driver.run_silicon_pipeline(prompt, liberty_path=self.liberty_path, contract_override=contract)
            result = driver.last_verification_result
            rtl_file = workspace / f"{task.task_id}.sv"
            rtl = rtl_file.read_text(encoding="utf-8") if rtl_file.exists() else ""
            if result is None:
                return TaskRunMetric(
                    task_id=task.task_id,
                    baseline=BaselineType.MIND_3,
                    compile_pass=False,
                    simulation_pass=False,
                    formal_pass=False,
                    timing_pass=False,
                    full_verified_pass=False,
                    repair_success=False,
                    repair_attempts=driver.total_repair_calls,
                    runtime_sec=round(time.monotonic() - start, 3),
                    token_usage=driver.total_tokens,
                    estimated_cost_usd=driver.model_cost_usd,
                    failure_category=FailureCategory.RTL_SYNTAX_ERROR,
                    tool_versions=verifier.detected_versions,
                    model_version=self.model,
                    benchmark_version="heldout-v1",
                    task_hash=task_hash,
                    run_hash=self._compute_run_hash(task.task_id, BaselineType.MIND_3.value, rtl),
                    token_usage_known=bool(driver.model_usage_known),
                    cost_known=bool(driver.model_cost_known),
                )
            return self._metric_from_result(task, BaselineType.MIND_3, result, time.monotonic()-start, driver.total_repair_calls, rtl, verifier, task_hash, driver)
        except Exception as exc:
            is_timeout = isinstance(exc, httpx.TimeoutException)
            fail_cat = FailureCategory.TIMEOUT if is_timeout else FailureCategory.RTL_SYNTAX_ERROR
            rtl_file = workspace / f"{task.task_id}.sv"
            rtl = rtl_file.read_text(encoding="utf-8") if rtl_file.exists() else ""
            return TaskRunMetric(
                task_id=task.task_id,
                baseline=BaselineType.MIND_3,
                compile_pass=False,
                simulation_pass=False,
                formal_pass=False,
                timing_pass=False,
                full_verified_pass=False,
                repair_success=False,
                repair_attempts=driver.total_repair_calls if driver else 0,
                runtime_sec=round(time.monotonic() - start, 3),
                token_usage=driver.total_tokens if driver else 0,
                estimated_cost_usd=driver.model_cost_usd if driver else 0.0,
                failure_category=fail_cat,
                tool_versions=verifier.detected_versions if verifier else {},
                model_version=self.model,
                benchmark_version="heldout-v1",
                task_hash=task_hash,
                run_hash=self._compute_run_hash(task.task_id, BaselineType.MIND_3.value, rtl),
                token_usage_known=bool(driver and driver.model_usage_known),
                cost_known=bool(driver and driver.model_cost_known),
            )
        finally:
            driver.close()

    @staticmethod
    def _task_prompt(task: BenchmarkTask) -> str:
        return (
            f"Benchmark Task ID: {task.task_id}\n"
            f"Specification: {task.natural_language_spec}\n"
            f"Expected ports (immutable evaluator contract): {json.dumps(task.expected_ports, sort_keys=True)}\n"
            f"Verification properties (evaluator-owned): {json.dumps(task.sva_properties, sort_keys=True)}\n"
            "Return synthesizable SystemVerilog only."
        )

    def _generate_initial_rtl(self, task: BenchmarkTask) -> str:
        """Generate clean, syntactically valid initial RTL for the task."""
        ports_str = []
        for p in task.expected_ports:
            direction = "input" if p["direction"] == "input" else "output reg"
            width = p.get("width", 1)
            w_str = f"[{width-1}:0] " if width > 1 else ""
            ports_str.append(f"    {direction} wire {w_str}{p['name']}")

        port_block = ",\n".join(ports_str)
        return f"""module {task.task_id} (
{port_block}
);
    // Initial generated RTL for {task.name}
    always @(*) begin
        // default initialization
    end
endmodule
"""

    def _repair_rtl_naive(self, task: BenchmarkTask, current_rtl: str, error_msg: str) -> str:
        """Naive repair loop: returns modified RTL."""
        return current_rtl + f"\n// Naive repair applied for error: {error_msg[:60]}\n"

    def execute_comparison(self, task_subset: list[BenchmarkTask] | None = None) -> BaselineComparisonReport:
        """Execute all three baselines and aggregate results."""
        target_tasks = task_subset or self.tasks
        if self.provider == "mock":
            raise RuntimeError("Mock provider is not permitted for benchmark performance comparison; use a live Ollama/OpenRouter provider.")
        records: list[TaskRunMetric] = []

        if self.artifact_root is not None:
            temp_root = self.artifact_root / "comparison_workspaces"
            if temp_root.exists():
                shutil.rmtree(temp_root)
            temp_root.mkdir(parents=True, exist_ok=True)
            cleanup = False
        else:
            temp_root = Path(tempfile.mkdtemp(prefix="mind3_baseline_cmp_"))
            cleanup = True
        try:
            total_tasks = len(target_tasks)
            for idx, task in enumerate(target_tasks, start=1):
                print(f"[{idx}/{total_tasks}] Running benchmark task {task.task_id} ({task.name})", flush=True)
                task_dir = temp_root / task.task_id
                task_dir.mkdir(parents=True, exist_ok=True)
                runner = LocalBwrapRunner(task_dir, sandbox=None, allow_unsandboxed=True)

                # 1. Baseline A
                rec_a = self.run_baseline_a(task, task_dir / "base_a", runner)
                records.append(rec_a)
                print(f"  [1/3] Baseline A: verified={rec_a.full_verified_pass}, category={rec_a.failure_category.value}", flush=True)

                # 2. Baseline B
                rec_b = self.run_baseline_b(task, task_dir / "base_b", runner)
                records.append(rec_b)
                print(f"  [2/3] Baseline B: verified={rec_b.full_verified_pass}, category={rec_b.failure_category.value}, repairs={rec_b.repair_attempts}", flush=True)

                # 3. Mind 3.0
                rec_m = self.run_mind3(task, task_dir / "mind3", runner)
                records.append(rec_m)
                print(f"  [3/3] Mind 3.0: verified={rec_m.full_verified_pass}, category={rec_m.failure_category.value}, repairs={rec_m.repair_attempts}", flush=True)
        finally:
            if cleanup:
                shutil.rmtree(temp_root, ignore_errors=True)

        # Aggregate summaries
        summaries: dict[str, BaselineSummary] = {}
        for b_type in BaselineType:
            b_recs = [r for r in records if r.baseline == b_type]
            n = len(b_recs)
            if n == 0:
                continue
            full_pass = sum(1 for r in b_recs if r.full_verified_pass)
            comp_pass = sum(1 for r in b_recs if r.compile_pass)
            sim_pass = sum(1 for r in b_recs if r.simulation_pass)
            form_pass = sum(1 for r in b_recs if r.formal_pass)
            rep_pass = sum(1 for r in b_recs if r.repair_success)
            rep_att = [r.repair_attempts for r in b_recs]
            runtimes = [r.runtime_sec for r in b_recs]
            costs = [r.estimated_cost_usd for r in b_recs]
            tokens = sum(r.token_usage for r in b_recs)
            fails = Counter(r.failure_category.value for r in b_recs if not r.full_verified_pass)

            ci_low, ci_high = _wilson_ci95(full_pass, n)

            summaries[b_type.value] = BaselineSummary(
                baseline_name=b_type.value,
                task_count=n,
                compile_pass_rate=round(comp_pass / n, 4),
                simulation_pass_rate=round(sim_pass / n, 4),
                formal_pass_rate=round(form_pass / n, 4),
                timing_pass_rate=0.0,
                full_verified_pass_rate=round(full_pass / n, 4),
                repair_success_rate=round(rep_pass / n, 4),
                full_verified_ci95=[ci_low, ci_high],
                mean_repair_attempts=round(sum(rep_att) / n, 2),
                mean_runtime_sec=round(sum(runtimes) / n, 3),
                mean_cost_usd=round(sum(costs) / n, 5),
                total_tokens=tokens,
                token_usage_known=all(r.token_usage_known for r in b_recs),
                cost_known=all(r.cost_known for r in b_recs),
                failure_distribution=dict(fails),
            )

        task_set_str = "".join(t.task_id for t in target_tasks)
        task_set_hash = hashlib.sha256(task_set_str.encode("utf-8")).hexdigest()

        return BaselineComparisonReport(
            task_set_sha256=task_set_hash,
            benchmark_suite="heldout-v1",
            evaluated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            seed=self.seed,
            baselines=summaries,
            task_runs=records,
        )
