"""Benchmark execution, transcript tuple extraction, and persistence pipeline for Mind 3.0.

Provides structured execution of RTL tasks through PhaseDriver with max_repairs=10,
extracting and persisting (contract, generated RTL, gate failure category, repair attempt, final outcome)
tuples to benchmarks/transcripts/.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from ..core.contracts import InterfaceContract, PortDefinition, PortDirection, SVAProperty, TimingConstraint
from ..core.driver import PhaseDriver
from ..core.types import PhaseEnum


class BenchmarkTask(BaseModel):
    """Specification of an RTL benchmark task."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1, description="Unique task identifier")
    category: str = Field(min_length=1, description="Benchmark category (FSM, Arithmetic, Bus Protocol, Memory Controller)")
    name: str = Field(min_length=1, description="Human-readable module name")
    natural_language_spec: str = Field(min_length=1, description="Detailed natural-language specification")
    expected_ports: list[dict[str, Any]] = Field(min_length=2, description="List of expected pinout ports")
    sva_properties: list[str] = Field(min_length=2, max_length=5, description="2-5 SVA properties for verification")
    benchmark_origin: str = Field(min_length=1, description="Origin attribution statement")


class RepairTurnRecord(BaseModel):
    """Record of an individual repair turn within the signoff loop."""

    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0, description="Repair turn index")
    guidance: str = Field(description="Error-guided feedback provided to the repair loop")
    repaired_rtl: str | None = Field(default=None, description="SystemVerilog RTL emitted by repair turn")
    passed: bool = Field(description="Whether signoff passed on this turn")
    error_category: str | None = Field(default=None, description="Signoff gate error category")
    failure_reason: str | None = Field(default=None, description="Detailed failure diagnostic message")
    gate_reports: list[dict[str, Any]] = Field(default_factory=list, description="Raw gate execution reports")


class BenchmarkTranscript(BaseModel):
    """Structured tuple capturing full end-to-end generation and verification of a benchmark task.

    Captures:
    1. Contract (InterfaceContract dict)
    2. Generated RTL (initial synthesizable SystemVerilog module)
    3. Gate failure category (or None if initial generation passed)
    4. Repair attempts (list of repair turns with guidance, RTL, and verification outcomes)
    5. Final outcome (passed, final status, turns taken, gate reports)
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, description="Benchmark task identifier")
    category: str = Field(min_length=1, description="Benchmark category")
    name: str = Field(min_length=1, description="Task name")
    natural_language_spec: str = Field(min_length=1, description="Natural-language prompt specification")
    is_schema_validation_fixture: bool = Field(
        default=False,
        description="True if generated from mock/fixture in environments lacking live inference",
    )
    label: str = Field(
        default="real generation output",
        description="Explicit truth-in-labeling tag",
    )
    model: str = Field(description="Generator model identifier")
    provider: str = Field(description="Inference provider (ollama, openrouter, mock)")
    max_repairs: int = Field(default=10, description="Maximum allowable repair turns ceiling")
    contract: dict[str, Any] | None = Field(
        default=None,
        description="Synthesized or supplied InterfaceContract schema",
    )
    generated_rtl: str | None = Field(
        default=None,
        description="Initial SystemVerilog code generated prior to repair loop",
    )
    gate_failure_category: str | None = Field(
        default=None,
        description="Initial signoff gate failure category, or None if initial success",
    )
    repair_attempts: list[RepairTurnRecord] = Field(
        default_factory=list,
        description="Chronological record of each repair turn taken",
    )
    final_outcome: dict[str, Any] = Field(
        default_factory=dict,
        description="Terminal outcome summary including passed status and total turns taken",
    )
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp of record creation")


class BenchmarkRunner:
    """Orchestrates benchmark task execution, transcript tuple extraction, and dataset persistence."""

    def __init__(
        self,
        tasks_file: Path | str | None = None,
        transcripts_dir: Path | str | None = None,
    ) -> None:
        root = Path(__file__).resolve().parent.parent.parent.parent
        self.tasks_file = (
            Path(tasks_file).resolve()
            if tasks_file is not None
            else root / "benchmarks" / "tasks.jsonl"
        )
        self.transcripts_dir = (
            Path(transcripts_dir).resolve()
            if transcripts_dir is not None
            else root / "benchmarks" / "transcripts"
        )
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

    def load_tasks(self) -> list[BenchmarkTask]:
        """Load all 50 benchmark tasks from tasks.jsonl."""
        if not self.tasks_file.exists():
            raise FileNotFoundError(f"Benchmark tasks file not found: {self.tasks_file}")
        tasks: list[BenchmarkTask] = []
        with open(self.tasks_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                tasks.append(BenchmarkTask.model_validate_json(line))
        return tasks

    @staticmethod
    def build_task_prompt(task: BenchmarkTask) -> str:
        """Construct a natural-language engineering prompt incorporating spec and expected ports."""
        port_lines = [
            f"  - {p['name']}: {p['direction']} [{p['width']} bit(s)] - {p.get('description', '')}"
            for p in task.expected_ports
        ]
        sva_lines = [f"  - {s}" for s in task.sva_properties]
        return (
            f"Module Name: {task.task_id}\n"
            f"Specification: {task.natural_language_spec}\n"
            f"Expected Interface Ports:\n" + "\n".join(port_lines) + "\n"
            f"Key Verification Properties to Satisfy:\n" + "\n".join(sva_lines)
        )

    def extract_transcript_tuple(
        self,
        task: BenchmarkTask,
        driver: PhaseDriver,
        final_passed: bool,
    ) -> BenchmarkTranscript:
        """Extract the (contract, generated_rtl, gate_failure_category, repair_attempts, final_outcome) tuple."""
        contract_dict: dict[str, Any] | None = None
        initial_rtl: str | None = None
        initial_failure_category: str | None = None
        repair_attempts: list[RepairTurnRecord] = []
        final_outcome: dict[str, Any] = {"passed": final_passed}

        current_guidance: str = ""
        current_repaired_rtl: str | None = None

        for rec in driver.transcript:
            phase = rec.phase
            payload = rec.event.payload

            if phase == PhaseEnum.PARSE and "ports" in payload:
                # Architect parsed contract
                contract_dict = payload
            elif phase == PhaseEnum.EXECUTE and payload.get("role") == "Principal RTL Design Engineer":
                initial_rtl = payload.get("rtl_file")
            elif phase == PhaseEnum.MODEL_CALL and payload.get("role") == "Targeted RTL Repair Loop":
                current_guidance = payload.get("guidance", "")
            elif phase == PhaseEnum.EXECUTE and payload.get("role") == "Targeted RTL Repair Loop":
                current_repaired_rtl = payload.get("rtl_file")
            elif phase == PhaseEnum.VERIFY:
                v_passed = payload.get("passed", False)
                v_cat = payload.get("error_category")
                v_reason = payload.get("failure_reason")
                v_reports = payload.get("gate_reports", [])

                turn_idx = rec.event.turn
                if turn_idx == 0:
                    if not v_passed:
                        initial_failure_category = v_cat
                else:
                    repair_attempts.append(
                        RepairTurnRecord(
                            turn=turn_idx,
                            guidance=current_guidance,
                            repaired_rtl=current_repaired_rtl,
                            passed=v_passed,
                            error_category=v_cat,
                            failure_reason=v_reason,
                            gate_reports=v_reports,
                        )
                    )
            elif phase == PhaseEnum.REPAIR_OR_FINISH:
                final_outcome = {
                    "passed": final_passed,
                    "status": payload.get("status", "COMPLETED"),
                    "turns_taken": payload.get("turns_taken", rec.event.turn + 1),
                    "silicon_verified": payload.get("silicon_verified", False),
                    "gate_reports": payload.get("gate_reports", []),
                }

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
            timestamp=time.time(),
        )

    def persist_transcript(self, transcript: BenchmarkTranscript) -> Path:
        """Persist a benchmark transcript to JSON in the transcripts directory."""
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        dest = self.transcripts_dir / f"{transcript.task_id}.json"
        dest.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
        return dest

    def create_schema_validation_fixture(
        self,
        task: BenchmarkTask,
        simulated_initial_pass: bool = False,
        simulated_converged: bool = True,
    ) -> BenchmarkTranscript:
        """Construct a rigorous schema-validation fixture for testing the persistence pipeline in isolation.

        Explicitly marked per Rule 1: 'schema-validation fixture, not real generation output'.
        """
        ports = [
            PortDefinition(
                name=p["name"],
                direction=PortDirection(p["direction"]),
                width=p["width"],
                description=p.get("description", ""),
            )
            for p in task.expected_ports
        ]
        sva = [
            SVAProperty(
                name=f"chk_prop_{i}",
                property_expr=task.sva_properties[i],
                description=f"Formal property {i}",
            )
            for i in range(len(task.sva_properties))
        ]
        contract = InterfaceContract(
            module_name=task.task_id,
            functional_spec=task.natural_language_spec,
            ports=ports,
            sva_properties=sva,
            timing=TimingConstraint(clock_name="clk", period_ns=10.0),
        )

        mock_rtl = (
            f"// [SCHEMA-VALIDATION FIXTURE - NOT REAL GENERATION OUTPUT]\n"
            f"module {task.task_id} (\n"
            + ",\n".join(f"  {p.to_verilog_declaration()}" for p in ports)
            + "\n);\n  // Synthesizable logic placeholder for schema validation\nendmodule\n"
        )

        repair_attempts: list[RepairTurnRecord] = []
        if simulated_initial_pass:
            init_cat = None
            final_outcome = {
                "passed": True,
                "status": "SILICON_VERIFIED",
                "turns_taken": 1,
                "silicon_verified": True,
                "gate_reports": [
                    {"gate": 1, "name": "Yosys Elaboration", "passed": True},
                    {"gate": 2, "name": "SymbiYosys Formal BMC", "passed": True},
                    {"gate": 3, "name": "Verilator LFSR Simulation", "passed": True},
                    {"gate": 4, "name": "OpenSTA Multi-Corner Timing", "passed": True},
                ],
            }
        elif simulated_converged:
            init_cat = "FORMAL_INVARIANT_BREACH"
            repair_attempts.append(
                RepairTurnRecord(
                    turn=1,
                    guidance="GATE 2 SIGN-OFF FAILURE: Formal SVA invariant breached in SymbiYosys BMC.",
                    repaired_rtl=mock_rtl,
                    passed=True,
                    error_category=None,
                    failure_reason=None,
                    gate_reports=[
                        {"gate": 1, "name": "Yosys Elaboration", "passed": True},
                        {"gate": 2, "name": "SymbiYosys Formal BMC", "passed": True},
                        {"gate": 3, "name": "Verilator LFSR Simulation", "passed": True},
                        {"gate": 4, "name": "OpenSTA Multi-Corner Timing", "passed": True},
                    ],
                )
            )
            final_outcome = {
                "passed": True,
                "status": "SILICON_VERIFIED",
                "turns_taken": 2,
                "silicon_verified": True,
                "gate_reports": [
                    {"gate": 1, "name": "Yosys Elaboration", "passed": True},
                    {"gate": 2, "name": "SymbiYosys Formal BMC", "passed": True},
                    {"gate": 3, "name": "Verilator LFSR Simulation", "passed": True},
                    {"gate": 4, "name": "OpenSTA Multi-Corner Timing", "passed": True},
                ],
            }
        else:
            init_cat = "TIMING_SLACK_VIOLATION"
            final_outcome = {
                "passed": False,
                "status": "REPAIR_EXHAUSTED",
                "turns_taken": 10,
                "silicon_verified": False,
                "gate_reports": [
                    {"gate": 1, "name": "Yosys Elaboration", "passed": True},
                    {"gate": 4, "name": "OpenSTA Timing", "passed": False, "details": "WNS violation: -0.150ns"},
                ],
            }

        return BenchmarkTranscript(
            task_id=task.task_id,
            category=task.category,
            name=task.name,
            natural_language_spec=task.natural_language_spec,
            is_schema_validation_fixture=True,
            label="schema-validation fixture, not real generation output",
            model="mock-fixture-generator",
            provider="mock",
            max_repairs=10,
            contract=contract.model_dump(mode="json"),
            generated_rtl=mock_rtl,
            gate_failure_category=init_cat,
            repair_attempts=repair_attempts,
            final_outcome=final_outcome,
            timestamp=time.time(),
        )

    def persist_all_fixtures(self, tasks: list[BenchmarkTask] | None = None) -> list[Path]:
        """Generate and persist schema-validation fixtures for the benchmark set."""
        if tasks is None:
            tasks = self.load_tasks()
        paths: list[Path] = []
        for i, task in enumerate(tasks):
            # Alternate realistic scenarios: turn-0 success, converged on turn 1, or exhausted
            sim_init_pass = (i % 3 == 0)
            sim_converged = (i % 3 != 2)
            fixture = self.create_schema_validation_fixture(
                task,
                simulated_initial_pass=sim_init_pass,
                simulated_converged=sim_converged,
            )
            paths.append(self.persist_transcript(fixture))
        return paths
