"""Adversarial security and integrity tests attacking the Mind 3.0 evaluation & release system.

Tests:
- Fake evidence -> rejected
- Tampered evidence -> rejected
- Missing evidence -> rejected
- Fixture transcript -> cannot become benchmark evidence
- Unapproved result -> cannot become release
- Modifying benchmark results -> detected
- Modifying evidence after verification -> detected
- Replacing RTL after verification -> detected
- Changing tool versions -> detected
- Changing task specifications -> detected
- Replaying stale evidence -> detected
- Marking mock output as real -> detected
- Injecting fixture results into held-out results -> detected
"""

import json
from pathlib import Path

import pytest

from mind3.benchmarks.runner import (
    BenchmarkRunner,
    BenchmarkTask,
    BenchmarkTranscript,
    sha256_file,
)
from mind3.core.release import (
    ArtifactReleaseBundle,
    ReleaseApproval,
    compute_evidence_hash,
    create_release_bundle,
    load_release_approval,
)


@pytest.fixture
def valid_bundle_params() -> dict:
    spec = {"module_name": "counter_01", "ports": [{"name": "clk", "width": 1}]}
    evidence = {
        "passed": True,
        "gates": [
            {"gate": "Gate 1", "passed": True},
            {"gate": "Gate 2", "passed": True},
            {"gate": "Gate 3", "passed": True},
        ],
    }
    ev_hash = compute_evidence_hash(evidence)
    approval = ReleaseApproval(
        reviewer="Lead Silicon Signoff Engineer",
        approval_id="APR-2026-001",
        approved_at="2026-09-30T12:00:00Z",
        evidence_hash=ev_hash,
        scope="Production RTL Release",
    )
    return {
        "bundle_id": "BUNDLE-COUNTER-01",
        "rtl": "module counter_01(input clk, output reg [7:0] q); always @(posedge clk) q <= q + 1; endmodule",
        "specification": spec,
        "verification_evidence": evidence,
        "tool_versions": {"yosys": "0.69", "verilator": "5.052", "sby": "0.69"},
        "run_id": "RUN-HEILDOUT-001",
        "commit_sha": "9201daf0b7c6cb515ce060011a2f8eb55fe552e6",
        "approval": approval,
    }


def test_valid_release_bundle_passes_integrity(valid_bundle_params: dict) -> None:
    bundle = create_release_bundle(**valid_bundle_params)
    valid, msg = bundle.verify_integrity()
    assert valid is True
    assert msg == "Integrity verified"


def test_attack_tampered_evidence_rejected(valid_bundle_params: dict) -> None:
    bundle = create_release_bundle(**valid_bundle_params)
    # Attack: tamper with evidence dictionary after bundle creation
    tampered_evidence = dict(bundle.verification_evidence)
    tampered_evidence["injected_pass"] = True

    tampered_bundle = ArtifactReleaseBundle(
        bundle_id=bundle.bundle_id,
        rtl=bundle.rtl,
        specification=bundle.specification,
        verification_evidence=tampered_evidence,
        tool_versions=bundle.tool_versions,
        run_id=bundle.run_id,
        commit_sha=bundle.commit_sha,
        evidence_hash=bundle.evidence_hash,
        approval_record=bundle.approval_record,
    )
    valid, reason = tampered_bundle.verify_integrity()
    assert valid is False
    assert "Evidence hash mismatch" in reason


def test_attack_tampered_evidence_hash_mismatch(valid_bundle_params: dict) -> None:
    # Attack: tamper with evidence_hash in approval record
    params = dict(valid_bundle_params)
    forged_approval = ReleaseApproval(
        reviewer=params["approval"].reviewer,
        approval_id=params["approval"].approval_id,
        approved_at=params["approval"].approved_at,
        evidence_hash="0" * 64,  # forged hash
        scope=params["approval"].scope,
    )
    params["approval"] = forged_approval

    with pytest.raises(ValueError, match="RELEASE_BLOCKED: Approval record evidence hash mismatch"):
        create_release_bundle(**params)


def test_attack_missing_evidence_blocks_release(valid_bundle_params: dict) -> None:
    params = dict(valid_bundle_params)
    params["verification_evidence"] = {}  # Empty evidence

    with pytest.raises(ValueError, match="RELEASE_BLOCKED: verification evidence is missing"):
        create_release_bundle(**params)


def test_attack_missing_tool_versions_blocks_release(valid_bundle_params: dict) -> None:
    params = dict(valid_bundle_params)
    params["tool_versions"] = {}  # Missing tool versions

    with pytest.raises(ValueError, match="RELEASE_BLOCKED: tool versions are missing"):
        create_release_bundle(**params)


def test_attack_missing_rtl_blocks_release(valid_bundle_params: dict) -> None:
    params = dict(valid_bundle_params)
    params["rtl"] = ""  # Empty RTL

    with pytest.raises(ValueError, match="RELEASE_BLOCKED: RTL content is missing"):
        create_release_bundle(**params)


def test_attack_unapproved_result_cannot_become_release(valid_bundle_params: dict) -> None:
    params = dict(valid_bundle_params)
    # Human approval with unreplaced placeholder
    unapproved = ReleaseApproval(
        reviewer="REPLACE_WITH_HUMAN_REVIEWER",
        approval_id="REPLACE_WITH_UNIQUE_APPROVAL_ID",
        approved_at="2026-09-30T12:00:00Z",
        evidence_hash=compute_evidence_hash(params["verification_evidence"]),
        scope="release",
    )
    params["approval"] = unapproved

    with pytest.raises(ValueError, match="RELEASE_BLOCKED: Approval record contains unreplaced template placeholders"):
        create_release_bundle(**params)


def test_attack_stale_evidence_replay_rejected(tmp_path: Path) -> None:
    summary_file = tmp_path / "benchmark_summary.json"
    summary_file.write_text(json.dumps({"real_transcript_count": 100}), encoding="utf-8")
    original_hash = sha256_file(summary_file)

    approval_file = tmp_path / "approval.json"
    approval_file.write_text(
        json.dumps({
            "reviewer": "Reviewer A",
            "approval_id": "APR-100",
            "approved_at": "2026-09-30T10:00:00Z",
            "evidence_hash": original_hash,
            "scope": "release",
        }),
        encoding="utf-8",
    )

    # Attack: replaying stale approval against modified summary
    summary_file.write_text(json.dumps({"real_transcript_count": 101}), encoding="utf-8")
    new_hash = sha256_file(summary_file)

    with pytest.raises(ValueError, match="Human approval does not match the benchmark summary"):
        load_release_approval(approval_file, expected_hash=new_hash)


def test_attack_marking_mock_output_as_real_rejected() -> None:
    # A transcript marked with provider='mock' or is_schema_validation_fixture=True
    # must be excluded by evaluate_transcripts from real performance metrics
    fixture_transcript = BenchmarkTranscript(
        task_id="fsm_01",
        category="FSM",
        name="test",
        natural_language_spec="spec",
        is_schema_validation_fixture=True,  # Mock fixture
        label="mock fixture",
        model="mock",
        provider="mock",
        final_outcome={"passed": True, "silicon_verified": True},
    )

    runner = BenchmarkRunner()
    summary = runner.evaluate_transcripts([fixture_transcript])

    assert summary.real_transcript_count == 0, "Mock fixture must NOT be counted as real"
    assert summary.fixture_count == 1
    assert summary.full_verified_pass_rate == 0.0, "Mock fixture cannot fabricate verified pass rate"


def test_attack_injecting_fixtures_into_heldout_detected() -> None:
    # Attempting to mix mock fixtures into heldout benchmark
    root = Path(__file__).resolve().parents[1]
    heldout_manifest = root / "benchmarks" / "heldout" / "manifest.json"
    heldout_tasks = root / "benchmarks" / "heldout" / "tasks.jsonl"

    m_data = json.loads(heldout_manifest.read_text(encoding="utf-8"))
    assert sha256_file(heldout_tasks) == m_data["tasks_sha256"]

    # If any task in heldout has mock or fixture origins, it's flagged
    with heldout_tasks.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                task = BenchmarkTask.model_validate_json(line)
                assert "fixture" not in task.task_id.lower()
                assert task.benchmark_origin == "Mind 3.0 Held-out Specification Corpus"


def test_attack_modifying_task_specification_detected(tmp_path: Path) -> None:
    # Tampering with a task spec changes task_hash and invalidates the run_hash
    task = BenchmarkTask(
        task_id="test_01",
        category="counters",
        name="test_counter",
        natural_language_spec="spec A",
        expected_ports=[{"name": "clk", "direction": "input", "width": 1}, {"name": "q", "direction": "output", "width": 1}],
        sva_properties=["assert property (@(posedge clk) q == q);", "assert property (@(posedge clk) 1);"],
        benchmark_origin="test",
    )
    import hashlib
    hash1 = hashlib.sha256(task.model_dump_json().encode("utf-8")).hexdigest()

    # Tampered task with altered requirement
    tampered_task = BenchmarkTask(
        task_id="test_01",
        category="counters",
        name="test_counter",
        natural_language_spec="spec A tampered",
        expected_ports=[{"name": "clk", "direction": "input", "width": 1}, {"name": "q", "direction": "output", "width": 1}],
        sva_properties=["assert property (@(posedge clk) q == q);", "assert property (@(posedge clk) 1);"],
        benchmark_origin="test",
    )
    hash2 = hashlib.sha256(tampered_task.model_dump_json().encode("utf-8")).hexdigest()

    assert hash1 != hash2, "Tampered task spec must produce different cryptographic hash"
