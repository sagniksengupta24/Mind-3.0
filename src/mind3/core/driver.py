"""
PhaseDriver: 11-phase deterministic execution engine for Mind 3.0.
Integrates Bubblewrap sandboxing, Ollama LLM driver, atomic snapshot rollbacks, and canonical trace hashing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from ..sandbox.bwrap import BubblewrapSandbox
from ..skills import SkillMatch, SkillRegistry, SkillRouter
from .types import (
    AgentAction,
    PhaseEnum,
    RunCommandAction,
    RunSkillScriptAction,
    TelemetryEvent,
    TraceRecord,
    VerificationResult,
    WriteFileAction,
    agent_action_adapter,
)
from .verifier import BaseVerifier, RTLVerifier


def _sanitize_json_output(raw_text: str) -> str:
    """Strip markdown code block fences if emitted by the LLM."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


class PhaseDriver:
    """Orchestrates the 11-phase agent lifecycle with fail-closed security and verification."""

    def __init__(
        self,
        session_id: str,
        workspace: Path | str,
        verifier: BaseVerifier,
        max_repairs: int = 3,
        ollama_url: str = "http://127.0.0.1:11434",
        sandbox: BubblewrapSandbox | None = None,
        transcript_path: Path | None = None,
        skills_dir: Path | str | None = None,
    ) -> None:
        """Initialize the driver runtime.

        Args:
            session_id: Unique execution session token.
            workspace: Target project directory.
            verifier: Domain-specific verification oracle.
            max_repairs: Maximum allowable self-correction turns before rollback.
            ollama_url: Base HTTP endpoint for Ollama daemon.
            sandbox: Optional pre-configured BubblewrapSandbox instance.
            transcript_path: Optional custom destination file for transcript.jsonl.
            skills_dir: Optional path to skills directory containing .skill archives or folders.
        """
        self.session_id: str = session_id
        self.workspace: Path = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.verifier: BaseVerifier = verifier
        self.max_repairs: int = max_repairs
        self.ollama_url: str = ollama_url.rstrip("/")

        # Initialize Skills subsystem (Heart integration)
        resolved_skills_dir: Path | None = None
        if skills_dir is not None:
            resolved_skills_dir = Path(skills_dir).resolve()
        else:
            ws_skill = self.workspace / "skill"
            project_skill = Path(__file__).resolve().parent.parent.parent.parent / "skill"
            if ws_skill.exists() and ws_skill.is_dir():
                resolved_skills_dir = ws_skill
            elif project_skill.exists() and project_skill.is_dir():
                resolved_skills_dir = project_skill

        self.skill_registry: SkillRegistry = SkillRegistry(resolved_skills_dir)
        self.skill_router: SkillRouter = SkillRouter(self.skill_registry)
        self.active_skill_match: SkillMatch | None = None

        self.turn: int = 0
        self.step_index: int = 0
        self.transcript: list[TraceRecord] = []
        self.prev_hash: str = "0" * 64

        self.mind_dir: Path = self.workspace / ".mind"
        self.mind_dir.mkdir(parents=True, exist_ok=True)

        self.snapshot_dir: Path = self.mind_dir / "snapshots" / self.session_id
        self.transcript_file: Path = (
            transcript_path.resolve()
            if transcript_path is not None
            else self.mind_dir / "transcript.jsonl"
        )
        self.transcript_file.parent.mkdir(parents=True, exist_ok=True)

        self.sandbox: BubblewrapSandbox = (
            sandbox if sandbox is not None else BubblewrapSandbox(self.workspace)
        )
        self.client: httpx.Client = httpx.Client(timeout=60.0)

    def close(self) -> None:
        """Close the underlying HTTP client resources."""
        self.client.close()

    def __enter__(self) -> PhaseDriver:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ── Trace & Canonical Hashing (Invariant 4) ──────────────────────────

    def _emit_trace(self, phase: PhaseEnum, payload: dict[str, Any]) -> TraceRecord:
        """Construct, hash, and persist an immutable trace record to transcript.jsonl."""
        event = TelemetryEvent(
            session_id=self.session_id,
            phase=phase,
            turn=self.turn,
            payload=payload,
            timestamp=time.time(),
        )

        record_body: dict[str, Any] = {
            "step_index": self.step_index,
            "phase": phase.value,
            "prev_hash": self.prev_hash,
            "event": event.model_dump(mode="json"),
        }

        canonical_json = json.dumps(record_body, sort_keys=True, separators=(",", ":"))
        hasher = hashlib.sha256()
        hasher.update(self.prev_hash.encode("utf-8"))
        hasher.update(canonical_json.encode("utf-8"))
        current_hash = hasher.hexdigest()

        trace_record = TraceRecord(
            step_index=self.step_index,
            phase=phase,
            prev_hash=self.prev_hash,
            current_hash=current_hash,
            event=event,
        )

        serialized_line = trace_record.to_jsonl()
        with open(self.transcript_file, "a", encoding="utf-8") as f:
            f.write(serialized_line + "\n")

        self.transcript.append(trace_record)
        self.prev_hash = current_hash
        self.step_index += 1
        return trace_record

    # ── Snapshot Management (Invariant 3) ────────────────────────────────

    def _create_snapshot(self) -> int:
        """Recursively mirror workspace state into .mind/snapshots/<session_id>, excluding .mind."""
        if self.snapshot_dir.exists():
            shutil.rmtree(self.snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        copied_count = 0
        for item in self.workspace.iterdir():
            if item.name == ".mind":
                continue
            dest = self.snapshot_dir / item.name
            if item.is_symlink():
                dest.symlink_to(item.readlink())
            elif item.is_dir():
                shutil.copytree(item, dest, symlinks=True)
            else:
                shutil.copy2(item, dest)
            copied_count += 1
        return copied_count

    def _restore_snapshot(self) -> None:
        """Purge active workspace modifications and revert completely to pre-mutation snapshot."""
        if not self.snapshot_dir.exists():
            raise RuntimeError(
                f"Cannot restore snapshot: directory {self.snapshot_dir} does not exist."
            )

        for item in self.workspace.iterdir():
            if item.name == ".mind":
                continue
            if item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        for item in self.snapshot_dir.iterdir():
            dest = self.workspace / item.name
            if item.is_symlink():
                dest.symlink_to(item.readlink())
            elif item.is_dir():
                shutil.copytree(item, dest, symlinks=True)
            else:
                shutil.copy2(item, dest)

    def _purge_snapshot(self) -> None:
        """Purge snapshot upon successful verification."""
        if self.snapshot_dir.exists():
            shutil.rmtree(self.snapshot_dir, ignore_errors=True)

    # ── Ollama Protocol Interaction (Invariant 5) ────────────────────────

    def _query_ollama(self, messages: list[dict[str, str]]) -> str:
        """Invoke Ollama API with forced JSON structured format."""
        endpoint = f"{self.ollama_url}/api/chat"
        payload = {
            "model": "qwen2.5-coder:7b",
            "messages": messages,
            "format": "json",
            "stream": False,
        }
        response = self.client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {})
        raw_content = str(message.get("content", "")).strip()
        return _sanitize_json_output(raw_content)

    # ── Policy Enforcement (Invariant 2) ─────────────────────────────────

    def _policy_check(self, action: AgentAction) -> None:
        """Enforce canonical path resolution and sandbox policy boundaries."""
        if action.action == "write_file":
            resolved_ws = self.workspace.resolve()
            target_path = (self.workspace / action.path).resolve()

            if not target_path.is_relative_to(resolved_ws):
                raise PermissionError(
                    f"Security violation: path traversal blocked for path: {action.path}"
                )

            if target_path == resolved_ws:
                raise PermissionError("Security violation: cannot overwrite workspace root directory.")

            if target_path.exists() and target_path.is_dir():
                raise IsADirectoryError(
                    f"Security violation: target path {action.path} is an existing directory."
                )

            mind_internal = (self.workspace / ".mind").resolve()
            if target_path == mind_internal or target_path.is_relative_to(mind_internal):
                raise PermissionError(
                    f"Security violation: mutation of .mind internal storage blocked: {action.path}"
                )

        elif action.action == "run_command":
            if not action.command:
                raise ValueError("Command list cannot be empty.")
            for arg in action.command:
                if not isinstance(arg, str):
                    raise TypeError(f"Command arguments must be strings, got: {type(arg)}")
            if not action.command[0].strip():
                raise ValueError("Executable binary name cannot be empty.")

        elif action.action == "run_skill_script":
            skill = self.skill_registry.get(action.skill_name)
            if skill is None:
                raise PermissionError(
                    f"Security violation: skill '{action.skill_name}' is not in registry."
                )
            if action.script_name not in skill.scripts:
                raise PermissionError(
                    f"Security violation: script '{action.script_name}' is not declared in skill '{action.skill_name}'."
                )
            for arg in action.args:
                if not isinstance(arg, str):
                    raise TypeError(f"Script arguments must be strings, got: {type(arg)}")

    # ── Host-Side & Sandboxed Execution (Invariant 2) ────────────────────

    def _execute_action(self, action: AgentAction) -> dict[str, Any]:
        """Apply write_file host-side or delegate run_command / run_skill_script to Bubblewrap."""
        if action.action == "write_file":
            target_path = (self.workspace / action.path).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(action.content, encoding="utf-8")
            return {
                "operation": "write_file",
                "path": str(target_path.relative_to(self.workspace.resolve())),
                "bytes_written": len(action.content.encode("utf-8")),
            }
        elif action.action == "run_skill_script":
            skill = self.skill_registry.get(action.skill_name)
            if skill is None:
                raise ValueError(f"Skill '{action.skill_name}' is not registered.")
            if action.script_name not in skill.scripts:
                raise FileNotFoundError(
                    f"Script '{action.script_name}' not found in skill '{action.skill_name}'."
                )

            # Materialize the script inside workspace .mind/skills/<skill>/<script>
            script_path = self.mind_dir / "skills" / action.skill_name / action.script_name
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(skill.scripts[action.script_name], encoding="utf-8")

            command = ["python3", str(script_path), *action.args]
            completed = self.sandbox.run(command, timeout_sec=action.timeout_sec)
            return {
                "operation": "run_skill_script",
                "skill_name": action.skill_name,
                "script_name": action.script_name,
                "command": command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        else:
            completed = self.sandbox.run(action.command, timeout_sec=action.timeout_sec)
            return {
                "operation": "run_command",
                "command": action.command,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }

    # ── Main 11-Phase Lifecycle Execution ────────────────────────────────

    def run(self, task_prompt: str) -> bool:
        """Execute the full 11-phase agent lifecycle.

        Args:
            task_prompt: Natural language engineering request.

        Returns:
            True if verification passed; False if repairs exhausted and workspace rolled back.
        """
        self.turn = 0

        # Phase 1: INTAKE
        self._emit_trace(
            PhaseEnum.INTAKE,
            {
                "task_prompt": task_prompt,
                "workspace": str(self.workspace),
                "skills_available": [s.metadata.name for s in self.skill_registry.list_skills()],
            },
        )

        # Phase 2: ROUTE
        skill_match = self.skill_router.route(task_prompt)
        self.active_skill_match = skill_match

        is_rtl = isinstance(self.verifier, RTLVerifier)
        if skill_match.skill is not None:
            domain_name = skill_match.suggested_domain
        else:
            domain_name = "RTL" if is_rtl else "SOFTWARE"

        self._emit_trace(
            PhaseEnum.ROUTE,
            {
                "domain": domain_name,
                "verifier": type(self.verifier).__name__,
                "max_repairs": self.max_repairs,
                "active_skill": skill_match.skill.metadata.name if skill_match.skill else None,
                "skill_score": skill_match.score,
                "matched_keywords": skill_match.matched_keywords,
                "relevant_references": [r.name for r in skill_match.relevant_references],
                "reasoning": skill_match.reasoning,
            },
        )

        # Phase 3: SNAPSHOT
        copied_items = self._create_snapshot()
        self._emit_trace(
            PhaseEnum.SNAPSHOT,
            {
                "snapshot_path": str(self.snapshot_dir),
                "items_captured": copied_items,
            },
        )

        system_instruction = (
            "You are Mind 3.0, a deterministic, fail-closed AI engineering agent.\n"
            "You MUST respond ONLY with a valid JSON object matching the AgentAction schema.\n"
            "Supported actions:\n"
            '1. {"action": "write_file", "path": "<relative_path>", "content": "<file_content>"}\n'
            '2. {"action": "run_command", "command": ["<cmd>", "<arg1>", "<arg2>"], "timeout_sec": 30}\n'
            '3. {"action": "run_skill_script", "skill_name": "<skill_name>", "script_name": "<relative_script_path>", "args": ["<arg1>"]}\n'
            "Strict rules: Never wrap output in markdown codeblocks. Do not include prose or commentary.\n"
        )

        if self.active_skill_match and self.active_skill_match.skill:
            skill = self.active_skill_match.skill
            system_instruction += (
                f"\n--- ACTIVE SPECIALIZED DOMAIN SKILL: {skill.metadata.name} ---\n"
                f"{skill.instructions}\n"
            )
            if self.active_skill_match.relevant_references:
                system_instruction += "\n--- MANDATORY DOMAIN REFERENCE SPECIFICATIONS ---\n"
                for ref in self.active_skill_match.relevant_references:
                    system_instruction += f"\n[{ref.name}]\n{ref.content}\n"

        repair_feedback: str | None = None

        while self.turn < self.max_repairs:
            messages: list[dict[str, str]] = [
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": (
                        f"Task: {task_prompt}"
                        if repair_feedback is None
                        else f"Task: {task_prompt}\n\nPrevious attempt failed verification:\n{repair_feedback}\nPlease repair the implementation."
                    ),
                },
            ]

            # Phase 4: MODEL_CALL
            try:
                raw_model_response = self._query_ollama(messages)
            except Exception as exc:
                self._emit_trace(
                    PhaseEnum.MODEL_CALL,
                    {"error": f"Ollama query failed: {exc}", "turn": self.turn},
                )
                self.turn += 1
                repair_feedback = f"Model call failed: {exc}"
                continue

            self._emit_trace(
                PhaseEnum.MODEL_CALL,
                {"model": "qwen2.5-coder:7b", "raw_response": raw_model_response},
            )

            # Phase 5: PARSE
            try:
                cleaned_response = _sanitize_json_output(raw_model_response)
                action = agent_action_adapter.validate_json(cleaned_response)
                self._emit_trace(
                    PhaseEnum.PARSE,
                    {"parsed_action": action.action, "turn": self.turn},
                )
            except Exception as exc:
                self._emit_trace(
                    PhaseEnum.PARSE,
                    {"error": f"Schema parse error: {exc}", "raw": raw_model_response},
                )
                self.turn += 1
                repair_feedback = (
                    f"Your response did not match the AgentAction JSON schema: {exc}\n"
                    f"Ensure you return raw JSON without markdown formatting."
                )
                continue

            # Phase 6: POLICY_CHECK
            try:
                self._policy_check(action)
                self._emit_trace(
                    PhaseEnum.POLICY_CHECK,
                    {"policy_status": "APPROVED", "action": action.action},
                )
            except Exception as exc:
                self._emit_trace(
                    PhaseEnum.POLICY_CHECK,
                    {"policy_status": "DENIED", "reason": str(exc)},
                )
                self.turn += 1
                repair_feedback = f"Policy violation: {exc}"
                continue

            # Phase 7: EXECUTE
            try:
                execution_record = self._execute_action(action)
                self._emit_trace(PhaseEnum.EXECUTE, execution_record)
            except Exception as exc:
                self._emit_trace(
                    PhaseEnum.EXECUTE,
                    {"error": f"Execution error: {exc}"},
                )
                self.turn += 1
                repair_feedback = f"Action execution failed: {exc}"
                continue

            # Phase 8: OBSERVE
            self._emit_trace(PhaseEnum.OBSERVE, {"observed": execution_record})

            # Phase 9: VERIFY
            v_result: VerificationResult = self.verifier.verify(
                self.workspace, self.sandbox
            )
            self._emit_trace(
                PhaseEnum.VERIFY,
                {
                    "passed": v_result.passed,
                    "domain": v_result.domain.value,
                    "exit_code": v_result.exit_code,
                    "failure_reason": v_result.failure_reason,
                    "error_category": v_result.error_category,
                    "silicon_verified": v_result.silicon_verified,
                    "gate_reports": v_result.gate_reports,
                    "stdout": v_result.stdout,
                    "stderr": v_result.stderr,
                },
            )

            # Phase 10: REPAIR_OR_FINISH
            if v_result.passed:
                self._purge_snapshot()
                status_label = "SILICON_VERIFIED" if v_result.silicon_verified else "VERIFIED_SUCCESS"
                self._emit_trace(
                    PhaseEnum.REPAIR_OR_FINISH,
                    {
                        "status": status_label,
                        "turns_taken": self.turn + 1,
                        "workspace_clean": True,
                        "silicon_verified": v_result.silicon_verified,
                        "gate_reports": v_result.gate_reports,
                    },
                )
                # Phase 11: TRACE Finalization
                self._emit_trace(
                    PhaseEnum.TRACE,
                    {
                        "final_status": status_label,
                        "total_steps": self.step_index,
                        "session_id": self.session_id,
                    },
                )
                return True

            self.turn += 1

            # Compact, non-bloating repair feedback categorized by failure code
            if v_result.error_category == "LATCH_INFERRED":
                repair_feedback = (
                    "GATE 1 SIGN-OFF FAILURE: Latch inferred in combinational logic.\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Ensure every 'if' has an explicit 'else' branch and every 'case' includes a 'default'."
                )
            elif v_result.error_category == "FORMAL_INVARIANT_BREACH":
                repair_feedback = (
                    "GATE 2 SIGN-OFF FAILURE: Formal SVA invariant breached in SymbiYosys BMC.\n"
                    f"Counterexample Trace: {v_result.failure_reason}\n"
                    "Fix Invariant: Correct sequential transition condition to prevent illegal state activation."
                )
            elif v_result.error_category == "COVERAGE_DEFICIT":
                repair_feedback = (
                    "GATE 3 SIGN-OFF FAILURE: Coverage threshold deficit.\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Exercise unreached branches and toggles."
                )
            elif v_result.error_category == "TIMING_SLACK_VIOLATION":
                repair_feedback = (
                    "GATE 4 SIGN-OFF FAILURE: OpenSTA timing violation (Slack < 0 ps).\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Reduce combinational logic depth and cell delay along the critical path."
                )
            else:
                repair_feedback = (
                    f"Verification failed in {v_result.domain.value} domain (exit code {v_result.exit_code}):\n"
                    f"Reason: {v_result.failure_reason}\n"
                    f"Compiler/Runner stderr:\n{v_result.stderr[:1000]}"
                )

            if self.turn >= self.max_repairs:
                self._restore_snapshot()
                self._emit_trace(
                    PhaseEnum.REPAIR_OR_FINISH,
                    {
                        "status": "ROLLED_BACK",
                        "turns_exhausted": self.turn,
                        "reverted_to_snapshot": str(self.snapshot_dir),
                        "last_error_category": v_result.error_category,
                    },
                )
                # Phase 11: TRACE Finalization
                self._emit_trace(
                    PhaseEnum.TRACE,
                    {
                        "final_status": "ROLLED_BACK",
                        "total_steps": self.step_index,
                        "session_id": self.session_id,
                    },
                )
                return False

            self._emit_trace(
                PhaseEnum.REPAIR_OR_FINISH,
                {
                    "status": "REPAIR_REQUIRED",
                    "next_turn": self.turn,
                    "max_repairs": self.max_repairs,
                },
            )

        # In case loop exits without return
        self._restore_snapshot()
        self._emit_trace(
            PhaseEnum.REPAIR_OR_FINISH,
            {
                "status": "ROLLED_BACK",
                "reason": f"Max repair budget of {self.max_repairs} turns exhausted.",
            },
        )
        self._emit_trace(
            PhaseEnum.TRACE,
            {"final_status": "ROLLED_BACK", "session_id": self.session_id},
        )
        return False


__all__ = ["PhaseDriver"]
