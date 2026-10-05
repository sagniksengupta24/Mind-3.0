"""Fail-closed human approval and evidence-bundle helpers.

Enforces:
generation -> verification -> evidence -> human approval -> release

The release bundle MUST contain:
1. RTL
2. specification
3. verification evidence
4. tool versions
5. benchmark/run ID
6. commit SHA
7. evidence hash
8. approval record

Any missing or tampered component strictly blocks release.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReleaseApproval(BaseModel):
    """Human approval bound to an exact evidence artifact hash."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    reviewer: str = Field(min_length=1)
    approval_id: str = Field(min_length=1)
    approved_at: str = Field(min_length=1)
    evidence_hash: str = Field(min_length=64, max_length=64)
    benchmark_summary_sha256: str = Field(default="", min_length=0)
    scope: str = Field(min_length=1)

    def model_post_init(self, __context: Any) -> None:
        if not self.benchmark_summary_sha256 and self.evidence_hash:
            object.__setattr__(self, "benchmark_summary_sha256", self.evidence_hash)
        elif not self.evidence_hash and self.benchmark_summary_sha256:
            object.__setattr__(self, "evidence_hash", self.benchmark_summary_sha256)


class ArtifactReleaseBundle(BaseModel):
    """Immutable, fully-auditable verified release bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str = Field(min_length=1)
    rtl: str = Field(min_length=10)
    specification: dict[str, Any] = Field(min_length=1)
    verification_evidence: dict[str, Any] = Field(min_length=1)
    tool_versions: dict[str, str] = Field(min_length=1)
    run_id: str = Field(min_length=1)
    commit_sha: str = Field(min_length=7)
    evidence_hash: str = Field(min_length=64, max_length=64)
    approval_record: ReleaseApproval

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify that evidence hash and approval record strictly match."""
        evidence_json = json.dumps(self.verification_evidence, sort_keys=True, separators=(",", ":"))
        expected_hash = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()

        if self.evidence_hash != expected_hash:
            return False, f"Evidence hash mismatch: declared {self.evidence_hash} != computed {expected_hash}"

        if self.approval_record.evidence_hash != self.evidence_hash:
            return False, (
                f"Approval record evidence hash mismatch: "
                f"approval={self.approval_record.evidence_hash} != bundle={self.evidence_hash}"
            )

        if any(
            v.startswith("REPLACE_WITH_")
            for v in (self.approval_record.reviewer, self.approval_record.approval_id, self.approval_record.approved_at)
        ):
            return False, "Approval record contains unreplaced template placeholders"

        try:
            datetime.fromisoformat(self.approval_record.approved_at.replace("Z", "+00:00"))
        except ValueError as exc:
            return False, f"Invalid ISO-8601 approved_at timestamp: {exc}"

        return True, "Integrity verified"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_evidence_hash(evidence: dict[str, Any]) -> str:
    evidence_json = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()


def load_release_approval(approval_path: Path | str, expected_hash: str) -> ReleaseApproval:
    path = Path(approval_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Human approval file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "benchmark_summary_sha256" in data and not data.get("evidence_hash"):
        data["evidence_hash"] = data["benchmark_summary_sha256"]
    elif "evidence_hash" in data and not data.get("benchmark_summary_sha256"):
        data["benchmark_summary_sha256"] = data["evidence_hash"]

    approval = ReleaseApproval.model_validate(data)
    if any(value.startswith("REPLACE_WITH_") for value in (approval.reviewer, approval.approval_id, approval.approved_at)):
        raise ValueError("Human approval still contains template placeholders")
    try:
        datetime.fromisoformat(approval.approved_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Human approval approved_at must be an ISO-8601 timestamp") from exc
    if approval.evidence_hash != expected_hash:
        raise ValueError(f"Human approval does not match the benchmark summary SHA-256 (declared {approval.evidence_hash} != expected {expected_hash})")
    return approval


def write_approval_template(output_path: Path | str, evidence_target: Path | str, scope: str) -> Path:
    p = Path(evidence_target)
    if p.is_file():
        h = sha256_file(p)
    else:
        h = str(evidence_target)
    approval_dict = {
        "reviewer": "REPLACE_WITH_HUMAN_REVIEWER",
        "approval_id": "REPLACE_WITH_UNIQUE_APPROVAL_ID",
        "approved_at": "REPLACE_WITH_ISO8601_TIMESTAMP",
        "evidence_hash": h,
        "benchmark_summary_sha256": h,
        "scope": scope,
    }
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(approval_dict, indent=2) + "\n", encoding="utf-8")
    return out


def create_release_bundle(
    *,
    bundle_id: str,
    rtl: str,
    specification: dict[str, Any],
    verification_evidence: dict[str, Any],
    tool_versions: dict[str, str],
    run_id: str,
    commit_sha: str,
    approval: ReleaseApproval,
) -> ArtifactReleaseBundle:
    """Build and validate an ArtifactReleaseBundle with strict fail-closed integrity checks."""
    if not rtl or len(rtl.strip()) < 10:
        raise ValueError("RELEASE_BLOCKED: RTL content is missing or too short.")
    if not specification:
        raise ValueError("RELEASE_BLOCKED: specification is empty.")
    if not verification_evidence:
        raise ValueError("RELEASE_BLOCKED: verification evidence is missing.")
    if not tool_versions:
        raise ValueError("RELEASE_BLOCKED: tool versions are missing.")
    if not run_id:
        raise ValueError("RELEASE_BLOCKED: run_id is missing.")
    if not commit_sha:
        raise ValueError("RELEASE_BLOCKED: commit_sha is missing.")

    evidence_hash = compute_evidence_hash(verification_evidence)

    bundle = ArtifactReleaseBundle(
        bundle_id=bundle_id,
        rtl=rtl,
        specification=specification,
        verification_evidence=verification_evidence,
        tool_versions=tool_versions,
        run_id=run_id,
        commit_sha=commit_sha,
        evidence_hash=evidence_hash,
        approval_record=approval,
    )

    valid, reason = bundle.verify_integrity()
    if not valid:
        raise ValueError(f"RELEASE_BLOCKED: {reason}")

    return bundle
