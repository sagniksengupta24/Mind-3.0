"""Canonical failure taxonomy and deterministic classifier for Mind 3.0.

Provides strict machine-readable failure categorization based on deterministic
EDA tool outputs, verifier reports, and execution state.

Enforces:
- Deterministic classification from concrete evidence
- LLM is NEVER permitted to arbitrarily assign its own failure category
- Complete preservation of raw evidence and fine-grained categories
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FailureCategory(StrEnum):
    """Canonical 12 failure categories required for Mind 3.0 benchmark & release evaluation."""

    SPECIFICATION_ERROR = "SPECIFICATION_ERROR"
    RTL_SYNTAX_ERROR = "RTL_SYNTAX_ERROR"
    RTL_SEMANTIC_ERROR = "RTL_SEMANTIC_ERROR"
    SIMULATION_FAILURE = "SIMULATION_FAILURE"
    FORMAL_FAILURE = "FORMAL_FAILURE"
    TIMING_FAILURE = "TIMING_FAILURE"
    CDC_FAILURE = "CDC_FAILURE"
    COVERAGE_FAILURE = "COVERAGE_FAILURE"
    REPAIR_FAILURE = "REPAIR_FAILURE"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class ClassifiedFailure(BaseModel):
    """Immutable classification result with evidence provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_category: FailureCategory
    fine_grained_category: str | None = None
    gate_name: str | None = None
    deterministic_evidence: str = Field(min_length=1)
    raw_error_snippet: str = ""


# Deterministic mapping table from fine-grained verifier categories to canonical FailureCategory
_FINE_GRAINED_MAP: dict[str, FailureCategory] = {
    # Specification issues
    "EMPTY_FORMAL_PROPERTY_SET": FailureCategory.SPECIFICATION_ERROR,
    "UNSUPPORTED_FORMAL_PROPERTY": FailureCategory.SPECIFICATION_ERROR,
    "SPECIFICATION_PARSING_FAILED": FailureCategory.SPECIFICATION_ERROR,
    "INVALID_CONTRACT": FailureCategory.SPECIFICATION_ERROR,
    "MISSING_SOURCE_FILES": FailureCategory.SPECIFICATION_ERROR,
    "MISSING_VERIFICATION_ARTIFACT": FailureCategory.SPECIFICATION_ERROR,
    # RTL Syntax issues
    "SYNTAX_ERROR": FailureCategory.RTL_SYNTAX_ERROR,
    "PARSE_ERROR": FailureCategory.RTL_SYNTAX_ERROR,
    "COVERAGE_BUILD_FAILURE": FailureCategory.RTL_SYNTAX_ERROR,
    # RTL Semantic issues
    "LATCH_INFERRED": FailureCategory.RTL_SEMANTIC_ERROR,
    "COMBINATIONAL_LOOP": FailureCategory.RTL_SEMANTIC_ERROR,
    "SYNTHESIS_ELABORATION_ERROR": FailureCategory.RTL_SEMANTIC_ERROR,
    "WIDTH_MISMATCH": FailureCategory.RTL_SEMANTIC_ERROR,
    "SIGNED_UNSIGNED_MISMATCH": FailureCategory.RTL_SEMANTIC_ERROR,
    "MULTIPLE_DRIVERS": FailureCategory.RTL_SEMANTIC_ERROR,
    # Simulation failures
    "SIMULATION_FAILURE": FailureCategory.SIMULATION_FAILURE,
    "SIMULATION_MISMATCH": FailureCategory.SIMULATION_FAILURE,
    "ASSERTION_FAILED": FailureCategory.SIMULATION_FAILURE,
    # Formal BMC failures
    "FORMAL_INVARIANT_BREACH": FailureCategory.FORMAL_FAILURE,
    # A vacuous result proves nothing (antecedent never exercised); a failed
    # reachability check is an analysis error. Both stay fine-grained exact
    # and are never relabeled as a proven violation.
    "VACUOUS_PROPERTY": FailureCategory.FORMAL_FAILURE,
    "FORMAL_ANALYSIS_FAILED": FailureCategory.FORMAL_FAILURE,
    "FORMAL_FAILURE": FailureCategory.FORMAL_FAILURE,
    "LEC_VERIFICATION_FAILED": FailureCategory.FORMAL_FAILURE,
    # Timing violations
    "TIMING_SLACK_VIOLATION": FailureCategory.TIMING_FAILURE,
    "HOLD_SLACK_VIOLATION": FailureCategory.TIMING_FAILURE,
    "TIMING_ANALYSIS_FAILED": FailureCategory.TIMING_FAILURE,
    "TIMING_REPORT_UNPARSEABLE": FailureCategory.TIMING_FAILURE,
    # CDC violations
    "CDC_VIOLATION": FailureCategory.CDC_FAILURE,
    "UNSYNCHRONIZED_CROSSING": FailureCategory.CDC_FAILURE,
    # CDC tooling/analysis failures: canonical bucket is environmental, but the
    # fine-grained category is preserved exactly and must never be relabeled
    # as CDC_VIOLATION (no crossing was proven).
    "CDC_TOOLING_UNAVAILABLE": FailureCategory.ENVIRONMENT_FAILURE,
    "CDC_ANALYSIS_FAILED": FailureCategory.ENVIRONMENT_FAILURE,
    # Coverage deficits
    "COVERAGE_DEFICIT": FailureCategory.COVERAGE_FAILURE,
    "LOW_BRANCH_COVERAGE": FailureCategory.COVERAGE_FAILURE,
    "LOW_TOGGLE_COVERAGE": FailureCategory.COVERAGE_FAILURE,
    # Repair failures
    "REPAIR_BUDGET_EXHAUSTED": FailureCategory.REPAIR_FAILURE,
    "MAX_TURNS_EXCEEDED": FailureCategory.REPAIR_FAILURE,
    "REPAIR_PATCH_REJECTED": FailureCategory.REPAIR_FAILURE,
    # Environment issues
    "EDA_BINARY_MISSING": FailureCategory.ENVIRONMENT_FAILURE,
    "SANDBOX_UNAVAILABLE": FailureCategory.ENVIRONMENT_FAILURE,
    "TOOL_SEGFAULT": FailureCategory.ENVIRONMENT_FAILURE,
    "MISSING_LIBERTY_FOR_PNR": FailureCategory.ENVIRONMENT_FAILURE,
    "MISSING_NETLIST_FOR_PNR": FailureCategory.ENVIRONMENT_FAILURE,
    "MISSING_NETLIST_FOR_LEC": FailureCategory.ENVIRONMENT_FAILURE,
    # Timeouts
    "EXECUTION_TIMEOUT": FailureCategory.TIMEOUT,
    "TIMEOUT": FailureCategory.TIMEOUT,
}


def classify_failure(
    *,
    error_category: str | None = None,
    failure_reason: str | None = None,
    stdout: str = "",
    stderr: str = "",
    gate_reports: list[dict[str, Any]] | None = None,
    exit_code: int | None = None,
) -> ClassifiedFailure:
    """Classify a failure into one of the 12 canonical failure categories deterministically."""
    combined_log = f"{stdout}\n{stderr}".strip()
    fine = (error_category or "").strip()

    # 1. Check direct fine-grained category mapping
    if fine and fine in _FINE_GRAINED_MAP:
        return ClassifiedFailure(
            canonical_category=_FINE_GRAINED_MAP[fine],
            fine_grained_category=fine,
            deterministic_evidence=f"Direct category match: {fine}",
            raw_error_snippet=(failure_reason or combined_log[:300]).strip(),
        )

    # 2. Check gate reports for first failing gate
    if gate_reports:
        for gate in gate_reports:
            if not gate.get("passed", False):
                gate_name = gate.get("gate", "Unknown Gate")
                g_cat = gate.get("error_category")
                g_det = gate.get("details", "")
                if g_cat and str(g_cat) in _FINE_GRAINED_MAP:
                    return ClassifiedFailure(
                        canonical_category=_FINE_GRAINED_MAP[str(g_cat)],
                        fine_grained_category=str(g_cat),
                        gate_name=gate_name,
                        deterministic_evidence=f"Gate failure in '{gate_name}': {g_cat}",
                        raw_error_snippet=g_det[:300].strip(),
                    )
                # Fallback gate name pattern matching
                if "Gate 1:" in gate_name or "Yosys" in gate_name:
                    if "latch" in g_det.lower():
                        return ClassifiedFailure(
                            canonical_category=FailureCategory.RTL_SEMANTIC_ERROR,
                            fine_grained_category="LATCH_INFERRED",
                            gate_name=gate_name,
                            deterministic_evidence="Gate 1 detected inferred latch",
                            raw_error_snippet=g_det[:300].strip(),
                        )
                    if "loop" in g_det.lower():
                        return ClassifiedFailure(
                            canonical_category=FailureCategory.RTL_SEMANTIC_ERROR,
                            fine_grained_category="COMBINATIONAL_LOOP",
                            gate_name=gate_name,
                            deterministic_evidence="Gate 1 detected combinational loop",
                            raw_error_snippet=g_det[:300].strip(),
                        )
                    if "syntax" in combined_log.lower() or "syntax error" in g_det.lower():
                        return ClassifiedFailure(
                            canonical_category=FailureCategory.RTL_SYNTAX_ERROR,
                            fine_grained_category="SYNTAX_ERROR",
                            gate_name=gate_name,
                            deterministic_evidence="Gate 1 elaboration syntax error",
                            raw_error_snippet=g_det[:300].strip(),
                        )
                    return ClassifiedFailure(
                        canonical_category=FailureCategory.RTL_SEMANTIC_ERROR,
                        fine_grained_category="SYNTHESIS_ELABORATION_ERROR",
                        gate_name=gate_name,
                        deterministic_evidence="Gate 1 synthesis/elaboration failure",
                        raw_error_snippet=g_det[:300].strip(),
                    )
                if "Gate 2:" in gate_name or "Formal" in gate_name:
                    return ClassifiedFailure(
                        canonical_category=FailureCategory.FORMAL_FAILURE,
                        fine_grained_category="FORMAL_INVARIANT_BREACH",
                        gate_name=gate_name,
                        deterministic_evidence="Gate 2 formal verification failed",
                        raw_error_snippet=g_det[:300].strip(),
                    )
                if "Gate 3:" in gate_name or "Coverage" in gate_name or "Simulation" in gate_name:
                    if "deficit" in g_det.lower() or "coverage" in g_det.lower():
                        return ClassifiedFailure(
                            canonical_category=FailureCategory.COVERAGE_FAILURE,
                            fine_grained_category="COVERAGE_DEFICIT",
                            gate_name=gate_name,
                            deterministic_evidence="Gate 3 coverage threshold deficit",
                            raw_error_snippet=g_det[:300].strip(),
                        )
                    return ClassifiedFailure(
                        canonical_category=FailureCategory.SIMULATION_FAILURE,
                        fine_grained_category="SIMULATION_FAILURE",
                        gate_name=gate_name,
                        deterministic_evidence="Gate 3 simulation failed",
                        raw_error_snippet=g_det[:300].strip(),
                    )
                if "Gate 4:" in gate_name or "Timing" in gate_name:
                    return ClassifiedFailure(
                        canonical_category=FailureCategory.TIMING_FAILURE,
                        fine_grained_category="TIMING_SLACK_VIOLATION",
                        gate_name=gate_name,
                        deterministic_evidence="Gate 4 timing constraint violation",
                        raw_error_snippet=g_det[:300].strip(),
                    )
                if "Gate 6:" in gate_name or "CDC" in gate_name:
                    return ClassifiedFailure(
                        canonical_category=FailureCategory.CDC_FAILURE,
                        fine_grained_category="CDC_VIOLATION",
                        gate_name=gate_name,
                        deterministic_evidence="Gate 6 clock domain crossing violation",
                        raw_error_snippet=g_det[:300].strip(),
                    )

    # 3. Deterministic inspection of raw logs and exit codes
    if exit_code == 124 or "timed out" in combined_log.lower() or "timeout" in combined_log.lower():
        return ClassifiedFailure(
            canonical_category=FailureCategory.TIMEOUT,
            fine_grained_category="TIMEOUT",
            deterministic_evidence=f"Process exited with timeout (code {exit_code})",
            raw_error_snippet=combined_log[:300],
        )

    if "binary missing" in combined_log.lower() or "not found on path" in combined_log.lower() or exit_code == 127:
        return ClassifiedFailure(
            canonical_category=FailureCategory.ENVIRONMENT_FAILURE,
            fine_grained_category="EDA_BINARY_MISSING",
            deterministic_evidence="Missing binary detected on PATH or exit code 127",
            raw_error_snippet=combined_log[:300],
        )

    if re.search(r"\b(?:assertion|assert)\s+(?:violation|failed|failure)\b|\$fatal\b|\bMISMATCH\b", combined_log, re.IGNORECASE):
        return ClassifiedFailure(
            canonical_category=FailureCategory.SIMULATION_FAILURE,
            fine_grained_category="ASSERTION_FAILED",
            deterministic_evidence="Simulation assertion or fatal mismatch signature detected in logs",
            raw_error_snippet=combined_log[:300],
        )

    if "syntax error" in combined_log.lower() or "syntax_error" in combined_log.lower():
        return ClassifiedFailure(
            canonical_category=FailureCategory.RTL_SYNTAX_ERROR,
            fine_grained_category="SYNTAX_ERROR",
            deterministic_evidence="Syntax error string detected in tool compilation output",
            raw_error_snippet=combined_log[:300],
        )

    if "latch" in combined_log.lower():
        return ClassifiedFailure(
            canonical_category=FailureCategory.RTL_SEMANTIC_ERROR,
            fine_grained_category="LATCH_INFERRED",
            deterministic_evidence="Latch inference signature detected in synthesis log",
            raw_error_snippet=combined_log[:300],
        )

    if "combinational loop" in combined_log.lower():
        return ClassifiedFailure(
            canonical_category=FailureCategory.RTL_SEMANTIC_ERROR,
            fine_grained_category="COMBINATIONAL_LOOP",
            deterministic_evidence="Combinational loop detected in synthesis log",
            raw_error_snippet=combined_log[:300],
        )

    # 4. Fallback: unknown
    return ClassifiedFailure(
        canonical_category=FailureCategory.UNKNOWN,
        fine_grained_category=fine or "UNKNOWN",
        deterministic_evidence="Unclassified failure pattern",
        raw_error_snippet=(failure_reason or combined_log[:300]).strip() or "No output available",
    )
