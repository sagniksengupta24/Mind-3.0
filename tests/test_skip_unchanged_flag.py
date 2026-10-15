"""D4: skip-unchanged behind MIND3_SKIP_UNCHANGED (default OFF).

Adapted port tests T1 (names suffixed, flag turned ON) plus a golden
flag-off test proving snapshot behavior is preserved except D3 stage labels.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from test_mind3 import MockSandbox

from mind3.core.driver import PhaseDriver
from mind3.core.types import PhaseEnum, VerificationDomain, VerificationResult
from mind3.core.verifier import SiliconSignoffVerifier


def test_silicon_pipeline_skips_unchanged_repair_candidate_with_skip_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unchanged repair must be recorded and must not consume another EDA run."""
    monkeypatch.setenv("MIND3_SKIP_UNCHANGED", "1")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        class FailOnceVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="dup_reg", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                if self.calls == 1:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="Latch inferred in dup_reg",
                        error_category="LATCH_INFERRED",
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    silicon_verified=True,
                )

        verifier = FailOnceVerifier()
        driver = PhaseDriver(
            session_id="unchanged-repair-candidate-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps({
            "module_name": "dup_reg",
            "functional_spec": "An enabled register with a reset.",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"},
                {"name": "d", "direction": "input", "width": 8, "description": "Data input"},
                {"name": "q", "direction": "output", "width": 8, "description": "Registered output"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })
        initial_rtl = (
            "module dup_reg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= q;\n"
            "  end\nendmodule"
        )
        corrected_rtl = initial_rtl.replace("else q <= q;", "else q <= d;")
        query_count = 0
        prompts: list[str] = []

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return contract_json
            if query_count == 2:
                return initial_rtl
            if query_count == 3:
                # Differ only by line ending/trailing whitespace; must be treated as unchanged.
                return initial_rtl.replace("\n", "\r\n") + "   \r\n"
            prompts.append(messages[-1]["content"])
            return corrected_rtl

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize dup_reg", liberty_path="sky130.lib") is True
        assert verifier.calls == 2, "unchanged candidate must not rerun the verifier"
        assert query_count == 4, "the unchanged candidate should trigger one bounded corrective retry"
        assert driver._stage_repair_attempts["compile"] == 2
        assert any(
            record.phase == PhaseEnum.VERIFY
            and record.event.payload.get("error_category") == "REPAIR_UNCHANGED_CANDIDATE"
            for record in driver.transcript
        )
        assert prompts and "Do not return the same implementation again" in prompts[0]


def test_silicon_pipeline_preserves_formal_stage_for_repair_calls_with_skip_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Formal failures must remain labeled/formally budgeted on subsequent repair calls."""
    monkeypatch.setenv("MIND3_SKIP_UNCHANGED", "1")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        class FailFormalTwiceVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="formal_reg", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                if self.calls <= 2:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="BMC assertion failed at step 2",
                        error_category="FORMAL_INVARIANT_BREACH",
                        gate_reports=[{
                            "gate": "Gate 2: Formal Verification",
                            "failing_property": "data_updates_when_enabled",
                            "details": "Assertion failed at step 2",
                            "step": 2,
                        }],
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    silicon_verified=True,
                )

        verifier = FailFormalTwiceVerifier()
        driver = PhaseDriver(
            session_id="formal-stage-budget-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps({
            "module_name": "formal_reg",
            "functional_spec": "An enabled register must capture d when enabled.",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"},
                {"name": "en", "direction": "input", "width": 1, "description": "Enable"},
                {"name": "d", "direction": "input", "width": 8, "description": "Data input"},
                {"name": "q", "direction": "output", "width": 8, "description": "Registered output"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })
        candidates = [
            "module formal_reg(input clk, input rst_n, input en, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else if (en) q <= q;\nendmodule",
            "module formal_reg(input clk, input rst_n, input en, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else if (en) q <= d;\nendmodule",
            "module formal_reg(input clk, input rst_n, input en, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else q <= en ? d : q;\nendmodule",
        ]
        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return contract_json
            return candidates[min(query_count - 2, len(candidates) - 1)]

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize formal_reg", liberty_path="sky130.lib") is True
        repair_calls = [
            record.event.payload
            for record in driver.transcript
            if record.phase == PhaseEnum.MODEL_CALL
            and record.event.payload.get("role") == "Independent RTL Verification Repair Engineer"
        ]
        assert len(repair_calls) == 2
        assert [call.get("stage") for call in repair_calls] == ["formal", "formal"]
        assert driver._stage_repair_attempts["formal"] == 2


def test_silicon_pipeline_bounds_repeated_unchanged_candidates_with_skip_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated identical candidates exhaust the bounded budget with the right failure label."""
    monkeypatch.setenv("MIND3_SKIP_UNCHANGED", "1")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        class AlwaysFailVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="stuck_reg", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                return VerificationResult(
                    passed=False,
                    domain=VerificationDomain.RTL,
                    exit_code=1,
                    failure_reason="Latch inferred in stuck_reg",
                    error_category="LATCH_INFERRED",
                )

        verifier = AlwaysFailVerifier()
        driver = PhaseDriver(
            session_id="repeated-unchanged-repair-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps({
            "module_name": "stuck_reg",
            "functional_spec": "A resettable register.",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"},
                {"name": "d", "direction": "input", "width": 8, "description": "Data input"},
                {"name": "q", "direction": "output", "width": 8, "description": "Registered output"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })
        rtl = (
            "module stuck_reg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else q <= d;\nendmodule"
        )
        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            return contract_json if query_count == 1 else rtl

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize stuck_reg", liberty_path="sky130.lib") is False
        assert verifier.calls == 1, "identical repair candidates must not rerun the verifier"
        # Parse budget counts failures only, so successfully parsed identical
        # candidates terminate via the stage budget (3 skips), not via parse
        # exhaustion: contract synthesis + initial generation + 3 repairs.
        assert query_count == 5, "initial generation plus three stage-bounded repair responses expected"
        finish_records = [r for r in driver.transcript if r.phase == PhaseEnum.REPAIR_OR_FINISH]
        assert finish_records[-1].event.payload.get("failure_category") == "REPAIR_UNCHANGED_CANDIDATE"
        assert finish_records[-1].event.payload.get("stage_budget_exhausted") is True
        assert finish_records[-1].event.payload.get("parse_budget_exhausted") is False


def test_flag_off_reruns_verifier_for_identical_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Golden flag-off test: with MIND3_SKIP_UNCHANGED unset, an identical
    candidate must still consume an EDA turn (snapshot behavior); only the D3
    stage labels differ from the snapshot."""
    monkeypatch.delenv("MIND3_SKIP_UNCHANGED", raising=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        class FailOnceVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="dup_reg", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                if self.calls == 1:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="Latch inferred in dup_reg",
                        error_category="LATCH_INFERRED",
                    )
                if self.calls == 2:
                    # Identical candidate was rerun through the verifier (no skip).
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="Latch inferred in dup_reg",
                        error_category="LATCH_INFERRED",
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    silicon_verified=True,
                )

        verifier = FailOnceVerifier()
        driver = PhaseDriver(
            session_id="flag-off-identical-rerun-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps({
            "module_name": "dup_reg",
            "functional_spec": "An enabled register with a reset.",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"},
                {"name": "d", "direction": "input", "width": 8, "description": "Data input"},
                {"name": "q", "direction": "output", "width": 8, "description": "Registered output"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })
        initial_rtl = (
            "module dup_reg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= q;\n"
            "  end\nendmodule"
        )
        corrected_rtl = initial_rtl.replace("else q <= q;", "else q <= d;")
        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return contract_json
            if query_count == 2:
                return initial_rtl
            if query_count == 3:
                return initial_rtl.replace("\n", "\r\n") + "   \r\n"
            return corrected_rtl

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize dup_reg", liberty_path="sky130.lib") is True
        assert verifier.calls == 3, "flag OFF must rerun the verifier for the identical candidate"
        assert not any(
            record.phase == PhaseEnum.VERIFY
            and record.event.payload.get("error_category") == "REPAIR_UNCHANGED_CANDIDATE"
            for record in driver.transcript
        ), "flag OFF must never emit the skip-unchanged trace"
        assert len(driver._candidate_hashes) >= 2, "copy C1 raw+normalized records must be kept"


def test_comment_only_candidate_does_not_skip_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normalized-only match (comment-only) must NOT skip the verifier even
    with the flag ON: the narrow hash differs, so a full EDA turn is spent."""
    monkeypatch.setenv("MIND3_SKIP_UNCHANGED", "1")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        mock_sb = MockSandbox(ws)

        class FailOnceVerifier(SiliconSignoffVerifier):
            def __init__(self) -> None:
                super().__init__(top_module="dup_reg", allow_mock_fallback=True)
                self.calls = 0

            def verify(self, workspace: Path, sandbox: Any) -> VerificationResult:
                self.calls += 1
                if self.calls <= 2:
                    return VerificationResult(
                        passed=False,
                        domain=VerificationDomain.RTL,
                        exit_code=1,
                        failure_reason="Latch inferred in dup_reg",
                        error_category="LATCH_INFERRED",
                    )
                return VerificationResult(
                    passed=True,
                    domain=VerificationDomain.RTL,
                    exit_code=0,
                    silicon_verified=True,
                )

        verifier = FailOnceVerifier()
        driver = PhaseDriver(
            session_id="comment-only-no-skip-test",
            workspace=ws,
            verifier=verifier,
            max_repairs=3,
            sandbox=mock_sb,  # type: ignore[arg-type]
        )
        contract_json = json.dumps({
            "module_name": "dup_reg",
            "functional_spec": "An enabled register with a reset.",
            "ports": [
                {"name": "clk", "direction": "input", "width": 1, "description": "Clock"},
                {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"},
                {"name": "d", "direction": "input", "width": 8, "description": "Data input"},
                {"name": "q", "direction": "output", "width": 8, "description": "Registered output"},
            ],
            "sva_properties": [],
            "timing": {"clock_name": "clk", "period_ns": 5.0},
        })
        initial_rtl = (
            "module dup_reg(input clk, input rst_n, input [7:0] d, output reg [7:0] q);\n"
            "  always @(posedge clk or negedge rst_n) begin\n"
            "    if (!rst_n) q <= 8'h00;\n"
            "    else q <= q;\n"
            "  end\nendmodule"
        )
        corrected_rtl = initial_rtl.replace("else q <= q;", "else q <= d;")
        query_count = 0

        def mock_queries(messages: list[dict[str, str]]) -> str:
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return contract_json
            if query_count == 2:
                return initial_rtl
            if query_count == 3:
                # Comment-only change: normalized-identical, narrow-different.
                return initial_rtl.replace(
                    "endmodule", "  // retry: re-examine the enable path\nendmodule"
                )
            return corrected_rtl

        monkeypatch.setattr(driver, "_query_ollama", mock_queries)
        assert driver.run_silicon_pipeline("Synthesize dup_reg", liberty_path="sky130.lib") is True
        assert verifier.calls == 3, "comment-only candidate must still consume an EDA turn"
        assert not any(
            record.phase == PhaseEnum.VERIFY
            and record.event.payload.get("error_category") == "REPAIR_UNCHANGED_CANDIDATE"
            for record in driver.transcript
        ), "normalized-only match must never emit the skip-unchanged trace"
