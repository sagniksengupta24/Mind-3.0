import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest


def _load_control_module() -> Any:
    """Load scripts/run_negative_controls.py without mutating sys.path."""
    script = Path(__file__).parents[1] / "scripts" / "run_negative_controls.py"
    assert script.is_file(), f"negative-control runner script missing: {script}"
    spec = importlib.util.spec_from_file_location("run_negative_controls", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_negative_control_corpus_is_complete_and_explicitly_expected() -> None:
    root = Path(__file__).parent / "negative_controls"
    manifest_file = root / "negative_controls_manifest.json"
    assert manifest_file.is_file(), "negative_controls_manifest.json must exist"

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(manifest) >= 15, f"Expected at least 15 negative controls, found {len(manifest)}"

    # Check each fixture has valid fields
    for entry in manifest:
        assert "id" in entry
        assert "source" in entry
        assert (root / entry["source"]).is_file(), f"Missing source file: {entry['source']}"
        assert entry["expected_compile"] in ("PASS", "FAIL")
        assert entry["expected_category"] in (
            "LATCH_INFERRED",
            "COMBINATIONAL_LOOP",
            "FORMAL_INVARIANT_BREACH",
            "SIMULATION_FAILURE",
            "CDC_VIOLATION",
            "TIMING_SLACK_VIOLATION",
            "SYNTHESIS_ELABORATION_ERROR",
            "COVERAGE_DEFICIT",
        )

    # Check all 15 required categories from primary prompt are represented
    ids = {e["id"] for e in manifest}
    required_ids = {
        "latch_inference",
        "combinational_loop",
        "incorrect_reset_behavior",
        "reset_deassertion_problem",
        "cdc_violation",
        "fifo_overflow",
        "fifo_underflow",
        "off_by_one_counter",
        "incorrect_handshake",
        "incorrect_fsm_transition",
        "width_truncation",
        "signed_unsigned_error",
        "timing_violation",
        "false_formal",
        "sim_behavioral_failure",
    }
    assert required_ids.issubset(ids), f"Missing required negative controls: {required_ids - ids}"

    readme = (root / "README.md").read_text(encoding="utf-8")
    for category in (
        "LATCH_INFERRED",
        "COMBINATIONAL_LOOP",
        "FORMAL_INVARIANT_BREACH",
        "SIMULATION_FAILURE",
        "COVERAGE_DEFICIT",
        "TIMING_SLACK_VIOLATION",
        "CDC_VIOLATION",
    ):
        assert category in readme


class _FakeSandbox:
    """Synthetic stand-in for BubblewrapSandbox (routing tests only)."""

    def __init__(self, workspace: Path, available: bool = True) -> None:
        if not available:
            raise RuntimeError("bwrap binary not found on PATH")
        self.workspace = Path(workspace)
        self.bwrap_binary = "/usr/bin/bwrap"


def _patch_selection(monkeypatch: pytest.MonkeyPatch, module: Any, available: bool, capable: bool) -> None:
    def fake_sandbox(workspace: Path) -> _FakeSandbox:
        return _FakeSandbox(workspace, available=available)

    monkeypatch.setattr(module, "BubblewrapSandbox", fake_sandbox)
    monkeypatch.setattr(
        module,
        "probe_bubblewrap_namespace_capability",
        lambda **kwargs: (capable, "synthetic probe verdict"),
    )


def test_control_runner_prefers_sandbox_when_namespaces_capable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic routing test: capable host -> sandboxed runner (no tool execution)."""
    module = _load_control_module()
    _patch_selection(monkeypatch, module, available=True, capable=True)
    runner, sandboxed = module.select_control_runner(tmp_path)
    assert sandboxed is True
    assert runner.sandbox is not None


def test_control_runner_falls_back_when_binary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic routing test: missing bwrap -> real unsandboxed runner, honestly labeled."""
    module = _load_control_module()
    _patch_selection(monkeypatch, module, available=False, capable=False)
    runner, sandboxed = module.select_control_runner(tmp_path)
    assert sandboxed is False
    assert runner.sandbox is None
    assert runner.allow_unsandboxed is True


def test_control_runner_falls_back_when_namespaces_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic routing test for the GitHub-hosted failure: binary present
    but namespace creation forbidden -> real unsandboxed runner, never a
    namespace error surfaced as a tool verdict."""
    module = _load_control_module()
    _patch_selection(monkeypatch, module, available=True, capable=False)
    runner, sandboxed = module.select_control_runner(tmp_path)
    assert sandboxed is False
    assert runner.sandbox is None
    assert runner.allow_unsandboxed is True


def _live_tools_missing(mode: str) -> str | None:
    """Return a skip reason when the live tools for a gate mode are absent."""
    if mode == "gate1" and shutil.which("yosys") is None:
        return "live yosys required"
    if mode == "gate3" and shutil.which("verilator") is None:
        return "live verilator required"
    if mode == "gate2" and shutil.which("sby") is None:
        return "live sby required"
    if mode == "gate4" and shutil.which("sta") is None and shutil.which("opensta") is None:
        return "live sta/opensta required"
    if mode == "gate6" and shutil.which("yosys") is None:
        return "live yosys required"
    return None


_LIVE_AFFECTED = (
    "latch_inference",
    "combinational_loop",
    "fifo_overflow",
    "fifo_underflow",
    "sim_behavioral_failure",
    "coverage_deficit",
    "timing_violation",
    "cdc_violation",
)


@pytest.mark.parametrize("case_id", list(_LIVE_AFFECTED))
def test_affected_negative_control_reaches_intended_gate_live(case_id: str) -> None:
    """Live gate proof for one previously mismatched control: with real
    tools, the fixture reaches its intended gate and classifies correctly
    with real (non-simulated) results. Honestly skips where the host lacks
    the required live toolchain (yosys cdc command, liberty+sta)."""
    from mind3.sandbox.remote_eda import LocalBwrapRunner

    module = _load_control_module()
    manifest = json.loads(
        (Path(__file__).parent / "negative_controls" / "negative_controls_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {entry["id"]: entry for entry in manifest}
    repo_lib = Path(__file__).parents[1] / "src" / "mind3" / "pdata" / "sky130" / "sky130_fd_sc_hd__tt_025C_1v80.lib"
    with tempfile.TemporaryDirectory(prefix="mind3_neg_ctrl_test_") as work_root:
        work_path = Path(work_root)
        entry = by_id[case_id]
        mode = entry["mode"]
        missing = _live_tools_missing(mode)
        if missing is not None:
            pytest.skip(f"{case_id}: {missing}")
        liberty = [str(repo_lib)] if mode == "gate4" and repo_lib.is_file() else None
        if mode == "gate4" and liberty is None:
            pytest.skip(f"{case_id}: timing liberty fixture unavailable")
        runner = LocalBwrapRunner(work_path / case_id, sandbox=None, allow_unsandboxed=True)
        result = module.run_control_case(entry, work_path, liberty, runner_override=runner)
        if entry["mode"] == "gate6" and result.get("observed_category") == "CDC_TOOLING_UNAVAILABLE":
            pytest.skip(f"{case_id}: host Yosys lacks CDC command")
        assert result["matched"] is True, (
            f"{case_id}: expected={result['expected_category']} observed={result.get('observed_category')} "
            f"details={str(result.get('details'))[:300]}"
        )
        assert result["simulated"] is False
        assert result["observed_category"] == entry["expected_category"]
        assert len(result["gate_reports"]) == 1
        # The manifest records the canonical gate title while reports use
        # the runtime gate label; compare on the stable "Gate N" prefix.
        assert result["gate_reports"][0]["gate"].split(":")[0] == entry["expected_gate"].split(":")[0]
        round_tripped = json.loads(json.dumps(result))
        assert round_tripped["observed_category"] == entry["expected_category"]
