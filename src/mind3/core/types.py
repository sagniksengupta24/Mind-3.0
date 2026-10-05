"""
Pydantic v2 data models, actions, telemetry events, and verification schemas for Mind 3.0.
"""

from __future__ import annotations

import hashlib
import json
import time
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class PhaseEnum(StrEnum):
    """The 11 strict lifecycle phases executed sequentially in Mind 3.0."""

    INTAKE = "INTAKE"
    ROUTE = "ROUTE"
    SNAPSHOT = "SNAPSHOT"
    MODEL_CALL = "MODEL_CALL"
    PARSE = "PARSE"
    POLICY_CHECK = "POLICY_CHECK"
    EXECUTE = "EXECUTE"
    OBSERVE = "OBSERVE"
    VERIFY = "VERIFY"
    REPAIR_OR_FINISH = "REPAIR_OR_FINISH"
    TRACE = "TRACE"


class WriteFileAction(BaseModel):
    """Host-side file mutation action with strict path canonicalization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["write_file"] = "write_file"
    path: str = Field(
        min_length=1,
        description="Target file path relative to workspace root",
    )
    content: str = Field(
        description="Full text content to write to the designated file",
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Target file path cannot be empty or whitespace.")
        return cleaned


class RunCommandAction(BaseModel):
    """Sandbox-confined command execution action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["run_command"] = "run_command"
    command: list[str] = Field(
        min_length=1,
        description="Non-empty array of command and arguments to execute inside Bubblewrap",
    )
    timeout_sec: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Maximum execution time limit in seconds",
    )

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Command list cannot be empty.")
        if not v[0].strip():
            raise ValueError("Executable binary name cannot be empty or whitespace.")
        return v


class RunSkillScriptAction(BaseModel):
    """Sandbox-confined skill script execution action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["run_skill_script"] = "run_skill_script"
    skill_name: str = Field(
        min_length=1,
        description="Target skill identifier (e.g. industry-report-analyst or semiconductor-vlsi)",
    )
    script_name: str = Field(
        min_length=1,
        description="Relative script path within the skill (e.g. scripts/generate_timeline_chart.py)",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command-line arguments to provide to the script",
    )
    timeout_sec: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Maximum execution time limit in seconds",
    )

    @field_validator("skill_name", "script_name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Skill and script names cannot be empty or whitespace.")
        return cleaned


class WriteBatchFilesAction(BaseModel):
    """Host-side atomic multi-file mutation action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["write_batch_files"] = "write_batch_files"
    files: list[WriteFileAction] = Field(
        min_length=1,
        description="List of WriteFileAction items to stage atomically",
    )


AgentAction = Annotated[
    Union[WriteFileAction, RunCommandAction, RunSkillScriptAction, WriteBatchFilesAction],
    Field(discriminator="action"),
]

agent_action_adapter: TypeAdapter[AgentAction] = TypeAdapter(AgentAction)


class VerificationDomain(StrEnum):
    """Target verification domain supported by Mind 3.0."""

    RTL = "RTL"
    SOFTWARE = "SOFTWARE"
    PHYSICAL_DESIGN = "PHYSICAL_DESIGN"
    VLSI_DEVICE = "VLSI_DEVICE"
    INDUSTRY_REPORT = "INDUSTRY_REPORT"


class VerificationResult(BaseModel):
    """Immutable outcome emitted by the verification subsystem."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool = Field(
        description="True only if compilation and test execution succeeded with zero errors",
    )
    domain: VerificationDomain = Field(
        description="Verification domain (RTL or SOFTWARE)",
    )
    exit_code: int = Field(
        description="Process exit code of the final verification binary/runner",
    )
    stdout: str = Field(
        default="",
        description="Standard output captured during verification execution",
    )
    stderr: str = Field(
        default="",
        description="Standard error captured during verification execution",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Diagnostic failure rationale if passed is False",
    )
    error_category: str | None = Field(
        default=None,
        description="Structured failure categorization (e.g. LATCH_INFERRED, FORMAL_INVARIANT_BREACH)",
    )
    silicon_verified: bool = Field(
        default=False,
        description="True if the configured OSS RTL-validation gates passed; not a tapeout claim",
    )
    tapeout_ready: bool = Field(
        default=False,
        description="True only when independently produced tapeout-readiness evidence is clean",
    )
    netlist_path: str | None = Field(
        default=None,
        description="Relative path to Gate 1 synthesized netlist if produced",
    )
    coverage_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Measured coverage values (e.g. line, branch, toggle)",
    )
    timing_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Measured timing metrics (e.g. wns, tns)",
    )
    gate_reports: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Detailed gate-by-gate verification diagnostics",
    )
    hold_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Hold-path timing metrics (e.g. hold_wns, hold_tns) from OpenSTA min-path analysis",
    )
    cdc_violations: list[str] = Field(
        default_factory=list,
        description="Clock-domain crossing warning messages emitted by Gate 6 Yosys CDC analysis",
    )
    dft_audit: dict[str, Any] = Field(
        default_factory=dict,
        description="Advisory DFT scan-chain report: dff_count, has_scan_port, needs_scan, advisory messages",
    )
    tapeout_evidence: dict[str, bool] = Field(
        default_factory=dict,
        description="TapeoutReadinessVerifier receipt checklist: maps receipt key to presence boolean",
    )
    pnr_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="OpenROAD place-and-route metrics: pnr_complete, placement_overflow, routing_congestion",
    )
    commercial_signoff: dict[str, Any] = Field(
        default_factory=dict,
        description="Commercial EDA signoff metrics across PrimeTime, Innovus, Calibre, Tessent",
    )


class TelemetryEvent(BaseModel):
    """Telemetry payload captured at each phase transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str = Field(
        min_length=1,
        description="Unique identifier of the active execution session",
    )
    phase: PhaseEnum = Field(
        description="Lifecycle phase currently emitting telemetry",
    )
    turn: int = Field(
        ge=0,
        description="Current repair loop iteration count",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary structured metadata recorded for the phase",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="POSIX epoch timestamp of event creation",
    )


class TraceRecord(BaseModel):
    """Cryptographically chained audit record persisted to transcript.jsonl."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_index: int = Field(
        ge=0,
        description="Monotonically increasing 0-indexed step sequence",
    )
    phase: PhaseEnum = Field(
        description="Lifecycle phase associated with this record",
    )
    prev_hash: str = Field(
        min_length=64,
        max_length=64,
        description="Hex-encoded SHA-256 digest of preceding trace record",
    )
    current_hash: str = Field(
        min_length=64,
        max_length=64,
        description="Hex-encoded SHA-256 digest computed over prev_hash and record content",
    )
    event: TelemetryEvent = Field(
        description="Associated telemetry payload for this trace step",
    )

    def compute_expected_hash(self) -> str:
        """Compute the deterministic canonical SHA-256 digest matching Invariant 4."""
        record_body: dict[str, Any] = {
            "step_index": self.step_index,
            "phase": self.phase.value,
            "prev_hash": self.prev_hash,
            "event": self.event.model_dump(mode="json"),
        }
        canonical_json = json.dumps(record_body, sort_keys=True, separators=(",", ":"))
        hasher = hashlib.sha256()
        hasher.update(self.prev_hash.encode("utf-8"))
        hasher.update(canonical_json.encode("utf-8"))
        return hasher.hexdigest()

    def is_hash_valid(self) -> bool:
        """Verify that current_hash strictly matches computed expected hash."""
        return self.current_hash == self.compute_expected_hash()

    def to_jsonl(self) -> str:
        """Serialize record into single-line canonical JSON."""
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )


__all__ = [
    "PhaseEnum",
    "WriteFileAction",
    "RunCommandAction",
    "RunSkillScriptAction",
    "WriteBatchFilesAction",
    "AgentAction",
    "agent_action_adapter",
    "VerificationDomain",
    "VerificationResult",
    "TelemetryEvent",
    "TraceRecord",
]
