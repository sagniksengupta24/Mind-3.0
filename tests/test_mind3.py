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

import pytest
from pydantic import ValidationError

from mind3.core.driver import PhaseDriver, _sanitize_json_output
from mind3.core.types import (
    AgentAction,
    PhaseEnum,
    RunCommandAction,
    RunSkillScriptAction,
    TelemetryEvent,
    TraceRecord,
    VerificationDomain,
    VerificationResult,
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
from mind3.core.verifier import BaseVerifier, RTLVerifier, SiliconSignoffVerifier, SoftwareVerifier
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
        RunCommandAction(command=["ls"], timeout_sec=0)

    with pytest.raises(ValidationError):
        RunCommandAction(command=["ls"], timeout_sec=121)


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
        verifier = SiliconSignoffVerifier(top_module="latch_unit", allow_mock_fallback=True)
        result = verifier.verify(ws, mock_sb)  # type: ignore

        assert result.passed is False
        assert result.error_category == "LATCH_INFERRED"
        assert result.silicon_verified is False
        assert "latch" in result.stderr.lower() or "latch" in result.stdout.lower()

        # Clean module without latch
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

        clean_verifier = SiliconSignoffVerifier(top_module="clean_unit", allow_mock_fallback=True)
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

        verifier = SiliconSignoffVerifier(top_module="counter", allow_mock_fallback=False)
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
        verifier = SiliconSignoffVerifier(top_module="core", allow_mock_fallback=False)
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

        mock_sb = MockSandbox(ws)
        verifier = SiliconSignoffVerifier(top_module="alu", allow_mock_fallback=True)
        res = verifier.verify(ws, mock_sb)  # type: ignore

        assert res.passed is True
        assert res.silicon_verified is True
        assert res.error_category is None
        assert len(res.gate_reports) == 4
        assert all(g["passed"] is True for g in res.gate_reports)


def test_phase_driver_silicon_signoff_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full PhaseDriver run with SiliconSignoffVerifier asserting SILICON_VERIFIED trace record."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        verifier = SiliconSignoffVerifier(top_module="shifter", allow_mock_fallback=True)
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
        assert len(receipts) == 4
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


