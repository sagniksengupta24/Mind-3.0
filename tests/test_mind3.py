"""
Comprehensive test suite for Mind 3.0.
Verifies Pydantic v2 schemas, sandboxing invariants, verifiers, policy checks, rollback recovery, and hash chaining.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from mind3.core.driver import (
    OpenRouterModelRegistry,
    OpenRouterModelRegistryError,
    PhaseDriver,
    _parse_model_code_response,
    _sanitize_json_output,
    fetch_openrouter_free_models,
)
from mind3.core.types import (
    AgentAction,
    PhaseEnum,
    RunCommandAction,
    RunSkillScriptAction,
    TelemetryEvent,
    TraceRecord,
    VerificationDomain,
    VerificationResult,
    WriteBatchFilesAction,
    WriteFileAction,
    agent_action_adapter,
)
from mind3.core.contracts import (
    ContractSynthesizer,
    InterfaceContract,
    PortDefinition,
    PortDirection,
    RTLGenerator,
    SVAProperty,
    TimingConstraint,
    VerificationHarnessGenerator,
)
# PortSpec: alias for PortDefinition used in new test cases
PortSpec = PortDefinition

from mind3.core.verifier import (
    BaseVerifier,
    RTLVerifier,
    SiliconSignoffVerifier,
    SoftwareVerifier,
    TapeoutReadinessVerifier,
    parse_opensta_mcmm,
    parse_opensta_wns,
)
from mind3.sandbox.bwrap import BubblewrapSandbox
from mind3.sandbox.remote_eda import (
    EDARunner,
    LocalBwrapRunner,
    RemoteSSHRunner,
    get_eda_runner,
)


class MockSandbox:
    """Mock sandbox to record commands and simulate process outcomes."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()
        self.executed_commands: list[list[str]] = []
        self.mock_returncode: int = 0
        self.mock_stdout: str = "PASS"
        self.mock_stderr: str = ""

    def run(self, command: list[str], timeout_sec: int = 30) -> subprocess.CompletedProcess[str]:
        self.executed_commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=self.mock_returncode,
            stdout=self.mock_stdout,
            stderr=self.mock_stderr,
        )


class MockVerifier(BaseVerifier):
    """Mock verification oracle for driving phase execution."""

    def __init__(self, should_pass: bool = True) -> None:
        self.should_pass = should_pass
        self.verify_calls = 0

    def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
        self.verify_calls += 1
        return VerificationResult(
            passed=self.should_pass,
            domain=VerificationDomain.SOFTWARE,
            exit_code=0 if self.should_pass else 1,
            stdout="Simulated test run completed",
            stderr="" if self.should_pass else "Assertion failure in module",
            failure_reason=None if self.should_pass else "Assertion failure",
        )


# ── Types & Action Validation Tests ──────────────────────────────────────────


def test_agent_action_discrimination() -> None:
    write_payload = {
        "action": "write_file",
        "path": "src/top.v",
        "content": "module top(); endmodule",
    }
    action1 = agent_action_adapter.validate_python(write_payload)
    assert isinstance(action1, WriteFileAction)
    assert action1.path == "src/top.v"

    cmd_payload = {
        "action": "run_command",
        "command": ["pytest", "tests/"],
        "timeout_sec": 45,
    }
    action2 = agent_action_adapter.validate_python(cmd_payload)
    assert isinstance(action2, RunCommandAction)
    assert action2.command == ["pytest", "tests/"]
    assert action2.timeout_sec == 45

    with pytest.raises(ValidationError):
        agent_action_adapter.validate_python({"action": "unsupported_action"})

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        agent_action_adapter.validate_python({
            "action": "write_file",
            "path": "test.txt",
            "content": "abc",
            "extra_field": "disallowed",
        })


def test_action_validators() -> None:
    with pytest.raises(ValidationError):
        WriteFileAction(path="   ", content="hello")

    with pytest.raises(ValidationError):
        RunCommandAction(command=[])

    with pytest.raises(ValidationError):
        RunCommandAction(command=["  "])

    with pytest.raises(ValidationError):
        RunCommandAction(command=[""])

    with pytest.raises(ValidationError):
        RunCommandAction(command=["ls"], timeout_sec=0)  # type: ignore

    with pytest.raises(ValidationError):
        RunCommandAction(command=["ls"], timeout_sec=121)  # type: ignore


def test_base_verifier_raises_not_implemented() -> None:
    class DummyVerifier(BaseVerifier):
        def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
            return super().verify(workspace, sandbox)  # type: ignore

    dummy = DummyVerifier()
    with pytest.raises(NotImplementedError):
        dummy.verify(Path("/tmp"), None)  # type: ignore


def test_driver_context_manager() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_sb = MockSandbox(Path(tmpdir))
        with PhaseDriver(
            session_id="cm-test",
            workspace=Path(tmpdir),
            verifier=MockVerifier(),
            sandbox=mock_sb,  # type: ignore
        ) as driver:
            assert driver.session_id == "cm-test"


# ── Trace Hashing & Verification Tests ───────────────────────────────────────


def test_trace_record_hashing_and_validation() -> None:
    prev_hash = "0" * 64
    event = TelemetryEvent(
        session_id="session-001",
        phase=PhaseEnum.INTAKE,
        turn=0,
        payload={"workspace": Path("/tmp/workspace")},
        timestamp=1700000000.0,
    )

    record_body = {
        "step_index": 0,
        "phase": PhaseEnum.INTAKE.value,
        "prev_hash": prev_hash,
        "event": event.model_dump(mode="json"),
    }
    canonical_json = json.dumps(record_body, sort_keys=True, separators=(",", ":"))
    hasher = hashlib.sha256()
    hasher.update(prev_hash.encode("utf-8"))
    hasher.update(canonical_json.encode("utf-8"))
    expected_hash = hasher.hexdigest()

    record = TraceRecord(
        step_index=0,
        phase=PhaseEnum.INTAKE,
        prev_hash=prev_hash,
        current_hash=expected_hash,
        event=event,
    )
    assert record.is_hash_valid() is True
    assert record.compute_expected_hash() == expected_hash

    # Tampered record fails validation
    tampered = TraceRecord(
        step_index=0,
        phase=PhaseEnum.INTAKE,
        prev_hash=prev_hash,
        current_hash="1" * 64,
        event=event,
    )
    assert tampered.is_hash_valid() is False


def test_trace_record_to_jsonl_serialization() -> None:
    event = TelemetryEvent(
        session_id="s1",
        phase=PhaseEnum.ROUTE,
        turn=1,
        payload={"nested": {"path": Path("/a/b")}},
    )
    record = TraceRecord(
        step_index=1,
        phase=PhaseEnum.ROUTE,
        prev_hash="a" * 64,
        current_hash="b" * 64,
        event=event,
    )
    jsonl_str = record.to_jsonl()
    parsed = json.loads(jsonl_str)
    assert parsed["step_index"] == 1
    assert parsed["event"]["payload"]["nested"]["path"] == "/a/b"


# ── Sandbox Tests ────────────────────────────────────────────────────────────


def test_bwrap_missing_binary_raises() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(RuntimeError) as exc_info:
            BubblewrapSandbox(
                workspace=Path(tmpdir),
                bwrap_binary="/nonexistent/bwrap_binary_path",
            )
        assert "bwrap binary not found on PATH" in str(exc_info.value)


def test_bwrap_empty_command_returns_error() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock bwrap path using dummy placeholder to test run() method directly
        sb = BubblewrapSandbox.__new__(BubblewrapSandbox)
        sb.workspace = Path(tmpdir).resolve()
        sb._bwrap_bin = "/usr/bin/true"

        res = sb.run([])
        assert res.returncode == 1
        assert "empty command list" in res.stderr


# ── Verifier Tests ───────────────────────────────────────────────────────────


def test_rtl_verifier_discovery_and_command_construction() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        alu = ws / "alu.v"
        alu.write_text("module alu(); endmodule", encoding="utf-8")
        decoder = ws / "decoder.sv"
        decoder.write_text("module decoder(); endmodule", encoding="utf-8")
        tb = ws / "tb_top.v"
        tb.write_text("module tb_top(); endmodule", encoding="utf-8")

        # Files in .mind or hidden dirs must be excluded from compilation
        mind_dir = ws / ".mind" / "snapshots" / "test_session"
        mind_dir.mkdir(parents=True)
        (mind_dir / "duplicate.v").write_text("module alu(); endmodule", encoding="utf-8")

        hidden_dir = ws / ".git" / "hooks"
        hidden_dir.mkdir(parents=True)
        (hidden_dir / "hook.v").write_text("module hook(); endmodule", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        verifier = RTLVerifier(top_module="tb_top", testbench_path=Path("tb_top.v"))
        res = verifier.verify(ws, mock_sb)  # type: ignore

        assert res.passed is True
        assert len(mock_sb.executed_commands) == 2
        compile_cmd = mock_sb.executed_commands[0]
        assert compile_cmd[0] == "iverilog"
        assert "-s" in compile_cmd
        assert "tb_top" in compile_cmd
        assert str(tb.resolve()) in compile_cmd
        assert str(alu.resolve()) in compile_cmd
        assert str(decoder.resolve()) in compile_cmd
        assert not any(".mind" in arg for arg in compile_cmd)
        assert not any(".git" in arg for arg in compile_cmd)


def test_rtl_verifier_simulation_failure_pattern_detection() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        tb = ws / "tb_test.v"
        tb.write_text("module tb_test(); endmodule", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        # Even with returncode 0, assertions in output must fail verification (no soft-pass)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "Simulation started... MISMATCH detected at time 40ns. FAILED"

        verifier = RTLVerifier(top_module="tb_test", testbench_path="tb_test.v")
        res = verifier.verify(ws, mock_sb)  # type: ignore

        assert res.passed is False
        assert res.failure_reason is not None
        assert "Simulation failure detected" in res.failure_reason


def test_rtl_verifier_missing_testbench() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        verifier = RTLVerifier(top_module="tb_missing", testbench_path="absent.v")
        res = verifier.verify(ws, mock_sb)  # type: ignore
        assert res.passed is False
        assert "missing" in str(res.failure_reason).lower()


def test_software_verifier_execution() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        pytest_verifier = SoftwareVerifier(runner="pytest", test_target="tests/")
        res1 = pytest_verifier.verify(ws, mock_sb)  # type: ignore
        assert res1.passed is True
        assert mock_sb.executed_commands[-1] == ["pytest", "tests/"]

        cargo_verifier = SoftwareVerifier(runner="cargo test", test_target="")
        res2 = cargo_verifier.verify(ws, mock_sb)  # type: ignore
        assert res2.passed is True
        assert mock_sb.executed_commands[-1] == ["cargo", "test"]

        with pytest.raises(ValueError):
            SoftwareVerifier(runner="npm test")  # type: ignore


# ── Policy & Security Tests ──────────────────────────────────────────────────


def test_policy_traversal_and_directory_protection() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)

        driver = PhaseDriver(
            session_id="policy-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore
        )

        # 1. Relative path traversal
        with pytest.raises(PermissionError) as exc1:
            driver._policy_check(WriteFileAction(path="../../outside.txt", content="x"))
        assert "path traversal blocked" in str(exc1.value)

        # 2. Absolute path outside workspace
        with pytest.raises(PermissionError) as exc2:
            driver._policy_check(WriteFileAction(path="/etc/passwd", content="x"))
        assert "path traversal blocked" in str(exc2.value)

        # 3. Attempt to mutate .mind directory
        with pytest.raises(PermissionError) as exc3:
            driver._policy_check(WriteFileAction(path=".mind/corrupt.json", content="x"))
        assert "mutation of .mind internal storage blocked" in str(exc3.value)

        # 4. Attempt to overwrite workspace root
        with pytest.raises(PermissionError) as exc4:
            driver._policy_check(WriteFileAction(path=".", content="x"))
        assert "cannot overwrite workspace root" in str(exc4.value)

        # 5. Attempt to overwrite existing directory
        sub_dir = ws / "sub_dir"
        sub_dir.mkdir()
        with pytest.raises(IsADirectoryError) as exc5:
            driver._policy_check(WriteFileAction(path="sub_dir", content="x"))
        assert "existing directory" in str(exc5.value)

        # 6. Null byte path injection blocked
        with pytest.raises(ValueError) as exc6:
            driver._policy_check(WriteFileAction(path="bad\x00file.txt", content="x"))
        assert "null bytes" in str(exc6.value).lower()

        # 7. Symlink escape outside workspace blocked
        outside_dir = Path(tmpdir).parent / "outside_sandbox_tmp"
        outside_dir.mkdir(exist_ok=True)
        symlink_path = ws / "escape_symlink"
        try:
            symlink_path.symlink_to(outside_dir)
            with pytest.raises(PermissionError) as exc7:
                driver._policy_check(WriteFileAction(path="escape_symlink/leak.txt", content="x"))
            assert "path traversal blocked" in str(exc7.value)
        finally:
            if symlink_path.is_symlink():
                symlink_path.unlink()
            if outside_dir.exists():
                outside_dir.rmdir()


# ── Snapshot & Rollback Lifecycle Tests ──────────────────────────────────────


def test_snapshot_and_rollback_recovery() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        original_file = ws / "intact.txt"
        original_file.write_text("clean state", encoding="utf-8")

        verifier = MockVerifier(should_pass=False)
        mock_sb = MockSandbox(ws)
        driver = PhaseDriver(
            session_id="rollback-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=1,
            sandbox=mock_sb,  # type: ignore
        )

        # 1. Snapshot taken
        driver._create_snapshot()
        assert (driver.snapshot_dir / "intact.txt").exists()

        # 2. Mutate workspace
        driver._execute_action(WriteFileAction(path="bad.py", content="invalid code"))
        assert (ws / "bad.py").exists()

        # 3. Restore snapshot
        driver._restore_snapshot()
        assert not (ws / "bad.py").exists()
        assert original_file.exists()
        assert original_file.read_text(encoding="utf-8") == "clean state"


def test_phase_driver_full_run_success_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)

        driver = PhaseDriver(
            session_id="run-success",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore
        )

        def mock_query(messages: list[dict[str, str]]) -> str:
            # Model output wrapped in markdown code fence
            return "```json\n{\"action\": \"write_file\", \"path\": \"valid.py\", \"content\": \"a = 1\\n\"}\n```"

        monkeypatch.setattr(driver, "_query_ollama", mock_query)

        result = driver.run("Build verified module")
        assert result is True
        assert (ws / "valid.py").exists()
        assert not driver.snapshot_dir.exists()

        # Check transcript.jsonl validity
        assert driver.transcript_file.exists()
        with open(driver.transcript_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) >= 11
        current_prev = "0" * 64
        for item in lines:
            assert item["prev_hash"] == current_prev
            record = TraceRecord.model_validate(item)
            assert record.is_hash_valid() is True
            current_prev = item["current_hash"]


def test_phase_driver_full_run_rollback_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        original_doc = ws / "original.txt"
        original_doc.write_text("clean base", encoding="utf-8")

        verifier = MockVerifier(should_pass=False)
        mock_sb = MockSandbox(ws)

        driver = PhaseDriver(
            session_id="run-rollback",
            workspace=ws,
            verifier=verifier,
            max_repairs=2,
            sandbox=mock_sb,  # type: ignore
        )

        def mock_query(messages: list[dict[str, str]]) -> str:
            return json.dumps({
                "action": "write_file",
                "path": "failing_impl.py",
                "content": "raise RuntimeError()\n",
            })

        monkeypatch.setattr(driver, "_query_ollama", mock_query)

        result = driver.run("Attempt buggy design")
        assert result is False
        # Failed changes must be rolled back completely
        assert not (ws / "failing_impl.py").exists()
        assert original_doc.exists()
        assert original_doc.read_text(encoding="utf-8") == "clean base"


def test_sanitize_json_output() -> None:
    raw_fenced = "```json\n{\"action\": \"run_command\", \"command\": [\"pytest\"]}\n```"
    cleaned = _sanitize_json_output(raw_fenced)
    assert cleaned == "{\"action\": \"run_command\", \"command\": [\"pytest\"]}"


def test_skill_registry_and_router() -> None:
    from mind3.skills import SkillRegistry, SkillRouter

    skill_dir = Path(__file__).resolve().parent.parent / "skill"
    registry = SkillRegistry(skill_dir)
    assert len(registry) >= 2
    assert registry.get("semiconductor-vlsi") is not None
    assert registry.get("industry-report-analyst") is not None

    router = SkillRouter(registry)
    # Test RTL routing
    match_rtl = router.route("Design a synthesizable FIFO controller in Verilog without latches")
    assert match_rtl.skill is not None
    assert match_rtl.skill.metadata.name == "semiconductor-vlsi"
    assert match_rtl.suggested_domain == "RTL"
    assert any("rtl-design.md" in r.name for r in match_rtl.relevant_references)

    # Test STA routing
    match_sta = router.route("Explain setup and hold slack violations in static timing analysis")
    assert match_sta.skill is not None
    assert match_sta.suggested_domain == "PHYSICAL_DESIGN"
    assert any("physical-design.md" in r.name for r in match_sta.relevant_references)

    # Test Report routing
    match_rep = router.route("Generate an industry report on TSMC vs Intel 18A node roadmap timeline")
    assert match_rep.skill is not None
    assert match_rep.skill.metadata.name == "industry-report-analyst"
    assert match_rep.suggested_domain == "INDUSTRY_REPORT"


def test_run_skill_script_action_validation() -> None:
    action = RunSkillScriptAction(
        skill_name="industry-report-analyst",
        script_name="scripts/generate_timeline_chart.py",
        args=["--spec", "spec.json", "--out", "chart.png"],
    )
    assert action.action == "run_skill_script"
    assert action.skill_name == "industry-report-analyst"

    parsed = agent_action_adapter.validate_python({
        "action": "run_skill_script",
        "skill_name": "industry-report-analyst",
        "script_name": "scripts/generate_timeline_chart.py",
        "args": ["--help"],
    })
    assert isinstance(parsed, RunSkillScriptAction)


def test_driver_heart_with_skill_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    from mind3.core.verifier import IndustryReportVerifier

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        skill_dir = Path(__file__).resolve().parent.parent / "skill"

        report_file = ws / "report.md"
        report_file.write_text(
            "# Semiconductor Node Transition Report\n\n"
            "## 1. Executive Summary\nAnalysis of N3E and 18A.\n\n"
            "## 2. Competitive Landscape\n"
            "| Foundry | Node | Density |\n| --- | --- | --- |\n| TSMC | N3E | High |\n\n"
            "## 3. Sources & References\n1. reuters.com\n",
            encoding="utf-8",
        )

        verifier = IndustryReportVerifier(report_path="report.md", min_sections=2)
        mock_sb = MockSandbox(ws)
        driver = PhaseDriver(
            session_id="skill-heart-test",
            workspace=ws,
            verifier=verifier,
            skills_dir=skill_dir,
            sandbox=mock_sb,  # type: ignore
        )

        def mock_query(messages: list[dict[str, str]]) -> str:
            # Check that specialized skill instructions were injected into system prompt
            system_msg = messages[0]["content"]
            assert "ACTIVE SPECIALIZED DOMAIN SKILL: semiconductor-vlsi" in system_msg
            assert "MANDATORY DOMAIN REFERENCE SPECIFICATIONS" in system_msg
            return json.dumps({
                "action": "write_file",
                "path": "notes.txt",
                "content": "Verified against skill guidelines.",
            })

        monkeypatch.setattr(driver, "_query_ollama", mock_query)

        success = driver.run("Synthesize a clean Verilog FIFO and explain setup timing constraints")
        assert success is True
        assert (ws / "notes.txt").exists()

        # Verify route trace recorded the skill match
        route_records = [r for r in driver.transcript if r.phase == PhaseEnum.ROUTE]
        assert len(route_records) == 1
        route_payload = route_records[0].event.payload
        assert route_payload["active_skill"] == "semiconductor-vlsi"
        assert route_payload["domain"] in ("RTL", "PHYSICAL_DESIGN")


def test_zero_stubs_integrity() -> None:
    """Ensure no pass, ellipsis ..., or TODO comments exist across src/mind3."""
    base_path = Path(__file__).resolve().parent.parent / "src" / "mind3"
    py_files = list(base_path.rglob("*.py"))
    assert len(py_files) >= 4

    stub_pattern = re.compile(r"\bpass\b|\.{3}|#\s*TODO")
    for file_path in py_files:
        content = file_path.read_text(encoding="utf-8")
        matches = stub_pattern.findall(content)
        assert len(matches) == 0, f"Found stub patterns {matches} in {file_path}"


def test_interface_contract_and_code_generation() -> None:
    """Validate InterfaceContract data structures, SVA emission, and SDC constraints."""
    contract = InterfaceContract(
        module_name="fifo_sync",
        functional_spec="Synchronous FIFO queue with 8-bit width and synchronous active-low reset",
        ports=[
            PortDefinition(name="clk", direction=PortDirection.INPUT, width=1, description="Primary clock"),
            PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1, description="Active-low reset"),
            PortDefinition(name="wr_en", direction=PortDirection.INPUT, width=1, description="Write enable"),
            PortDefinition(name="rd_en", direction=PortDirection.INPUT, width=1, description="Read enable"),
            PortDefinition(name="data_in", direction=PortDirection.INPUT, width=8, description="Write data payload"),
            PortDefinition(name="data_out", direction=PortDirection.OUTPUT, width=8, description="Read data output"),
            PortDefinition(name="full", direction=PortDirection.OUTPUT, width=1, description="FIFO full flag"),
            PortDefinition(name="empty", direction=PortDirection.OUTPUT, width=1, description="FIFO empty flag"),
        ],
        sva_properties=[
            SVAProperty(
                name="no_overflow_write",
                property_expr="full && wr_en |-> ##1 full",
                description="Writing while full retains full state without corrupting boundary",
            ),
            SVAProperty(
                name="no_underflow_read",
                property_expr="empty && rd_en |-> ##1 empty",
                description="Reading while empty retains empty state",
            ),
        ],
        timing=TimingConstraint(
            clock_name="clk",
            period_ns=2.0,
        ),
    )

    # Validate SVA generation
    sva_code = "\n".join(p.to_verilog_assertion() for p in contract.sva_properties)
    assert "property p_no_overflow_write;" in sva_code
    assert "@(posedge clk)" in sva_code
    assert "assert property (p_no_overflow_write)" in sva_code
    assert "property p_no_underflow_read;" in sva_code

    # Validate header template generation
    header = contract.to_header_template()
    assert "module fifo_sync (" in header
    assert "input wire [7:0] data_in" in header
    assert "output wire full" in header

    # Validate SDC synthesis timing script
    sdc_code = contract.timing.to_sdc()
    assert "create_clock -name clk -period 2.000 [get_ports clk]" in sdc_code
    assert "set_input_delay -clock clk 1.000 [all_inputs]" in sdc_code

    # Validate JSON serialization round-trip
    dumped = contract.model_dump_json()
    reloaded = InterfaceContract.model_validate_json(dumped)
    assert reloaded.module_name == "fifo_sync"
    assert len(reloaded.ports) == 8
    assert len(reloaded.sva_properties) == 2


def test_contract_synthesizer_and_prompt_decoupling() -> None:
    """Ensure multi-agent decoupling: RTL prompt has no testbench, Harness prompt has no RTL."""
    prompt = ContractSynthesizer.build_prompt("Design a dual-clock FIFO with 16 words depth")
    assert "JSON object strictly adhering to the InterfaceContract schema" in prompt["system"]
    assert "Design a dual-clock FIFO" in prompt["user"]

    raw_json = json.dumps({
        "module_name": "counter_updown",
        "functional_spec": "4-bit synchronous up/down counter with asynchronous reset",
        "ports": [
            {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
            {"name": "rst_n", "direction": "input", "width": 1, "description": "Reset"},
            {"name": "count", "direction": "output", "width": 4, "description": "Count value"},
        ],
        "sva_properties": [
            {
                "name": "rst_val",
                "property_expr": "!rst_n |-> ##1 (count == 4'b0000)",
                "description": "Reset value",
            }
        ],
        "timing": {"clock_name": "clk", "period_ns": 5.0},
    })
    contract = InterfaceContract.model_validate_json(raw_json)
    assert contract.module_name == "counter_updown"

    # Verify RTLGenerator prompt
    rtl_prompt = RTLGenerator.build_prompt(contract)
    assert "counter_updown" in rtl_prompt["user"]
    assert "zero access to the testbench" in rtl_prompt["system"].lower()

    # Verify SBY formal harness configuration
    sby_cfg = VerificationHarnessGenerator.build_sby_config(contract, depth=25)
    assert "[options]" in sby_cfg
    assert "mode bmc" in sby_cfg
    assert "depth 25" in sby_cfg
    assert "counter_updown" in sby_cfg

    # Verify Verilator C++ testbench harness
    cpp_tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
    assert "Vcounter_updown" in cpp_tb
    assert "eval()" in cpp_tb


def test_eda_runners_local_and_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate LocalBwrapRunner and RemoteSSHRunner command generation and routing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "Yosys 0.38"

        # Local runner
        local_runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        res = local_runner.run(["yosys", "-V"])
        assert res.returncode == 0
        assert "Yosys 0.38" in res.stdout
        assert mock_sb.executed_commands[0] == ["yosys", "-V"]

        # Remote SSH runner
        remote_runner = RemoteSSHRunner(
            host="eda.corp.internal",
            user="silicon_team",
            remote_workdir="/eda/scratch/mind3",
        )
        assert remote_runner.runner_type == "remote_ssh"
        assert remote_runner.host == "eda.corp.internal"
        assert remote_runner.is_available() is True

        # Runner factory tests
        monkeypatch.delenv("EDA_REMOTE_HOST", raising=False)
        default_runner = get_eda_runner(ws, mock_sb)  # type: ignore
        assert isinstance(default_runner, LocalBwrapRunner)

        monkeypatch.setenv("EDA_REMOTE_HOST", "eda-farm.enterprise.com")
        monkeypatch.setenv("EDA_REMOTE_USER", "cad_user")
        factory_remote = get_eda_runner(ws, mock_sb)  # type: ignore
        assert isinstance(factory_remote, RemoteSSHRunner)
        assert factory_remote.host == "eda-farm.enterprise.com"
        assert factory_remote.user == "cad_user"


def test_silicon_signoff_gate1_latch_trap() -> None:
    """Ensure Gate 1 catches unintended latch inferences in combinational always blocks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        # Incomplete if branch infers a storage latch
        latch_v = ws / "latch_unit.v"
        latch_v.write_text(
            "module latch_unit(input a, input sel, output reg y);\n"
            "  always @* begin\n"
            "    if (sel)\n"
            "      y = a;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )

        mock_sb = MockSandbox(ws)
        verifier = SiliconSignoffVerifier(
            top_module="latch_unit",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=True,
        )
        result = verifier.verify(ws, mock_sb)  # type: ignore

        assert result.passed is False
        assert result.error_category == "LATCH_INFERRED"
        assert result.silicon_verified is False
        assert "latch" in result.stderr.lower() or "latch" in result.stdout.lower()

        # Clean module without latch + required verification artifacts
        clean_v = ws / "clean_unit.v"
        clean_v.write_text(
            "module clean_unit(input a, input sel, output reg y);\n"
            "  always @* begin\n"
            "    if (sel)\n"
            "      y = a;\n"
            "    else\n"
            "      y = 1'b0;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        latch_v.unlink()
        (ws / "clean_unit.sby").write_text("[options]\nmode bmc\n", encoding="utf-8")
        (ws / "tb.cpp").write_text("int main() { return 0; }", encoding="utf-8")
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.18\n"

        clean_verifier = SiliconSignoffVerifier(
            top_module="clean_unit",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=True,
        )
        clean_res = clean_verifier.verify(ws, mock_sb)  # type: ignore
        assert clean_res.passed is True
        assert clean_res.silicon_verified is True
        assert clean_res.error_category is None


def test_silicon_signoff_gate2_formal_bmc_failure() -> None:
    """Ensure Gate 2 extracts counterexample trace details when SymbiYosys BMC fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 1
        mock_sb.mock_stdout = "Assert failed in counter_updown: step 14 FAILED (counterexample trace stored in engine_0/trace.vcd)"
        mock_sb.mock_stderr = "SBY BMC returned failure"

        # Create a dummy .sby file
        (ws / "counter.sby").write_text("[options]\nmode bmc\ndepth 25\n", encoding="utf-8")
        (ws / "counter.v").write_text("module counter(); endmodule\n", encoding="utf-8")

        verifier = SiliconSignoffVerifier(
            top_module="counter",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        gate2_report = verifier._run_gate2_formal_sby(runner, [ws / "counter.v"], ws)

        assert gate2_report["passed"] is False
        assert gate2_report["error_category"] == "FORMAL_INVARIANT_BREACH"
        assert "T=14" in gate2_report["details"]


def test_silicon_signoff_gate4_timing_slack_violation() -> None:
    """Ensure Gate 4 catches negative worst negative slack (WNS) timing violations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns -0.35\ntns -1.42\n"
        mock_sb.mock_stderr = ""

        (ws / "core.v").write_text("module core(); endmodule\n", encoding="utf-8")
        verifier = SiliconSignoffVerifier(
            top_module="core",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        gate4_report = verifier._run_gate4_timing(runner, [ws / "core.v"], ws)

        assert gate4_report["passed"] is False
        assert gate4_report["error_category"] == "TIMING_SLACK_VIOLATION"
        assert "-0.35" in gate4_report["details"]


def test_silicon_signoff_all_gates_clean() -> None:
    """Verify that all 4 gates pass cleanly and yield silicon_verified=True with full receipts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        top_v = ws / "alu.v"
        top_v.write_text(
            "module alu(\n"
            "  input wire clk,\n"
            "  input wire rst_n,\n"
            "  input wire [3:0] a,\n"
            "  input wire [3:0] b,\n"
            "  output reg [3:0] sum\n"
            ");\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n)\n"
            "      sum <= 4'b0000;\n"
            "    else\n"
            "      sum <= a + b;\n"
            "  end\n"
            "endmodule\n",
            encoding="utf-8",
        )
        (ws / "alu.sby").write_text("[options]\nmode bmc\n", encoding="utf-8")
        (ws / "tb.cpp").write_text("int main() { return 0; }", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.25\n"
        verifier = SiliconSignoffVerifier(
            top_module="alu",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=True,
        )
        res = verifier.verify(ws, mock_sb)  # type: ignore

        assert res.passed is True
        assert res.silicon_verified is True
        assert res.error_category is None
        assert len(res.gate_reports) >= 4
        assert all(g["passed"] is True for g in res.gate_reports)


def test_phase_driver_silicon_signoff_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full PhaseDriver run with SiliconSignoffVerifier asserting SILICON_VERIFIED trace record."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "shifter.sby").write_text("[options]\nmode bmc\n", encoding="utf-8")
        (ws / "tb.cpp").write_text("int main() { return 0; }", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.18\n"

        verifier = SiliconSignoffVerifier(
            top_module="shifter",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=True,
        )
        driver = PhaseDriver(
            session_id="silicon-driver-signoff",
            workspace=ws,
            verifier=verifier,
            sandbox=mock_sb,  # type: ignore
        )

        clean_rtl = (
            "module shifter(input clk, input rst_n, input [3:0] d, output reg [3:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n)\n"
            "      q <= 4'b0000;\n"
            "    else\n"
            "      q <= {d[2:0], 1'b0};\n"
            "  end\n"
            "endmodule\n"
        )

        def mock_query(messages: list[dict[str, str]]) -> str:
            return json.dumps({
                "action": "write_file",
                "path": "shifter.v",
                "content": clean_rtl,
            })

        monkeypatch.setattr(driver, "_query_ollama", mock_query)

        ok = driver.run("Synthesize a clean 4-bit left shifter with synchronous pipeline")
        assert ok is True

        # Verify SILICON_VERIFIED event stamped in transcript
        finish_records = [
            r for r in driver.transcript
            if r.phase == PhaseEnum.REPAIR_OR_FINISH
        ]
        assert len(finish_records) >= 1
        finish_payload = finish_records[-1].event.payload
        assert finish_payload.get("status") == "SILICON_VERIFIED"
        assert finish_payload.get("silicon_verified") is True
        receipts = finish_payload.get("gate_reports", [])
        assert len(receipts) >= 4
        assert any("Gate 1" in str(r.get("gate")) for r in receipts)
        assert any("Gate 4" in str(r.get("gate")) for r in receipts)


def test_phase_driver_categorized_repair_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that PhaseDriver formats targeted, non-bloating repair guidance per error category."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        # Custom verifier that fails turn 0 with LATCH_INFERRED, then passes on turn 1
        class LatchFailingVerifier(BaseVerifier):
            def __init__(self) -> None:
                self.calls: int = 0

            def verify(self, workspace: Path, sandbox: BubblewrapSandbox) -> VerificationResult:
                self.calls += 1
                if self.calls == 1:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        stdout="",
                        stderr="Latch inferred in fifo.v",
                        failure_reason="Incomplete if branch infers storage latch.",
                        error_category="LATCH_INFERRED",
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    stdout="Clean",
                    stderr="",
                    silicon_verified=True,
                )

        failing_verifier = LatchFailingVerifier()
        driver = PhaseDriver(
            session_id="repair-feedback-test",
            workspace=ws,
            verifier=failing_verifier,
            sandbox=mock_sb,  # type: ignore
        )

        repair_prompts_seen: list[str] = []

        def mock_query(messages: list[dict[str, str]]) -> str:
            # Capture user messages to inspect repair feedback
            last_msg = messages[-1]["content"]
            if "GATE 1 SIGN-OFF FAILURE" in last_msg:
                repair_prompts_seen.append(last_msg)
            return json.dumps({
                "action": "write_file",
                "path": "fifo.v",
                "content": "module fifo(); endmodule\n",
            })

        monkeypatch.setattr(driver, "_query_ollama", mock_query)

        ok = driver.run("Build a verified FIFO without latches")
        assert ok is True
        assert len(repair_prompts_seen) == 1
        assert "GATE 1 SIGN-OFF FAILURE: Latch inferred in combinational logic." in repair_prompts_seen[0]
        assert "Fix Invariant: Ensure every 'if' has an explicit 'else'" in repair_prompts_seen[0]


# ── Acceptance Tests for Verification & Driver Integrity Fixes ───────────────


def test_acceptance_1_kill_mock_fallback_default_and_missing_eda_binaries() -> None:
    """Item 1: Default allow_mock_fallback=False returns EDA_BINARY_MISSING when tools are absent.

    Simulated fallback is only allowed when explicitly enabled, must prefix stdout with
    '[SIMULATED - NOT REAL TOOL OUTPUT]', mark simulated=True, and NEVER grant silicon_verified=True.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "core.v").write_text("module core(input clk, output reg q); always @(posedge clk) q <= ~q; endmodule\n", encoding="utf-8")
        (ws / "core.sby").write_text("[options]\nmode bmc\n", encoding="utf-8")
        (ws / "tb.cpp").write_text("int main() { return 0; }", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 127
        mock_sb.mock_stdout = ""
        mock_sb.mock_stderr = "yosys: command not found"

        # 1. Default must have allow_mock_fallback=False
        verifier = SiliconSignoffVerifier(
            top_module="core",
            liberty_path="sky130.lib",
        )
        assert verifier.allow_mock_fallback is False

        # Run full pipeline with default (allow_mock_fallback=False)
        result = verifier.verify(ws, mock_sb)  # type: ignore
        assert result.passed is False
        assert result.error_category == "EDA_BINARY_MISSING"
        assert result.silicon_verified is False
        assert "yosys" in str(result.failure_reason).lower()
        assert "install" in str(result.failure_reason).lower()

        # Check missing binary in Gate 2 (sby)
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        mock_sb.mock_stderr = "sby: command not found"
        gate2_res = verifier._run_gate2_formal_sby(runner, [ws / "core.v"], ws)
        assert gate2_res["passed"] is False
        assert gate2_res["error_category"] == "EDA_BINARY_MISSING"
        assert "sby" in gate2_res["details"].lower()
        assert "install" in gate2_res["details"].lower()

        # Check missing binary in Gate 3 (verilator)
        mock_sb.mock_stderr = "verilator: command not found"
        gate3_res = verifier._run_gate3_coverage(runner, [ws / "core.v"], ws)
        assert gate3_res["passed"] is False
        assert gate3_res["error_category"] == "EDA_BINARY_MISSING"
        assert "verilator" in gate3_res["details"].lower()
        assert "install" in gate3_res["details"].lower()

        # Check missing binary in Gate 4 (sta)
        mock_sb.mock_stderr = "sta: command not found"
        gate4_res = verifier._run_gate4_timing(runner, [ws / "core.v"], ws)
        assert gate4_res["passed"] is False
        assert gate4_res["error_category"] == "EDA_BINARY_MISSING"
        assert "sta" in gate4_res["details"].lower()
        assert "install" in gate4_res["details"].lower()

        # 2. When allow_mock_fallback=True is explicitly set
        sim_verifier = SiliconSignoffVerifier(
            top_module="core",
            liberty_path="sky130.lib",
            allow_mock_fallback=True,
        )
        # Gate 1 simulation
        mock_sb.mock_stderr = "yosys: command not found"
        g1_sim = sim_verifier._run_gate1_yosys(runner, [ws / "core.v"], ws)
        assert g1_sim["passed"] is True
        assert g1_sim["simulated"] is True
        assert g1_sim["stdout"].startswith("[SIMULATED - NOT REAL TOOL OUTPUT]")

        # Gate 2 simulation
        mock_sb.mock_stderr = "sby: command not found"
        g2_sim = sim_verifier._run_gate2_formal_sby(runner, [ws / "core.v"], ws)
        assert g2_sim["passed"] is True
        assert g2_sim["simulated"] is True
        assert g2_sim["stdout"].startswith("[SIMULATED - NOT REAL TOOL OUTPUT]")

        # Gate 3 simulation
        mock_sb.mock_stderr = "verilator: command not found"
        g3_sim = sim_verifier._run_gate3_coverage(runner, [ws / "core.v"], ws)
        assert g3_sim["passed"] is True
        assert g3_sim["simulated"] is True
        assert g3_sim["stdout"].startswith("[SIMULATED - NOT REAL TOOL OUTPUT]")

        # Gate 4 simulation
        mock_sb.mock_stderr = "sta: command not found"
        g4_sim = sim_verifier._run_gate4_timing(runner, [ws / "core.v"], ws)
        assert g4_sim["passed"] is True
        assert g4_sim["simulated"] is True
        assert g4_sim["stdout"].startswith("[SIMULATED - NOT REAL TOOL OUTPUT]")

        # Run full pipeline with simulation: silicon_verified must strictly be False
        full_sim_res = sim_verifier.verify(ws, mock_sb)  # type: ignore
        assert full_sim_res.passed is True
        assert full_sim_res.silicon_verified is False
        assert any(g.get("simulated") is True for g in full_sim_res.gate_reports)


def test_acceptance_2_stop_silently_noop_passing_gates_2_and_3() -> None:
    """Item 2: require_formal and require_coverage default True and fail without artifacts.

    Only caller explicit opt-out allows skipping, which marks skipped=True and keeps silicon_verified=False.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "top.v").write_text("module top(input a, output y); assign y = a; endmodule\n", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.20\n"

        # Defaults: require_formal=True, require_coverage=True
        verifier = SiliconSignoffVerifier(
            top_module="top",
            liberty_path="sky130.lib",
            allow_mock_fallback=True,
        )
        assert verifier.require_formal is True
        assert verifier.require_coverage is True

        # Run with no .sby and no .cpp
        res = verifier.verify(ws, mock_sb)  # type: ignore
        assert res.passed is False
        assert res.error_category == "MISSING_VERIFICATION_ARTIFACT"
        assert res.silicon_verified is False
        assert "sby" in str(res.failure_reason).lower() or "formal" in str(res.failure_reason).lower()

        # Add .sby harness; now Gate 3 must fail due to missing .cpp testbench
        (ws / "top.sby").write_text("[options]\nmode bmc\n", encoding="utf-8")
        res2 = verifier.verify(ws, mock_sb)  # type: ignore
        assert res2.passed is False
        assert res2.error_category == "MISSING_VERIFICATION_ARTIFACT"
        assert res2.silicon_verified is False
        assert "c++" in str(res2.failure_reason).lower() or "cpp" in str(res2.failure_reason).lower()

        # Explicit opt-out via require_formal=False and require_coverage=False
        optout_verifier = SiliconSignoffVerifier(
            top_module="top",
            liberty_path="sky130.lib",
            allow_mock_fallback=True,
            require_formal=False,
            require_coverage=False,
        )
        (ws / "top.sby").unlink()
        res3 = optout_verifier.verify(ws, mock_sb)  # type: ignore
        assert res3.passed is True
        # Must NEVER be silicon_verified if any gate was skipped
        assert res3.silicon_verified is False
        skipped_gates = [g for g in res3.gate_reports if g.get("skipped") is True]
        assert len(skipped_gates) >= 2
        assert any("Gate 2" in g.get("gate", "") for g in skipped_gates)
        assert any("Gate 3" in g.get("gate", "") for g in skipped_gates)


def test_acceptance_3_opensta_wns_parser_fixtures() -> None:
    """Item 3: Validate WNS parser across real OpenSTA outputs and failure on unparseable reports.

    Citations:
    - Real Fixture 1 & 2: Upstream OpenSTA repository: The-OpenROAD-Project/OpenSTA
      Path: search/test/search_worst_slack_sta.ok (report_wns and report_worst_slack commands)
    - Real Fixture 3: Upstream OpenSTA repository: The-OpenROAD-Project/OpenSTA
      Path: test/set_path_margin1.ok (report_checks negative slack violation)
    - Real Fixture 4: Upstream OpenSTA repository: The-OpenROAD-Project/OpenSTA
      Path: test/mcmm3.ok (report_checks multi-corner met slack path)
    Note: Neither sta nor opensta binary is installed on the local test environment (`which sta`
    returns non-zero), so golden fixture captures were pulled directly from the OpenSTA upstream repo.
    """
    # Fixture 1: Verbatim capture from search/test/search_worst_slack_sta.ok (report_wns)
    fixture_real_wns = (
        "--- report_wns ---\n"
        "wns max 0.00\n"
        "wns min 0.00\n"
        "wns max -0.25\n"
    )
    assert parse_opensta_wns(fixture_real_wns) == -0.25

    # Fixture 2: Verbatim capture from search/test/search_worst_slack_sta.ok (report_worst_slack)
    fixture_real_worst_slack = (
        "--- report_worst_slack ---\n"
        "worst slack min 1.04\n"
        "worst slack max 7.90\n"
        "worst slack max -0.15\n"
    )
    assert parse_opensta_wns(fixture_real_worst_slack) == -0.15

    # Fixture 3: Verbatim capture from test/set_path_margin1.ok (report_checks slack VIOLATED)
    fixture_real_checks_violated = (
        "   0.0000    0.0000   clock clk (rise edge)\n"
        "   0.0000    0.0000   clock network delay (ideal)\n"
        "   0.5000    0.5000   path margin\n"
        "   0.0000    0.5000   clock reconvergence pessimism\n"
        "             0.5000 ^ r3/CK (DFF_X1)\n"
        "   0.0016    0.5016   library hold time\n"
        "             0.5016   data required time\n"
        "-------------------------------------------------------------\n"
        "             0.5016   data required time\n"
        "            -0.1026   data arrival time\n"
        "-------------------------------------------------------------\n"
        "            -0.3990   slack (VIOLATED)\n"
    )
    assert parse_opensta_wns(fixture_real_checks_violated) == -0.3990

    # Fixture 4: Verbatim capture from test/mcmm3.ok (report_checks slack MET)
    fixture_real_checks_met = (
        "  Delay    Time   Description\n"
        "---------------------------------------------------------\n"
        "   0.00    0.00   clock m2_clk (rise edge)\n"
        " 123.30  123.30 ^ r3/Q (DFFHQx4_ASAP7_75t_R)\n"
        "  19.50  142.80 ^ out (out)\n"
        "         142.80   data arrival time\n"
        "---------------------------------------------------------\n"
        "         400.00   data required time\n"
        "        -142.80   data arrival time\n"
        "---------------------------------------------------------\n"
        "         257.20   slack (MET)\n"
    )
    assert parse_opensta_wns(fixture_real_checks_met) == 257.20

    # Fixture 5: Flow log format with table header
    fixture_flow_log = (
        "===========================================================================\n"
        "Worst Negative Slack\n"
        "---------------------------------------------------------------------------\n"
        "-0.125\n"
        "===========================================================================\n"
    )
    assert parse_opensta_wns(fixture_flow_log) == -0.125

    # Fixture 6: Multi-corner worst_slack (selects worst / minimum)
    fixture_multicorner = (
        "corner slow_ss_125C: worst slack -max -0.420\n"
        "corner fast_ff_m40C: worst slack -max 0.150\n"
        "corner typ_tt_025C: worst slack -max -0.050\n"
    )
    assert parse_opensta_wns(fixture_multicorner) == -0.420

    # Fixture 7: Unparseable/corrupt output
    fixture_unparseable = "Error: command failed with Tcl exception\nno slack values generated\n"
    assert parse_opensta_wns(fixture_unparseable) is None

    # Integration test with _run_gate4_timing
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "top.v").write_text("module top(); endmodule\n", encoding="utf-8")
        mock_sb = MockSandbox(ws)
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore

        verifier = SiliconSignoffVerifier(top_module="top", liberty_path="sky130.lib")

        # Clean report passes
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = fixture_real_checks_met
        rep_clean = verifier._run_gate4_timing(runner, [ws / "top.v"], ws)
        assert rep_clean["passed"] is True
        assert rep_clean["error_category"] is None

        # Violating report fails with TIMING_SLACK_VIOLATION
        mock_sb.mock_stdout = fixture_real_checks_violated
        rep_viol = verifier._run_gate4_timing(runner, [ws / "top.v"], ws)
        assert rep_viol["passed"] is False
        assert rep_viol["error_category"] == "TIMING_SLACK_VIOLATION"


def test_acceptance_4_rtl_verifier_failure_patterns_and_authoritative_exit_code() -> None:
    """Item 4: sim_proc.returncode != 0 is authoritative, tightened regexes prevent false-positives."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        tb = ws / "tb.v"
        tb.write_text("module tb(); endmodule\n", encoding="utf-8")
        verifier = RTLVerifier(top_module="tb", testbench_path="tb.v")
        mock_sb = MockSandbox(ws)

        # 1. Authoritative failure: non-zero returncode fails even without text match
        call_count = 0
        def mock_run(cmd: list[str], timeout_sec: int = 30) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=139, stdout="Simulation run completed normally", stderr="")

        mock_sb.run = mock_run  # type: ignore
        res1 = verifier.verify(ws, mock_sb)  # type: ignore
        assert res1.passed is False
        assert "non-zero status: 139" in str(res1.failure_reason)

        # 2. Benign banner text containing generic words like ERROR/FAIL does NOT false-positive
        mock_sb2 = MockSandbox(ws)
        mock_sb2.mock_returncode = 0
        mock_sb2.mock_stdout = (
            "Icarus Verilog banner:\n"
            "Elaboration finished with 0 ERRORS and 0 FAILS.\n"
            "Comparison checks: 0 MISMATCH found across all vectors.\n"
            "Simulation completed.\n"
        )
        mock_sb2.mock_stderr = ""
        res2 = verifier.verify(ws, mock_sb2)  # type: ignore
        assert res2.passed is True
        assert res2.failure_reason is None

        # 3. Genuine simulation failure signatures correctly fail with returncode 0
        failure_cases = [
            "$fatal: simulation timeout reached at time 1000ns",
            "Assertion violation: expected 8'hAA but received 8'h55",
            "ERROR: module halted due to protocol violation",
            "TEST FAILED at cycle 42",
            "FAILED: output buffer underflow",
            "MISMATCH detected at time 250ns",
            "verification mismatch on data bus",
        ]
        for fail_text in failure_cases:
            mock_sb_fail = MockSandbox(ws)
            mock_sb_fail.mock_returncode = 0
            mock_sb_fail.mock_stdout = fail_text
            res_fail = verifier.verify(ws, mock_sb_fail)  # type: ignore
            assert res_fail.passed is False, f"Expected failure for stdout: {fail_text!r}"
            assert "Simulation failure detected" in str(res_fail.failure_reason)


def test_acceptance_5_phase_driver_configurable_generator_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 5: PhaseDriver supports configurable model param, threads it to Ollama and traces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        # 1. Default model is qwen2.5-coder:7b
        default_driver = PhaseDriver(
            session_id="default-model-test",
            workspace=ws,
            verifier=MockVerifier(),
            sandbox=mock_sb,  # type: ignore
        )
        assert default_driver.model == "qwen2.5-coder:7b"

        # 2. Custom model configuration
        custom_driver = PhaseDriver(
            session_id="custom-model-test",
            workspace=ws,
            verifier=MockVerifier(),
            sandbox=mock_sb,  # type: ignore
            model="deepseek-coder:33b",
        )
        assert custom_driver.model == "deepseek-coder:33b"

        recorded_model_queries: list[str] = []

        def mock_query(messages: list[dict[str, str]]) -> str:
            recorded_model_queries.append(custom_driver.model)
            return json.dumps({
                "action": "run_command",
                "command": ["echo", "model verified"],
                "timeout_sec": 10,
            })

        monkeypatch.setattr(custom_driver, "_query_ollama", mock_query)

        ok = custom_driver.run("Execute with customized generator model")
        assert ok is True
        assert len(recorded_model_queries) >= 1
        assert all(m == "deepseek-coder:33b" for m in recorded_model_queries)

        # Verify trace stamps custom model name
        model_traces = [r for r in custom_driver.transcript if r.phase == PhaseEnum.MODEL_CALL]
        assert len(model_traces) >= 1
        assert model_traces[0].event.payload.get("model") == "deepseek-coder:33b"


def test_acceptance_6_silicon_signoff_pdk_liberty_path_configuration() -> None:
    """Item 6: liberty_path is keyword-only/optional at construction; Gate 4 fails loudly if unset."""
    # 1. Positional construction preserves backwards-compatibility for (top_module, contract)
    contract_stub = None
    v_pos = SiliconSignoffVerifier("alu", contract_stub)
    assert v_pos.top_module == "alu"
    assert v_pos.contract is None
    assert v_pos.liberty_paths == []

    # 2. Omitting liberty_path succeeds at __init__, but Gate 4 execution raises ValueError
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "alu.v").write_text("module alu(); endmodule\n", encoding="utf-8")
        runner = LocalBwrapRunner(ws, MockSandbox(ws))  # type: ignore
        with pytest.raises(ValueError, match="requires 'liberty_path' to be configured"):
            v_pos._run_gate4_timing(runner, [ws / "alu.v"], ws)

    # 3. Empty liberty_path raises ValueError
    with pytest.raises(ValueError):
        SiliconSignoffVerifier(top_module="alu", liberty_path="")

    with pytest.raises(ValueError):
        SiliconSignoffVerifier(top_module="alu", liberty_path=[])

    # 4. Single liberty path
    v_single = SiliconSignoffVerifier(top_module="alu", liberty_path="pdk/single_tt.lib")
    assert v_single.liberty_paths == ["pdk/single_tt.lib"]

    # 5. Multi-corner liberty paths
    corner_libs = ["pdk/corner_slow.lib", "pdk/corner_typ.lib", "pdk/corner_fast.lib"]
    v_multi = SiliconSignoffVerifier(top_module="alu", liberty_path=corner_libs)
    assert v_multi.liberty_paths == corner_libs

    # 6. Verify generated STA script contains all liberty paths
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "alu.v").write_text("module alu(); endmodule\n", encoding="utf-8")
        mock_sb = MockSandbox(ws)
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.12\n"
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore

        v_multi._run_gate4_timing(runner, [ws / "alu.v"], ws)
        sta_tcl = ws / "sta_check.tcl"
        assert sta_tcl.exists()
        tcl_content = sta_tcl.read_text(encoding="utf-8")
        for lib in corner_libs:
            assert f"read_liberty {lib}" in tcl_content


def test_acceptance_7_repair_budget_exhaustion_rolls_back_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 7: When repair budget is exhausted, PhaseDriver atomically rolls back workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        baseline_file = ws / "baseline_circuit.v"
        baseline_file.write_text("module golden_reference(); endmodule\n", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        always_failing_verifier = MockVerifier(should_pass=False)

        driver = PhaseDriver(
            session_id="budget-exhaustion-test",
            workspace=ws,
            verifier=always_failing_verifier,
            sandbox=mock_sb,  # type: ignore
            max_repairs=2,
        )

        repair_turn = 0

        def mock_query(messages: list[dict[str, str]]) -> str:
            nonlocal repair_turn
            repair_turn += 1
            return json.dumps({
                "action": "write_file",
                "path": f"corrupt_attempt_{repair_turn}.v",
                "content": f"// Broken implementation turn {repair_turn}\n",
            })

        monkeypatch.setattr(driver, "_query_ollama", mock_query)

        ok = driver.run("Attempt impossible repair that exhausts budget")
        assert ok is False
        assert driver.turn == 2

        # Workspace must be atomically rolled back
        assert baseline_file.exists()
        assert baseline_file.read_text(encoding="utf-8") == "module golden_reference(); endmodule\n"
        assert not (ws / "corrupt_attempt_1.v").exists()
        assert not (ws / "corrupt_attempt_2.v").exists()

        # Check audit trail records rollback
        rollback_records = [
            r for r in driver.transcript
            if r.phase == PhaseEnum.REPAIR_OR_FINISH and r.event.payload.get("status") == "ROLLED_BACK"
        ]
        assert len(rollback_records) >= 1
        assert rollback_records[-1].event.payload.get("turns_exhausted") == 2

        trace_records = [
            r for r in driver.transcript
            if r.phase == PhaseEnum.TRACE and r.event.payload.get("final_status") == "ROLLED_BACK"
        ]
        assert len(trace_records) >= 1


def test_acceptance_8_non_repairable_failure_aborts_without_wasted_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 1: When verification fails with a non-repairable category (e.g. EDA_BINARY_MISSING),
    PhaseDriver immediately rolls back and aborts without consuming further repair turns or calling model."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        baseline = ws / "baseline.v"
        baseline.write_text("module golden(); endmodule\n", encoding="utf-8")

        mock_sb = MockSandbox(ws)

        class MissingEdaVerifier(BaseVerifier):
            def verify(self, workspace: Path, sandbox: BubblewrapSandbox) -> VerificationResult:
                return VerificationResult(
                    passed=False,
                    domain=VerificationDomain.RTL,
                    exit_code=127,
                    failure_reason="yosys binary missing: yosys: command not found",
                    error_category="EDA_BINARY_MISSING",
                    silicon_verified=False,
                    gate_reports=[],
                    stdout="",
                    stderr="yosys: command not found",
                )

        driver = PhaseDriver(
            session_id="non-repairable-abort-test",
            workspace=ws,
            verifier=MissingEdaVerifier(),
            sandbox=mock_sb,  # type: ignore
            max_repairs=3,
        )

        model_calls = 0

        def mock_query(messages: list[dict[str, str]]) -> str:
            nonlocal model_calls
            model_calls += 1
            return json.dumps({
                "action": "write_file",
                "path": "mutated.v",
                "content": "module broken(); endmodule\n",
            })

        monkeypatch.setattr(driver, "_query_ollama", mock_query)

        ok = driver.run("Synthesize design with missing EDA toolchain")
        assert ok is False
        # Model must only be called ONCE (the initial turn), NOT a second or third repair turn!
        assert model_calls == 1
        # Turn must not have been incremented for repair loop
        assert driver.turn == 0

        # Workspace must be rolled back to pre-mutation snapshot
        assert baseline.exists()
        assert not (ws / "mutated.v").exists()

        # Trace must record ABORTED_NON_REPAIRABLE
        abort_records = [
            r for r in driver.transcript
            if r.phase == PhaseEnum.REPAIR_OR_FINISH
            and r.event.payload.get("status") == "ABORTED_NON_REPAIRABLE"
        ]
        assert len(abort_records) == 1
        assert abort_records[0].event.payload.get("error_category") == "EDA_BINARY_MISSING"

        trace_final = [
            r for r in driver.transcript
            if r.phase == PhaseEnum.TRACE
            and r.event.payload.get("final_status") == "ABORTED_NON_REPAIRABLE"
        ]
        assert len(trace_final) == 1
        assert trace_final[0].event.payload.get("error_category") == "EDA_BINARY_MISSING"


def test_acceptance_9_gate4_stale_tcl_liberty_regeneration() -> None:
    """Item 4: Stale sta_check.tcl in reused workspace is regenerated to reflect updated liberty_path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "top.v").write_text("module top(); endmodule\n", encoding="utf-8")
        mock_sb = MockSandbox(ws)
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.20\n"
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore

        # Run 1: with liberty_path "pdk/corner_slow.lib"
        v1 = SiliconSignoffVerifier(top_module="top", liberty_path="pdk/corner_slow.lib")
        v1._run_gate4_timing(runner, [ws / "top.v"], ws)
        sta_tcl = ws / "sta_check.tcl"
        assert sta_tcl.exists()
        content1 = sta_tcl.read_text(encoding="utf-8")
        assert "read_liberty pdk/corner_slow.lib" in content1
        assert "read_liberty pdk/corner_fast.lib" not in content1

        # Run 2: against the SAME workspace with liberty_path "pdk/corner_fast.lib"
        v2 = SiliconSignoffVerifier(top_module="top", liberty_path="pdk/corner_fast.lib")
        v2._run_gate4_timing(runner, [ws / "top.v"], ws)
        content2 = sta_tcl.read_text(encoding="utf-8")
        # Must reflect new liberty_path and NOT stale previous run
        assert "read_liberty pdk/corner_fast.lib" in content2
        assert "read_liberty pdk/corner_slow.lib" not in content2

        # Also verify custom user script (not named sta_check.tcl) is preserved untouched
        custom_tcl = ws / "user_custom_sta.tcl"
        custom_tcl.write_text("# Custom STA script\nread_liberty my_custom.lib\n", encoding="utf-8")
        v3 = SiliconSignoffVerifier(top_module="top", liberty_path="pdk/corner_new.lib")
        v3._run_gate4_timing(runner, [ws / "top.v"], ws)
        assert custom_tcl.read_text(encoding="utf-8") == "# Custom STA script\nread_liberty my_custom.lib\n"


def test_openrouter_success_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 4(a): OpenRouter 200 response parses choices[0].message.content into the same string return shape as Ollama."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)
        driver = PhaseDriver(
            session_id="openrouter_success_test",
            workspace=ws,
            verifier=verifier,
            sandbox=mock_sb,  # type: ignore
            provider="openrouter",
            api_key="sk-or-v1-testkey12345",
            model="google/gemma-4-31b-it:free",
        )

        expected_action = '{"action": "write_file", "path": "alu.v", "content": "module alu(); endmodule"}'
        openrouter_response_payload = {
            "id": "gen-test-12345",
            "model": "google/gemma-4-31b-it:free",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"```json\n{expected_action}\n```",
                    },
                    "finish_reason": "stop",
                }
            ],
        }

        posted_requests: list[dict[str, Any]] = []

        def mock_post(url: str, json: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
            posted_requests.append({"url": url, "json": json, "headers": headers})
            return httpx.Response(
                status_code=200,
                json=openrouter_response_payload,
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(driver.client, "post", mock_post)

        messages = [
            {"role": "system", "content": "You are Mind 3.0."},
            {"role": "user", "content": "Task: Create ALU"},
        ]

        # 1. Direct call to _query_openrouter
        result_direct = driver._query_openrouter(messages)
        assert result_direct == expected_action
        assert isinstance(result_direct, str)

        # Verify headers and payload
        assert len(posted_requests) == 1
        req = posted_requests[0]
        assert req["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert req["headers"]["Authorization"] == "Bearer sk-or-v1-testkey12345"
        assert req["headers"]["Content-Type"] == "application/json"
        assert req["json"]["model"] == "google/gemma-4-31b-it:free"
        assert req["json"]["messages"] == messages

        # 2. Dispatch call via _query_model returns identical string shape
        result_dispatch = driver._query_model(messages)
        assert result_dispatch == expected_action


def test_openrouter_401_authentication_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 4(b): OpenRouter 401 raises clear auth failure without silent empty content fallback."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)
        driver = PhaseDriver(
            session_id="openrouter_401_test",
            workspace=ws,
            verifier=verifier,
            sandbox=mock_sb,  # type: ignore
            provider="openrouter",
            api_key="sk-or-v1-invalid-key",
            model="google/gemma-4-31b-it:free",
        )

        error_body = '{"error": {"message": "Invalid API key provided", "code": 401}}'

        def mock_post(url: str, json: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
            return httpx.Response(
                status_code=401,
                text=error_body,
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(driver.client, "post", mock_post)

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(PermissionError) as excinfo:
            driver._query_openrouter(messages)

        err_msg = str(excinfo.value)
        assert "401" in err_msg
        assert "authentication failed" in err_msg.lower()
        assert "Invalid API key" in err_msg


def test_openrouter_429_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 4(c): OpenRouter 429 is clearly distinguishable as RATE_LIMITED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)
        driver = PhaseDriver(
            session_id="openrouter_429_test",
            workspace=ws,
            verifier=verifier,
            sandbox=mock_sb,  # type: ignore
            provider="openrouter",
            api_key="sk-or-v1-testkey",
            model="google/gemma-4-31b-it:free",
        )

        rate_limit_body = '{"error": {"message": "Free tier quota exceeded. Wait 60 seconds.", "code": 429}}'

        def mock_post(url: str, json: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
            return httpx.Response(
                status_code=429,
                text=rate_limit_body,
                request=httpx.Request("POST", url),
            )

        monkeypatch.setattr(driver.client, "post", mock_post)

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(RuntimeError) as excinfo:
            driver._query_openrouter(messages)

        err_msg = str(excinfo.value)
        # Must be identifiable as RATE_LIMITED
        assert "RATE_LIMITED" in err_msg
        assert "429" in err_msg
        assert "Free tier quota exceeded" in err_msg


def test_openrouter_missing_api_key_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Item 4(d): Missing OPENROUTER_API_KEY raises a clear config error, not a cryptic failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)

        # 1. When environment variable is unset and api_key is None -> ValueError
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(ValueError) as excinfo:
            PhaseDriver(
                session_id="openrouter_no_key",
                workspace=ws,
                verifier=verifier,
                sandbox=mock_sb,  # type: ignore
                provider="openrouter",
                api_key=None,
            )

        err_msg = str(excinfo.value)
        assert "OPENROUTER_API_KEY" in err_msg
        assert "api_key" in err_msg

        # 2. When OPENROUTER_API_KEY is provided via environment -> succeeds
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-env-key-999")
        driver_env = PhaseDriver(
            session_id="openrouter_env_key",
            workspace=ws,
            verifier=verifier,
            sandbox=mock_sb,  # type: ignore
            provider="openrouter",
        )
        assert driver_env.api_key == "sk-or-v1-env-key-999"


def test_ollama_provider_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: provider='ollama' constructs and runs exactly as before with zero behavioral diff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)

        # 1. Default constructor uses provider='ollama'
        driver_default = PhaseDriver(
            session_id="reg_default",
            workspace=ws,
            verifier=verifier,
            sandbox=mock_sb,  # type: ignore
        )
        assert driver_default.provider == "ollama"
        assert driver_default.model == "qwen2.5-coder:7b"
        assert driver_default.ollama_url == "http://127.0.0.1:11434"

        # 2. Explicit provider='ollama' routes _query_model directly to _query_ollama
        driver_explicit = PhaseDriver(
            session_id="reg_explicit",
            workspace=ws,
            verifier=verifier,
            sandbox=mock_sb,  # type: ignore
            provider="ollama",
            model="qwen2.5-coder:7b",
        )
        assert driver_explicit.provider == "ollama"

        query_ollama_invoked = False

        def mock_query_ollama(messages: list[dict[str, str]]) -> str:
            nonlocal query_ollama_invoked
            query_ollama_invoked = True
            return '{"action": "write_file", "path": "reg.v", "content": "module reg(); endmodule"}'

        monkeypatch.setattr(driver_explicit, "_query_ollama", mock_query_ollama)

        # Calling _query_model routes to _query_ollama
        resp = driver_explicit._query_model([{"role": "user", "content": "hi"}])
        assert query_ollama_invoked is True
        assert "module reg()" in resp

        # Running driver executes normal lifecycle via _query_ollama
        query_ollama_invoked = False
        success = driver_explicit.run("Implement register module")
        assert success is True
        assert query_ollama_invoked is True
        assert (ws / "reg.v").exists()


def test_openrouter_free_models_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify fetch_openrouter_free_models queries API, filters free models, respects TTL, and fails closed."""
    call_count = 0
    fake_catalog = {
        "data": [
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "qwen/qwen-2.5-coder-32b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "open-source/custom-zero-cost", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "anthropic/claude-3.5-sonnet", "pricing": {"prompt": "0.003", "completion": "0.015"}},
            {"id": "openai/gpt-4o", "pricing": {"prompt": "0.005", "completion": "0.015"}},
        ]
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return fake_catalog

    class CountingMockClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def __enter__(self) -> "CountingMockClient":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def get(self, url: str, headers: dict[str, str]) -> MockResponse:
            nonlocal call_count
            call_count += 1
            assert "models" in url
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", CountingMockClient)

    # 1. Successful query and free-tier filtering
    OpenRouterModelRegistry._cached_models = []
    OpenRouterModelRegistry._last_fetch_time = 0.0
    free_models = fetch_openrouter_free_models(ttl_seconds=3600.0, force_refresh=True)
    assert len(free_models) == 3
    assert "meta-llama/llama-3.3-70b-instruct:free" in free_models
    assert "qwen/qwen-2.5-coder-32b-instruct:free" in free_models
    assert "open-source/custom-zero-cost" in free_models
    assert "anthropic/claude-3.5-sonnet" not in free_models
    assert "openai/gpt-4o" not in free_models
    assert call_count == 1

    # 2. TTL caching: Repeated call within TTL returns cached result without querying API
    cached_free = fetch_openrouter_free_models(ttl_seconds=3600.0)
    assert cached_free == free_models
    assert call_count == 1  # No additional network query

    # 3. Configurable TTL expiry: When TTL is expired, a new query is dispatched
    expired_free = fetch_openrouter_free_models(ttl_seconds=0.0, force_refresh=True)
    assert expired_free == free_models
    assert call_count == 2  # New network query dispatched

    # 4. Fail-closed typed exception on query failure with no valid cache
    class FailingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def __enter__(self) -> "FailingClient":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def get(self, url: str, headers: dict[str, str]) -> Any:
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "Client", FailingClient)
    OpenRouterModelRegistry._cached_models = []
    OpenRouterModelRegistry._last_fetch_time = 0.0

    with pytest.raises(OpenRouterModelRegistryError) as exc_info:
        fetch_openrouter_free_models(force_refresh=True)

    assert "Failed to query OpenRouter model registry" in str(exc_info.value)
    assert "fail-closed mode" in str(exc_info.value)


def test_openrouter_model_registry_dynamic_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify OpenRouterModelRegistry dynamic query, TTL caching, and fail-closed behavior."""
    fake_catalog = {
        "data": [
            {"id": "meta-llama/llama-3.3-70b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "qwen/qwen-2.5-coder-32b-instruct:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "anthropic/claude-3.5-sonnet", "pricing": {"prompt": "0.003", "completion": "0.015"}},
        ]
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return fake_catalog

    class MockClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> "MockClient":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def get(self, url: str, headers: dict[str, str]) -> MockResponse:
            assert "models" in url
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", MockClient)

    # Force refresh and verify dynamic resolution
    free_models = OpenRouterModelRegistry.get_free_models(force_refresh=True)
    assert len(free_models) == 2
    assert "meta-llama/llama-3.3-70b-instruct:free" in free_models
    assert "qwen/qwen-2.5-coder-32b-instruct:free" in free_models
    assert "anthropic/claude-3.5-sonnet" not in free_models


def test_parse_model_code_response_robustness() -> None:
    """Verify _parse_model_code_response uses schema validation rather than string sniffing."""
    # Case 1: Structured WriteFileAction JSON
    json_action = '{"action": "write_file", "path": "alu.sv", "content": "module alu(input clk); endmodule"}'
    assert _parse_model_code_response(json_action) == "module alu(input clk); endmodule"

    # Case 2: Generic JSON without WriteFileAction schema tag is preserved as raw text (no key sniffing)
    json_dict = '{"content": "module fifo(); endmodule"}'
    assert _parse_model_code_response(json_dict) == json_dict

    # Case 3: Markdown code fences
    fenced_code = "```systemverilog\nmodule counter(input clk);\nendmodule\n```"
    assert _parse_model_code_response(fenced_code) == "module counter(input clk);\nendmodule"

    # Case 4: Raw Verilog that contains the word 'content' and starts with a brace in a comment
    tricky_verilog = "/* { brace at start with content in comment */\nmodule tricky();\nendmodule"
    parsed = _parse_model_code_response(tricky_verilog)
    assert "module tricky();" in parsed
    assert "brace at start" in parsed
    assert parsed == tricky_verilog


# ── Production Silicon & Multi-Agent Tests (Mind 3.0 10/10 Suite) ────────────


def test_write_batch_files_action_validation_and_driver_execution() -> None:
    """Validate WriteBatchFilesAction schema discrimination, policy traversal checks, and execution."""
    payload = {
        "action": "write_batch_files",
        "files": [
            {"action": "write_file", "path": "rtl/top.sv", "content": "module top(); endmodule"},
            {"action": "write_file", "path": "sdc/top.sdc", "content": "create_clock -period 10.0 [get_ports clk]"},
        ],
    }
    action = agent_action_adapter.validate_python(payload)
    assert isinstance(action, WriteBatchFilesAction)
    assert len(action.files) == 2
    assert action.files[0].path == "rtl/top.sv"

    # Disallow empty batch
    with pytest.raises(ValidationError):
        agent_action_adapter.validate_python({"action": "write_batch_files", "files": []})

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        driver = PhaseDriver(
            session_id="batch-test",
            workspace=ws,
            verifier=MockVerifier(),
            sandbox=mock_sb,  # type: ignore
        )

        # Policy traversal check inside batch
        bad_batch = WriteBatchFilesAction(files=[
            WriteFileAction(path="safe.v", content="// safe"),
            WriteFileAction(path="../escaped.v", content="// bad"),
        ])
        with pytest.raises(PermissionError, match="path traversal blocked"):
            driver._policy_check(bad_batch)

        # Successful execution
        valid_batch = WriteBatchFilesAction(files=[
            WriteFileAction(path="mod_a.sv", content="module mod_a(); endmodule"),
            WriteFileAction(path="mod_b.sv", content="module mod_b(); endmodule"),
        ])
        driver._policy_check(valid_batch)
        exec_res = driver._execute_action(valid_batch)

        assert exec_res["operation"] == "write_batch_files"
        assert exec_res["count"] == 2
        assert (ws / "mod_a.sv").exists()
        assert (ws / "mod_b.sv").exists()


def test_sva_bind_module_generation() -> None:
    """Validate SystemVerilog bind module generation for formal BMC verification."""
    contract = InterfaceContract(
        module_name="arbiter_rr",
        functional_spec="Round-robin arbiter with 2 requestors",
        ports=[
            PortDefinition(name="clk", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="rst_n", direction=PortDirection.INPUT, width=1),
            PortDefinition(name="req", direction=PortDirection.INPUT, width=2),
            PortDefinition(name="gnt", direction=PortDirection.OUTPUT, width=2),
        ],
        sva_properties=[
            SVAProperty(
                name="onehot_grant",
                property_expr="$onehot0(gnt)",
                description="Grant must be one-hot or zero",
            ),
        ],
    )

    bind_code = VerificationHarnessGenerator.build_sva_bind_module(contract)
    assert "module arbiter_rr_sva (" in bind_code
    assert "input wire clk" in bind_code
    assert "input wire [1:0] req" in bind_code
    assert "output wire [1:0] gnt" in bind_code
    assert "property p_onehot_grant;" in bind_code
    assert "bind arbiter_rr arbiter_rr_sva sva_inst (.*);" in bind_code

    # SBY config must include the bind file
    sby_cfg = VerificationHarnessGenerator.build_sby_config(contract, depth=25, include_sva_file=True)
    assert "arbiter_rr_sva.sv" in sby_cfg
    assert "read -formal arbiter_rr_sva.sv" in sby_cfg


def test_gate1_technology_synthesis_netlist_generation() -> None:
    """Ensure Gate 1 performs technology mapping to netlist when liberty_paths is configured."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "counter.v").write_text(
            "module counter(input clk, input rst_n, output reg [3:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else q <= q + 1;\n"
            "endmodule\n",
            encoding="utf-8",
        )

        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "Yosys 0.38: ABC results: mapping successful. Clean."

        verifier = SiliconSignoffVerifier(
            top_module="counter",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        report = verifier._run_gate1_yosys(runner, [ws / "counter.v"], ws)

        assert report["passed"] is True
        assert report["netlist_path"] == "counter_netlist.v"

        # Verify yosys was invoked with abc -liberty technology mapping commands
        executed_cmd = " ".join(mock_sb.executed_commands[0])
        assert "abc -liberty" in executed_cmd
        assert "dfflibmap -liberty" in executed_cmd
        assert "counter_netlist.v" in executed_cmd


def test_gate2_sva_bind_auto_generation_and_property_parsing() -> None:
    """Ensure Gate 2 auto-generates SVA bind file from contract and reports failing property label."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "fifo.v").write_text("module fifo(); endmodule\n", encoding="utf-8")

        contract = InterfaceContract(
            module_name="fifo",
            functional_spec="Synchronous FIFO queue",
            ports=[
                PortDefinition(name="clk", direction=PortDirection.INPUT),
                PortDefinition(name="rst_n", direction=PortDirection.INPUT),
            ],
            sva_properties=[
                SVAProperty(name="overflow_check", property_expr="1'b1"),
            ],
        )

        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 1
        mock_sb.mock_stdout = "Assert failed in fifo: p_overflow_check: step 7 FAILED"

        verifier = SiliconSignoffVerifier(
            top_module="fifo",
            contract=contract,
            liberty_path="sky130.lib",
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        report = verifier._run_gate2_formal_sby(runner, [ws / "fifo.v"], ws)

        assert report["passed"] is False
        assert report["error_category"] == "FORMAL_INVARIANT_BREACH"
        assert report["step"] == "7"
        # Auto-generated bind file and sby file must have been written to workspace
        assert (ws / "fifo_sva.sv").exists()
        assert (ws / "fifo.sby").exists()


def test_gate3_verilator_executable_simulation_and_coverage_thresholds() -> None:
    """Ensure Gate 3 compiles and executes binary, detecting branch/toggle coverage deficits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "mac.v").write_text("module mac(); endmodule\n", encoding="utf-8")
        (ws / "mac_tb.cpp").write_text("int main() { return 0; }", encoding="utf-8")

        # Case 1: Coverage deficit detected in simulation output
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "Simulation finished. Coverage: branch=82.4% toggle=71.0%"

        verifier = SiliconSignoffVerifier(
            top_module="mac",
            liberty_path="sky130.lib",
            min_branch_coverage=95.0,
            min_toggle_coverage=90.0,
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        report = verifier._run_gate3_coverage(runner, [ws / "mac.v"], ws)

        assert report["passed"] is False
        assert report["error_category"] == "COVERAGE_DEFICIT"
        assert "82.4%" in report["details"]
        assert report["metrics"]["branch"] == 82.4
        assert report["metrics"]["toggle"] == 71.0

        # Case 2: Simulation runtime failure (exit code != 0)
        obj_dir = ws / "obj_dir"
        obj_dir.mkdir(parents=True, exist_ok=True)
        sim_bin = obj_dir / "Vmac"
        sim_bin.write_text("#!/bin/sh\nexit 1\n")
        sim_bin.chmod(0o755)

        mock_sb_fail = MockSandbox(ws)
        mock_sb_fail.mock_returncode = 1
        mock_sb_fail.mock_stderr = "$fatal: assertion mismatch at cycle 140"
        report_fail = verifier._run_gate3_coverage(runner, [ws / "mac.v"], ws)
        assert report_fail["passed"] is False


def test_gate4_timing_reads_synthesized_gate_netlist() -> None:
    """Ensure Gate 4 targets the technology-synthesized netlist and populates timing metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "alu.v").write_text("module alu(); endmodule\n", encoding="utf-8")
        # Technology netlist produced by Gate 1
        (ws / "alu_netlist.v").write_text("module alu(clk, y); input clk; output y; endmodule\n", encoding="utf-8")
        (ws / "alu.sdc").write_text("create_clock -period 5.0 [get_ports clk]\n", encoding="utf-8")

        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns max 0.42\nworst slack max 0.42\n"

        verifier = SiliconSignoffVerifier(
            top_module="alu",
            liberty_path="sky130.lib",
            allow_mock_fallback=False,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        report = verifier._run_gate4_timing(runner, [ws / "alu.v"], ws)

        assert report["passed"] is True
        assert report["metrics"]["wns"] == 0.42
        assert "Timing closure confirmed" in report["details"]

        # Ensure generated sta_check.tcl loaded the netlist, NOT the unmapped RTL
        sta_tcl = (ws / "sta_check.tcl").read_text(encoding="utf-8")
        assert "read_verilog alu_netlist.v" in sta_tcl


def test_remote_ssh_runner_workspace_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate RemoteSSHRunner bidirectional synchronization methods."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "design.sv").write_text("module design(); endmodule", encoding="utf-8")

        runner = RemoteSSHRunner(
            host="cluster.silicon.corp",
            user="cad_lead",
            workspace=ws,
            remote_workdir="/scratch/vlsi_job_001",
        )

        # Mock successful subprocess execution for ssh/tar streaming
        class MockPopen:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.returncode = 0
                self.stdout = None

            def communicate(self, timeout: int | None = None) -> tuple[bytes, bytes]:
                return b"", b""

            def wait(self, timeout: int | None = None) -> int:
                return 0

        monkeypatch.setattr(subprocess, "Popen", MockPopen)
        assert runner.sync_to_remote(ws) is True
        assert runner.sync_from_remote(ws) is True


def test_run_silicon_pipeline_full_multi_agent_orchestration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full PhaseDriver.run_silicon_pipeline multi-agent orchestration lifecycle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.25\n"

        driver = PhaseDriver(
            session_id="multi-agent-silicon-test",
            workspace=ws,
            verifier=MockVerifier(should_pass=True),
            sandbox=mock_sb,  # type: ignore
        )

        architect_json = json.dumps({
            "module_name": "counter_4bit",
            "functional_spec": "4-bit synchronous counter with enable",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Reset"},
                {"name": "en", "direction": "input", "width": 1, "description": "Enable"},
                {"name": "count", "direction": "output", "width": 4, "description": "Count"},
            ],
            "sva_properties": [
                {"name": "rst_zero", "property_expr": "!rst_n |-> ##1 (count == 4'b0000)"},
            ],
            "timing": {"clock_name": "clk", "period_ns": 4.0},
        })

        rtl_code = (
            "module counter_4bit(input clk, input rst_n, input en, output reg [3:0] count);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) count <= 4'b0000;\n"
            "    else if (en) count <= count + 1'b1;\n"
            "  end\n"
            "endmodule\n"
        )

        query_count = 0

        def mock_agent_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                # Architect call: returns InterfaceContract
                return architect_json
            else:
                # RTL Generator call: returns RTL code
                return rtl_code

        monkeypatch.setattr(driver, "_query_ollama", mock_agent_queries)

        success = driver.run_silicon_pipeline(
            task_prompt="Design a 4-bit synchronous counter with enable and asynchronous active-low reset",
            liberty_path="sky130.lib",
        )

        assert success is True
        # Verify that all multi-agent decoupled artifacts were generated and staged
        assert (ws / "counter_4bit.sv").exists()
        assert (ws / "counter_4bit_sva.sv").exists()
        assert (ws / "counter_4bit.sby").exists()
        assert (ws / "counter_4bit_tb.cpp").exists()
        assert (ws / "counter_4bit.sdc").exists()

        # Verify trace transcript recorded the multi-agent roles
        roles_recorded = [
            r.event.payload.get("role") for r in driver.transcript if "role" in r.event.payload
        ]
        assert "Lead Silicon Architect" in roles_recorded
        assert "Verification Lead" in roles_recorded
        assert "Principal RTL Design Engineer" in roles_recorded


def test_silicon_pipeline_rtl_extraction_wrapped_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_silicon_pipeline extracts .content from wrapped WriteFileAction JSON response."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.25\n"

        driver = PhaseDriver(
            session_id="wrapped-json-test",
            workspace=ws,
            verifier=MockVerifier(should_pass=True),
            sandbox=mock_sb,  # type: ignore
        )

        architect_json = json.dumps({
            "module_name": "alu_unit",
            "functional_spec": "Simple ALU",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Reset"},
                {"name": "out", "direction": "output", "width": 8, "description": "Result"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })

        inner_rtl = "module alu_unit(input clk, input rst_n, output [7:0] out);\nassign out = 8'h42;\nendmodule\n"
        wrapped_json_response = json.dumps({
            "action": "write_file",
            "path": "alu_unit.sv",
            "content": inner_rtl,
        })

        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return architect_json
            return wrapped_json_response

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)

        success = driver.run_silicon_pipeline("Synthesize alu_unit", liberty_path="sky130.lib")
        assert success is True
        written_content = (ws / "alu_unit.sv").read_text(encoding="utf-8")
        assert written_content == inner_rtl
        assert "action" not in written_content
        assert "write_file" not in written_content


def test_silicon_pipeline_rtl_extraction_raw_rtl_with_content_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_silicon_pipeline preserves raw RTL with literal 'content' substring in comment without misfiring."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.25\n"

        driver = PhaseDriver(
            session_id="content-comment-test",
            workspace=ws,
            verifier=MockVerifier(should_pass=True),
            sandbox=mock_sb,  # type: ignore
        )

        architect_json = json.dumps({
            "module_name": "comment_alu",
            "functional_spec": "ALU with comment",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Reset"},
                {"name": "out", "direction": "output", "width": 8, "description": "Result"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })

        raw_rtl_with_content_comment = (
            "/* { Header content block: module contains 'content' in comment and starts with brace } */\n"
            "module comment_alu(input clk, input rst_n, output [7:0] out);\n"
            "  // Payload content definition\n"
            "  assign out = 8'hA5;\n"
            "endmodule\n"
        )

        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return architect_json
            return raw_rtl_with_content_comment

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)

        success = driver.run_silicon_pipeline("Synthesize comment_alu", liberty_path="sky130.lib")
        assert success is True
        written_content = (ws / "comment_alu.sv").read_text(encoding="utf-8")
        assert written_content == raw_rtl_with_content_comment.strip()
        assert "Header content block" in written_content
        assert "Payload content definition" in written_content


def test_silicon_pipeline_repair_loop_rtl_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test run_silicon_pipeline repair loop handles both wrapped JSON and raw RTL with 'content' comment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "OpenSTA 2.6.0\nwns 0.25\n"

        call_verifier_count = 0

        class RepairSiliconVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="repaired_reg", allow_mock_fallback=True)

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                nonlocal call_verifier_count
                call_verifier_count += 1
                if call_verifier_count == 1:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="LATCH INFERRED",
                        error_category="LATCH_INFERRED",
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    silicon_verified=True,
                )

        driver = PhaseDriver(
            session_id="repair-json-test",
            workspace=ws,
            verifier=RepairSiliconVerifier(),
            max_repairs=2,
            sandbox=mock_sb,  # type: ignore
        )

        architect_json = json.dumps({
            "module_name": "repaired_reg",
            "functional_spec": "Repairable register",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Reset"},
                {"name": "d", "direction": "input", "width": 8, "description": "Data"},
                {"name": "q", "direction": "output", "width": 8, "description": "Output"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 4.0},
        })

        initial_buggy_rtl = "module repaired_reg();\nendmodule"
        repaired_rtl = (
            "/* { content: repaired latch-free register } */\n"
            "module repaired_reg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= d;\n"
            "  end\n"
            "endmodule\n"
        )
        repaired_json_action = json.dumps({
            "action": "write_file",
            "path": "repaired_reg.sv",
            "content": repaired_rtl,
        })

        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return architect_json
            if query_count == 2:
                return initial_buggy_rtl
            return repaired_json_action

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)

        success = driver.run_silicon_pipeline("Synthesize repaired_reg", liberty_path="sky130.lib")
        assert success is True
        assert call_verifier_count == 2
        written_content = (ws / "repaired_reg.sv").read_text(encoding="utf-8")
        assert written_content == repaired_rtl
        assert "content: repaired latch-free register" in written_content
        assert "write_file" not in written_content


# ═══════════════════════════════════════════════════════════════════════════════
# NEW TESTS: parse_opensta_timing, Gate 5 PnR, Gate 6 CDC, DFT, Tapeout, LFSR
# ═══════════════════════════════════════════════════════════════════════════════



def test_parse_opensta_timing_setup_wns() -> None:
    """Verify parse_opensta_timing extracts setup WNS from standard wns report line."""
    from mind3.core.verifier import parse_opensta_timing
    output = "OpenSTA 2.6.0\nwns 0.25\ntns -0.00\n"
    result = parse_opensta_timing(output)
    assert result["setup_wns"] == pytest.approx(0.25, abs=1e-6)


def test_parse_opensta_timing_tns() -> None:
    """Verify parse_opensta_timing extracts setup TNS from tns report line."""
    from mind3.core.verifier import parse_opensta_timing
    output = "OpenSTA 2.6.0\nwns -0.35\ntns -1.42\n"
    result = parse_opensta_timing(output)
    assert result["setup_wns"] == pytest.approx(-0.35, abs=1e-6)
    assert result["setup_tns"] == pytest.approx(-1.42, abs=1e-6)


def test_parse_opensta_timing_hold_wns() -> None:
    """Verify parse_opensta_timing extracts hold WNS from wns -min report line."""
    from mind3.core.verifier import parse_opensta_timing
    output = "OpenSTA 2.6.0\nwns 0.18\nwns -min -0.05\n"
    result = parse_opensta_timing(output)
    assert result["setup_wns"] == pytest.approx(0.18, abs=1e-6)
    assert result["hold_wns"] == pytest.approx(-0.05, abs=1e-6)


def test_parse_opensta_timing_hold_keyword() -> None:
    """Verify parse_opensta_timing extracts hold WNS from 'hold slack' keyword."""
    from mind3.core.verifier import parse_opensta_timing
    output = "wns 0.20\nhold slack: -0.12\n"
    result = parse_opensta_timing(output)
    assert result["hold_wns"] == pytest.approx(-0.12, abs=1e-6)


def test_parse_opensta_timing_returns_none_when_absent() -> None:
    """Verify parse_opensta_timing returns None for absent fields."""
    from mind3.core.verifier import parse_opensta_timing
    result = parse_opensta_timing("OpenSTA 2.6.0 initialized\n")
    assert result["setup_wns"] is None
    assert result["setup_tns"] is None
    assert result["hold_wns"] is None


def test_gate5_pnr_skipped_by_default() -> None:
    """Gate 5 must skip cleanly (passed=True, skipped=True) when require_pnr=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        (ws / "top.v").write_text("module top(); endmodule\n", encoding="utf-8")
        verifier = SiliconSignoffVerifier(
            top_module="top",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=False,
            require_pnr=False,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        gate5_report = verifier._run_gate5_openroad_pnr(runner, [ws / "top.v"], ws)
        assert gate5_report["passed"] is True
        assert gate5_report["skipped"] is True
        assert gate5_report["error_category"] is None


def test_gate5_openroad_binary_missing_with_require_pnr() -> None:
    """Gate 5 must return EDA_BINARY_MISSING when openroad is absent and require_pnr=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 127
        mock_sb.mock_stderr = "openroad: command not found"
        netlist = ws / "top_netlist.v"
        netlist.write_text("module top(); endmodule\n", encoding="utf-8")
        verifier = SiliconSignoffVerifier(
            top_module="top",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=False,
            require_pnr=True,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        gate5_report = verifier._run_gate5_openroad_pnr(runner, [ws / "top_netlist.v"], ws)
        assert gate5_report["passed"] is False
        assert gate5_report["error_category"] == "EDA_BINARY_MISSING"


def test_gate6_cdc_violation_detection() -> None:
    """Gate 6 must detect and report CDC WARNING lines from Yosys output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = (
            "Yosys 0.40\n"
            "CDC WARNING: Unregistered signal crossing from clk_a to clk_b: data_bus\n"
            "CDC WARNING: Async reset crosses from domain fast to slow: rst_async\n"
        )
        (ws / "dual_clk.v").write_text(
            "module dual_clk(input clk_a, clk_b, input [7:0] data_bus, input rst_async, output reg [7:0] q);\n"
            "  always @(posedge clk_b) q <= data_bus;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        verifier = SiliconSignoffVerifier(
            top_module="dual_clk",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=False,
            require_cdc=True,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        gate6_report = verifier._run_gate6_cdc_analysis(runner, [ws / "dual_clk.v"], ws)
        assert gate6_report["passed"] is False
        assert gate6_report["error_category"] == "CDC_VIOLATION"
        assert len(gate6_report["cdc_violations"]) == 2
        assert any("clk_a" in v for v in gate6_report["cdc_violations"])


def test_gate6_cdc_clean() -> None:
    """Gate 6 must pass cleanly when Yosys reports no CDC warnings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = "Yosys 0.40\nSuccessfully elaborated.\n"
        (ws / "single_clk.v").write_text(
            "module single_clk(input clk, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk) q <= d;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        verifier = SiliconSignoffVerifier(
            top_module="single_clk",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=True,
            require_cdc=True,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        gate6_report = verifier._run_gate6_cdc_analysis(runner, [ws / "single_clk.v"], ws)
        assert gate6_report["passed"] is True
        assert gate6_report["cdc_violations"] == []
        assert gate6_report["error_category"] is None


def test_dft_scan_audit_missing_scan_port() -> None:
    """DFT audit must emit advisory when design has >4 DFFs but no scan-enable port."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = (
            "Yosys 0.40\n"
            "Number of cells:\n"
            "  $dff           8\n"
        )
        src = ws / "shift_reg.v"
        src.write_text(
            "module shift_reg(input clk, rst_n, d, output reg q);\n"
            "  always @(posedge clk) q <= d;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        verifier = SiliconSignoffVerifier(
            top_module="shift_reg",
            liberty_path="sky130_fd_sc_hd__tt_025C_1v80.lib",
            allow_mock_fallback=True,
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore
        dft_report = verifier._run_dft_scan_audit(runner, [src], ws)
        assert dft_report["passed"] is True  # Advisory never blocks
        audit = dft_report["dft_audit"]
        assert audit["dff_count"] == 8
        assert audit["needs_scan"] is True
        assert audit["has_scan_port"] is False
        assert audit["advisory_count"] >= 1


def test_tapeout_readiness_verifier_full_clean() -> None:
    """TapeoutReadinessVerifier must pass when all required receipts are present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        for filename in [
            "chip.lint.rpt", "chip.cdc.rpt", "chip.ec.rpt", "chip.upf",
            "chip.dft.rpt", "chip.sta.rpt", "chip.drc.rpt", "chip.lvs.rpt", "chip.em.rpt",
        ]:
            (ws / filename).write_text("CLEAN\n", encoding="utf-8")
        verifier = TapeoutReadinessVerifier()
        mock_sb = MockSandbox(ws)
        result = verifier.verify(ws, mock_sb)  # type: ignore
        assert result.passed is True
        assert result.tapeout_ready is True
        assert all(result.tapeout_evidence.values())
        assert result.error_category is None


def test_tapeout_readiness_verifier_missing_lvs() -> None:
    """TapeoutReadinessVerifier must fail when LVS report is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        for fname in ["chip.lint.rpt", "chip.cdc.rpt", "chip.ec.rpt", "chip.upf",
                      "chip.dft.rpt", "chip.sta.rpt", "chip.drc.rpt", "chip.em.rpt"]:
            (ws / fname).write_text("CLEAN\n", encoding="utf-8")
        # No LVS report written
        verifier = TapeoutReadinessVerifier()
        mock_sb = MockSandbox(ws)
        result = verifier.verify(ws, mock_sb)  # type: ignore
        assert result.passed is False
        assert result.tapeout_ready is False
        assert result.tapeout_evidence.get("lvs") is False
        assert result.error_category == "MISSING_TAPEOUT_EVIDENCE"
        assert "lvs" in (result.failure_reason or "")


def test_tapeout_readiness_verifier_custom_required_receipts() -> None:
    """TapeoutReadinessVerifier must check only the receipts listed in required_receipts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "chip.drc.rpt").write_text("DRC CLEAN\n", encoding="utf-8")
        (ws / "chip.lvs.rpt").write_text("LVS CLEAN\n", encoding="utf-8")
        verifier = TapeoutReadinessVerifier(required_receipts=["drc", "lvs"])
        mock_sb = MockSandbox(ws)
        result = verifier.verify(ws, mock_sb)  # type: ignore
        assert result.passed is True
        assert result.tapeout_evidence["drc"] is True
        assert result.tapeout_evidence["lvs"] is True


def test_tapeout_readiness_verifier_invalid_key_raises() -> None:
    """TapeoutReadinessVerifier must raise ValueError for unknown receipt keys."""
    with pytest.raises(ValueError, match="Unknown receipt keys"):
        TapeoutReadinessVerifier(required_receipts=["drc", "invalid_key"])


def test_verilator_testbench_lfsr_stimulus() -> None:
    """Generated C++ testbench must contain LFSR pseudo-random stimulus code."""
    contract = InterfaceContract(
        module_name="alu8",
        functional_spec="8-bit ALU",
        ports=[
            PortSpec(name="clk", direction=PortDirection.INPUT, width=1),
            PortSpec(name="rst_n", direction=PortDirection.INPUT, width=1),
            PortSpec(name="a", direction=PortDirection.INPUT, width=8),
            PortSpec(name="b", direction=PortDirection.INPUT, width=8),
            PortSpec(name="result", direction=PortDirection.OUTPUT, width=8),
        ],
    )
    tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
    assert "0xACE1u" in tb, "LFSR seed must be present"
    assert "0xB4BCD35Cu" in tb, "LFSR polynomial must be present"
    assert "lfsr" in tb
    assert "uint32_t" in tb
    assert "Galois LFSR" in tb, "Comment must accurately identify Galois LFSR topology"
    assert "A fixed 32-bit Galois LFSR (mask 0xB4BCD35C) used for pseudo-random stimulus." in tb
    assert "maximal-length" not in tb, "Must not claim maximal-length without mathematical verification"
    assert "Fibonacci" not in tb, "Comment must not misidentify Galois implementation as Fibonacci"


def test_verilator_testbench_boundary_sweep() -> None:
    """Generated C++ testbench must include boundary sweep (all-zeros / all-ones) patterns."""
    contract = InterfaceContract(
        module_name="mux2",
        functional_spec="2-to-1 mux",
        ports=[
            PortSpec(name="clk", direction=PortDirection.INPUT, width=1),
            PortSpec(name="rst_n", direction=PortDirection.INPUT, width=1),
            PortSpec(name="sel", direction=PortDirection.INPUT, width=1),
            PortSpec(name="a", direction=PortDirection.INPUT, width=4),
            PortSpec(name="b", direction=PortDirection.INPUT, width=4),
            PortSpec(name="y", direction=PortDirection.OUTPUT, width=4),
        ],
    )
    tb = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
    assert "0x00000000u" in tb, "All-zeros boundary pattern must be present"
    assert "0xFFFFFFFFu" in tb, "All-ones boundary pattern must be present"
    assert "bit_pos" in tb, "Walking-1 loop must be present"
    assert "Phase 4" in tb, "Reset recovery phase must be present"


def test_timing_constraint_pvt_corners() -> None:
    """TimingConstraint must persist pvt_corners and lef_path with correct defaults."""
    tc = TimingConstraint(clock_name="sys_clk", period_ns=5.0)
    assert "tt_025c_1v80" in tc.pvt_corners
    assert "ff_n40c_1v95" in tc.pvt_corners
    assert "ss_125c_1v60" in tc.pvt_corners
    assert tc.lef_path is None

    tc_custom = TimingConstraint(
        clock_name="sys_clk",
        period_ns=5.0,
        pvt_corners=["tt_025c_1v80"],
        lef_path="pdk/sky130_tech.lef",
    )
    assert tc_custom.pvt_corners == ["tt_025c_1v80"]
    assert tc_custom.lef_path == "pdk/sky130_tech.lef"


def test_timing_sdc_contains_timing_exception_stubs() -> None:
    """to_sdc() must include false-path and multicycle-path stub comments."""
    tc = TimingConstraint(clock_name="clk", period_ns=10.0)
    sdc = tc.to_sdc()
    assert "set_false_path" in sdc
    assert "set_multicycle_path" in sdc
    assert "create_clock" in sdc


def test_sby_config_property_depth_override() -> None:
    """build_sby_config must respect per-property depth overrides."""
    contract = InterfaceContract(
        module_name="deep_pipe",
        functional_spec="Deep pipeline",
        ports=[PortSpec(name="clk", direction=PortDirection.INPUT, width=1)],
        sva_properties=[SVAProperty(name="liveness_check", property_expr="always (valid |-> ##50 done)")],
    )
    sby = VerificationHarnessGenerator.build_sby_config(
        contract, depth=25, property_depths={"liveness_check": 100}
    )
    assert "depth 100" in sby


def test_timing_constraint_target_library_removed() -> None:
    """TimingConstraint must not contain target_library; extra fields are forbidden by schema."""
    tc = TimingConstraint(clock_name="clk", period_ns=4.0)
    assert not hasattr(tc, "target_library")

    with pytest.raises(ValidationError):
        TimingConstraint(clock_name="clk", period_ns=4.0, target_library="sky130.lib")  # type: ignore

    sdc = tc.to_sdc()
    assert "read_liberty" not in sdc
    assert "target_library" not in sdc
    assert "create_clock -name clk -period 4.000 [get_ports clk]" in sdc


def test_parse_opensta_mcmm_report() -> None:
    """Validate parse_opensta_mcmm extracts per-corner slacks and global worst slack."""
    fixtures_dir = Path(__file__).parent / "fixtures" / "eda_outputs"
    log_text = (fixtures_dir / "opensta_mcmm_report.log").read_text(encoding="utf-8")
    mcmm = parse_opensta_mcmm(log_text)

    assert "tt_025c_1v80" in mcmm["corners"]
    assert "ff_n40c_1v95" in mcmm["corners"]
    assert "ss_125c_1v60" in mcmm["corners"]

    assert mcmm["corners"]["tt_025c_1v80"]["setup_wns"] == 0.180
    assert mcmm["corners"]["ff_n40c_1v95"]["setup_wns"] == 0.320
    assert mcmm["corners"]["ss_125c_1v60"]["setup_wns"] == 0.025

    assert mcmm["corners"]["tt_025c_1v80"]["hold_wns"] == 0.045
    assert mcmm["corners"]["ff_n40c_1v95"]["hold_wns"] == 0.012
    assert mcmm["corners"]["ss_125c_1v60"]["hold_wns"] == 0.060

    assert mcmm["setup_wns"] == 0.025
    assert mcmm["hold_wns"] == 0.012
    assert mcmm["worst_corner"] == "ss_125c_1v60"


def test_gate4_multi_corner_slack_violation_attribution() -> None:
    """Gate 4 multi-corner STA must attribute setup violation to the specific worst corner."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "top.v").write_text("module top(); endmodule\n", encoding="utf-8")
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 0
        mock_sb.mock_stdout = (
            "OpenSTA 2.6.0\n"
            "Corner: fast_corner\n"
            "  setup wns: 0.150 ns\n"
            "Corner: slow_corner\n"
            "  setup wns: -0.220 ns\n"
            "Worst setup WNS across all corners: -0.220 ns (VIOLATED)\n"
        )
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore

        verifier = SiliconSignoffVerifier(
            top_module="top",
            liberty_path=["fast.lib", "slow.lib"],
            allow_mock_fallback=False,
        )
        report = verifier._run_gate4_timing(runner, [ws / "top.v"], ws)

        assert report["passed"] is False
        assert report["error_category"] == "TIMING_SLACK_VIOLATION"
        assert "slow_corner" in report["details"]
        assert report["metrics"]["worst_corner"] == "slow_corner"
        assert report["metrics"]["setup_wns"] == -0.220


def test_gate4_multi_corner_simulated_pvt_corners() -> None:
    """Gate 4 mock fallback must populate simulated metrics for all contract-declared PVT corners."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "top.v").write_text("module top(); endmodule\n", encoding="utf-8")
        mock_sb = MockSandbox(ws)
        mock_sb.mock_returncode = 127
        mock_sb.mock_stderr = "sta: command not found"
        runner = LocalBwrapRunner(ws, mock_sb)  # type: ignore

        contract = InterfaceContract(
            module_name="top",
            functional_spec="Test top",
            ports=[PortDefinition(name="clk", direction=PortDirection.INPUT, width=1)],
            timing=TimingConstraint(clock_name="clk", period_ns=5.0, pvt_corners=["c_typ", "c_slow"]),
        )
        verifier = SiliconSignoffVerifier(
            top_module="top",
            contract=contract,
            liberty_path="typ.lib",
            allow_mock_fallback=True,
        )
        report = verifier._run_gate4_timing(runner, [ws / "top.v"], ws)

        assert report["passed"] is True
        assert report["simulated"] is True
        assert "c_typ" in report["metrics"]["corners"]
        assert "c_slow" in report["metrics"]["corners"]


def test_air_gapped_forbids_cloud_provider() -> None:
    """air_gapped=True must forbid cloud LLM providers (e.g. openrouter)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        with pytest.raises(ValueError, match="Air-gapped security violation"):
            PhaseDriver(
                session_id="airgap-test",
                workspace=ws,
                verifier=verifier,
                provider="openrouter",
                api_key="sk-fake",
                air_gapped=True,
            )


def test_air_gapped_forbids_non_loopback_base_url() -> None:
    """air_gapped=True must forbid non-loopback base URLs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        with pytest.raises(ValueError, match="Air-gapped security violation"):
            PhaseDriver(
                session_id="airgap-test",
                workspace=ws,
                verifier=verifier,
                provider="ollama",
                base_url="http://192.168.1.100:11434",
                air_gapped=True,
            )


def test_air_gapped_emits_cryptographic_attestation() -> None:
    """air_gapped=True must inject air_gapped_attestation SHA-256 into trace events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        verifier = MockVerifier(should_pass=True)
        mock_sb = MockSandbox(ws)
        driver = PhaseDriver(
            session_id="airgap-attest",
            workspace=ws,
            verifier=verifier,
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            sandbox=mock_sb,  # type: ignore
            air_gapped=True,
        )
        rec = driver._emit_trace(PhaseEnum.INTAKE, {"input": "clean RTL"})
        assert "air_gapped_attestation" in rec.event.payload
        assert len(rec.event.payload["air_gapped_attestation"]) == 64


def test_scan_chain_synthesizer_port_injection() -> None:
    """ScanChainSynthesizer must inject scan_en, scan_in, and scan_out into Verilog module."""
    from mind3.core.dft import ScanChainSynthesizer

    rtl = (
        "module simple_alu (\n"
        "    input  wire clk,\n"
        "    input  wire rst_n,\n"
        "    output reg [7:0] out\n"
        ");\n"
        "    always @(posedge clk) out <= out + 1;\n"
        "endmodule\n"
    )

    stitched = ScanChainSynthesizer.insert_scan_ports(rtl)
    assert "input  wire scan_en" in stitched
    assert "input  wire scan_in" in stitched
    assert "output wire scan_out" in stitched

    # Idempotent: second pass should not double-insert
    stitched_twice = ScanChainSynthesizer.insert_scan_ports(stitched)
    assert stitched_twice.count("scan_en") == 1


def test_parse_openroad_irdrop_clean() -> None:
    """parse_openroad_irdrop must pass when maximum drop is below threshold."""
    from mind3.core.verifier import parse_openroad_irdrop

    clean_log = (
        "[INFO PDN-0001] Analyzing power grid for VDD...\n"
        "[INFO PDN-0012] Total current = 14.2 mA\n"
        "[INFO PDN-0015] Worstcase voltage = 1.748 V\n"
        "[INFO PDN-0016] Maximum IR drop = 0.052 V (2.89% of VDD)\n"
        "[INFO PDN-0017] Average IR drop = 0.019 V\n"
    )

    res = parse_openroad_irdrop(clean_log, max_drop_pct_threshold=5.0)
    assert res["passed"] is True
    assert res["max_ir_drop_v"] == 0.052
    assert res["max_ir_drop_pct"] == 2.89
    assert res["worst_voltage_v"] == 1.748
    assert len(res["errors"]) == 0


def test_parse_openroad_irdrop_violation() -> None:
    """parse_openroad_irdrop must fail when drop exceeds threshold or PDN error exists."""
    from mind3.core.verifier import parse_openroad_irdrop

    violated_log = (
        "[INFO PDN-0001] Analyzing power grid for VDD...\n"
        "[INFO PDN-0015] Worstcase voltage = 1.662 V\n"
        "[INFO PDN-0016] Maximum IR drop = 0.138 V (7.67% of VDD)\n"
        "[ERROR PDN-0022] Maximum IR drop 0.138 V exceeds signoff limit 5.00%\n"
    )

    res = parse_openroad_irdrop(violated_log, max_drop_pct_threshold=5.0)
    assert res["passed"] is False
    assert res["max_ir_drop_pct"] == 7.67
    assert len(res["errors"]) >= 1





