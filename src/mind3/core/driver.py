"""
PhaseDriver: 11-phase deterministic execution engine for Mind 3.0.
Integrates Bubblewrap sandboxing, Ollama LLM driver, atomic snapshot rollbacks, and canonical trace hashing.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import httpx

from ..sandbox.bwrap import BubblewrapSandbox
from ..skills import SkillMatch, SkillRegistry, SkillRouter
from .contracts import (
    ContractSynthesizer,
    InterfaceContract,
    RTLGenerator,
    VerificationHarnessGenerator,
)
from .types import (
    AgentAction,
    PhaseEnum,
    RunCommandAction,
    RunSkillScriptAction,
    TelemetryEvent,
    TraceRecord,
    VerificationResult,
    WriteBatchFilesAction,
    WriteFileAction,
    agent_action_adapter,
)
from .verifier import BaseVerifier, RTLVerifier, SiliconSignoffVerifier


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


def _parse_model_code_response(raw_output: str) -> str:
    """Deterministically parse code or tool action from model output.

    Replaces fragile string-sniffing heuristics with rigorous JSON schema validation:
    1. First, attempts to parse as a structured AgentAction (e.g. WriteFileAction).
       If valid, extracts the file content directly from the typed schema.
    2. Second, attempts to parse as raw JSON dictionary containing 'content' or 'code'.
    3. Third, if not JSON, cleans markdown code fences (```verilog / ```systemverilog / ```).
    4. Returns the extracted code without corruption.
    """
    cleaned = _sanitize_json_output(raw_output)

    # 1. Attempt strict Pydantic AgentAction deserialization
    try:
        action_obj = agent_action_adapter.validate_json(cleaned)
        if isinstance(action_obj, WriteFileAction):
            return action_obj.content
    except Exception:
        action_obj = None

    # 2. Attempt generic JSON dict extraction if model produced JSON without full schema
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            for key in ("content", "code", "rtl", "verilog", "systemverilog"):
                if key in data and isinstance(data[key], str):
                    return data[key]
    except Exception:
        data = None

    # 3. Handle raw code or markdown-wrapped code
    fence_pattern = re.compile(r"```(?:verilog|systemverilog|sv|v)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
    match = fence_pattern.search(raw_output)
    if match:
        return match.group(1).strip()

    return cleaned


NON_REPAIRABLE_CATEGORIES: set[str] = {
    "EDA_BINARY_MISSING",
    "TIMING_REPORT_UNPARSEABLE",
    "MISSING_SOURCE_FILES",
    "MISSING_NETLIST_FOR_PNR",
    "MISSING_LIBERTY_FOR_PNR",
    "CDC_ANALYSIS_FAILED",
}


class OpenRouterModelRegistryError(Exception):
    """Raised when querying the OpenRouter model registry fails and no valid cache exists."""


class OpenRouterModelRegistry:
    """Dynamic, fail-closed model registry for OpenRouter endpoints.

    Queries the live OpenRouter API (https://openrouter.ai/api/v1/models) to discover
    active models without hardcoded or fabricated slugs. Implements configurable TTL
    caching and strictly validates availability before dispatch.
    """

    DEFAULT_CACHE_TTL_SEC: float = 3600.0  # 1 hour
    _cached_models: list[dict[str, Any]] = []
    _last_fetch_time: float = 0.0

    @classmethod
    def fetch_models(
        cls,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 10.0,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SEC,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch models from OpenRouter API with configurable TTL caching.

        Fails closed on HTTP error or unreachable endpoint unless cached data is valid.
        Raises OpenRouterModelRegistryError on query failure with no valid cache.
        """
        now = time.time()
        if not force_refresh and cls._cached_models and (now - cls._last_fetch_time) < ttl_seconds:
            return cls._cached_models

        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(f"{base_url.rstrip('/')}/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                models = data.get("data", [])
                if not isinstance(models, list):
                    raise ValueError("Unexpected OpenRouter API response format: 'data' is not a list")
                cls._cached_models = models
                cls._last_fetch_time = now
                return models
        except Exception as exc:
            if not force_refresh and cls._cached_models and (now - cls._last_fetch_time) < ttl_seconds:
                return cls._cached_models
            raise OpenRouterModelRegistryError(
                f"Failed to query OpenRouter model registry at {base_url}/models: {exc}. "
                "OpenRouterModelRegistry operates in fail-closed mode without silent fallback to hardcoded lists."
            ) from exc

    @classmethod
    def get_free_models(
        cls,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 10.0,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SEC,
        force_refresh: bool = False,
    ) -> list[str]:
        """Return IDs of currently active free models on OpenRouter."""
        models = cls.fetch_models(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            ttl_seconds=ttl_seconds,
            force_refresh=force_refresh,
        )
        free_ids: list[str] = []
        for m in models:
            model_id = m.get("id", "")
            pricing = m.get("pricing", {})
            prompt_cost = str(pricing.get("prompt", "1"))
            completion_cost = str(pricing.get("completion", "1"))
            if (prompt_cost == "0" and completion_cost == "0") or model_id.endswith(":free"):
                free_ids.append(model_id)
        return sorted(free_ids)


def fetch_openrouter_free_models(
    api_key: str | None = None,
    base_url: str = "https://openrouter.ai/api/v1",
    timeout: float = 10.0,
    ttl_seconds: float = 3600.0,
    force_refresh: bool = False,
) -> list[str]:
    """Query https://openrouter.ai/api/v1/models, filter for free-tier models, and cache with configurable TTL.

    Raises:
        OpenRouterModelRegistryError: On query failure with no valid cache.
    """
    return OpenRouterModelRegistry.get_free_models(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        ttl_seconds=ttl_seconds,
        force_refresh=force_refresh,
    )


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
        model: str = "qwen2.5-coder:7b",
        provider: str = "ollama",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the driver runtime.

        Args:
            session_id: Unique execution session token.
            workspace: Target project directory.
            verifier: Domain-specific verification oracle.
            max_repairs: Maximum allowable self-correction turns before rollback.
                Note: A budget of 3 is a deliberately conservative ceiling.
                When deploying weaker local models (e.g., 7B parameter models),
                signoff repair loops against formal invariants or timing closure
                often require raising this ceiling to converge.
            ollama_url: Base HTTP endpoint for Ollama daemon.
            sandbox: Optional pre-configured BubblewrapSandbox instance.
            transcript_path: Optional custom destination file for transcript.jsonl.
            skills_dir: Optional path to skills directory containing .skill archives or folders.
            model: Name of the generator model (default: "qwen2.5-coder:7b").
            provider: LLM backend provider ("ollama" or "openrouter", default: "ollama").
            api_key: API authorization key (defaults to OPENROUTER_API_KEY env var for OpenRouter).
            base_url: Optional custom provider API base URL.
        """
        self.session_id: str = session_id
        self.workspace: Path = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.verifier: BaseVerifier = verifier
        self.max_repairs: int = max_repairs
        self.ollama_url: str = ollama_url.rstrip("/")
        self.model: str = model

        self.provider: str = provider.lower()
        if self.provider not in {"ollama", "openrouter"}:
            raise ValueError(f"Unsupported provider '{provider}'. Must be 'ollama' or 'openrouter'.")

        self.api_key: str | None = api_key
        if self.provider == "openrouter":
            if self.api_key is None:
                self.api_key = os.environ.get("OPENROUTER_API_KEY")
            if not self.api_key:
                raise ValueError(
                    "OpenRouter provider requires 'api_key' parameter or 'OPENROUTER_API_KEY' environment variable."
                )
            self.base_url: str = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        else:
            self.base_url = (base_url or self.ollama_url).rstrip("/")

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

    # ── Model Provider Interaction (Invariant 5) ────────────────────────

    @staticmethod
    def _build_prompt_messages(
        system_instruction: str,
        task_prompt: str,
        repair_feedback: str | None = None,
    ) -> list[dict[str, str]]:
        """Construct standard 2-message system/user prompt payload."""
        user_content = (
            f"Task: {task_prompt}"
            if repair_feedback is None
            else f"Task: {task_prompt}\n\nPrevious attempt failed verification:\n{repair_feedback}\nPlease repair the implementation."
        )
        return [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ]

    def _query_ollama(self, messages: list[dict[str, str]]) -> str:
        """Invoke Ollama API with forced JSON structured format."""
        endpoint = f"{self.ollama_url}/api/chat"
        payload = {
            "model": self.model,
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

    def _query_openrouter(
        self,
        prompt_or_messages: str | list[dict[str, str]],
        system_instruction: str | None = None,
    ) -> str:
        """Invoke OpenRouter API with OpenAI-compatible chat completions schema."""
        if isinstance(prompt_or_messages, list):
            messages = prompt_or_messages
        else:
            messages = self._build_prompt_messages(
                system_instruction=system_instruction or "",
                task_prompt=prompt_or_messages,
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/mind3/mind3",
            "X-Title": "Mind 3.0 VLSI Agent",
        }
        payload = {
            "model": self.model,
            "messages": messages,
        }

        try:
            response = self.client.post(endpoint, json=payload, headers=headers)
        except httpx.RequestError as req_err:
            raise RuntimeError(f"OpenRouter network request failed: {req_err}") from req_err

        if response.status_code == 401:
            raise PermissionError(
                f"OpenRouter authentication failed (HTTP 401): {response.text}"
            )
        elif response.status_code == 429:
            raise RuntimeError(
                f"RATE_LIMITED: OpenRouter rate limit exceeded (HTTP 429): {response.text}"
            )
        elif response.is_error:
            raise RuntimeError(
                f"OpenRouter API error (HTTP {response.status_code}): {response.text}"
            )

        data = response.json()
        try:
            choices = data.get("choices", [])
            if not choices:
                raise ValueError(f"OpenRouter response contained no choices: {data}")
            raw_content = choices[0]["message"]["content"]
            if raw_content is None:
                raw_content = ""
            raw_content = str(raw_content).strip()
        except (KeyError, IndexError, TypeError) as parse_err:
            raise ValueError(
                f"Unexpected OpenRouter response structure: {data}"
            ) from parse_err

        return _sanitize_json_output(raw_content)

    def _query_model(
        self,
        prompt_or_messages: str | list[dict[str, str]],
        system_instruction: str | None = None,
    ) -> str:
        """Dispatch model query to configured provider (ollama or openrouter)."""
        if isinstance(prompt_or_messages, list):
            messages = prompt_or_messages
        else:
            messages = self._build_prompt_messages(
                system_instruction=system_instruction or "",
                task_prompt=prompt_or_messages,
            )

        if self.provider == "openrouter":
            return self._query_openrouter(messages)
        elif self.provider == "ollama":
            return self._query_ollama(messages)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

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

        elif action.action == "write_batch_files":
            if not action.files:
                raise ValueError("write_batch_files list cannot be empty.")
            for sub_action in action.files:
                self._policy_check(sub_action)

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
        """Apply write_file/write_batch_files host-side or delegate run_command / run_skill_script to Bubblewrap."""
        if action.action == "write_file":
            target_path = (self.workspace / action.path).resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(action.content, encoding="utf-8")
            return {
                "operation": "write_file",
                "path": str(target_path.relative_to(self.workspace.resolve())),
                "bytes_written": len(action.content.encode("utf-8")),
            }
        elif action.action == "write_batch_files":
            records = [self._execute_action(sub_f) for sub_f in action.files]
            total_bytes = sum(r.get("bytes_written", 0) for r in records)
            return {
                "operation": "write_batch_files",
                "count": len(records),
                "total_bytes_written": total_bytes,
                "files": records,
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
            True if verification passed; False if repairs exhausted or non-repairable failure.
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
            '2. {"action": "write_batch_files", "files": [{"action": "write_file", "path": "<path1>", "content": "<content1>"}]}\n'
            '3. {"action": "run_command", "command": ["<cmd>", "<arg1>", "<arg2>"], "timeout_sec": 30}\n'
            '4. {"action": "run_skill_script", "skill_name": "<skill_name>", "script_name": "<relative_script_path>", "args": ["<arg1>"]}\n'
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
            messages: list[dict[str, str]] = self._build_prompt_messages(
                system_instruction=system_instruction,
                task_prompt=task_prompt,
                repair_feedback=repair_feedback,
            )

            # Phase 4: MODEL_CALL
            try:
                raw_model_response = self._query_model(messages)
            except Exception as exc:
                self._emit_trace(
                    PhaseEnum.MODEL_CALL,
                    {"error": f"Model query failed: {exc}", "turn": self.turn},
                )
                self.turn += 1
                repair_feedback = f"Model call failed: {exc}"
                continue

            self._emit_trace(
                PhaseEnum.MODEL_CALL,
                {"model": self.model, "raw_response": raw_model_response},
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

            # Non-repairable environmental / infrastructure failures immediately abort
            if v_result.error_category in NON_REPAIRABLE_CATEGORIES:
                self._restore_snapshot()
                self._emit_trace(
                    PhaseEnum.REPAIR_OR_FINISH,
                    {
                        "status": "ABORTED_NON_REPAIRABLE",
                        "error_category": v_result.error_category,
                        "turns_taken": self.turn,
                        "reverted_to_snapshot": str(self.snapshot_dir),
                        "failure_reason": v_result.failure_reason,
                    },
                )
                # Phase 11: TRACE Finalization
                self._emit_trace(
                    PhaseEnum.TRACE,
                    {
                        "final_status": "ABORTED_NON_REPAIRABLE",
                        "total_steps": self.step_index,
                        "session_id": self.session_id,
                        "error_category": v_result.error_category,
                    },
                )
                return False

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
            elif v_result.error_category == "MISSING_VERIFICATION_ARTIFACT":
                repair_feedback = (
                    "VERIFICATION ARTIFACT MISSING: Required verification harness or testbench is missing.\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Use 'write_file' to author the missing verification harness "
                    "(e.g. .sby formal verification configuration for SymbiYosys or .cpp testbench for Verilator)."
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

    def run_silicon_pipeline(
        self,
        task_prompt: str,
        liberty_path: str | list[str] | None = None,
    ) -> bool:
        """Execute decoupled multi-agent silicon synthesis, testbench generation, and 4-gate signoff.

        Orchestrates:
        1. Lead Architect (ContractSynthesizer) -> InterfaceContract
        2. Verification Lead (VerificationHarnessGenerator) -> SVA bind, SBY, SDC, C++ harness
        3. Principal RTL Design Engineer (RTLGenerator) -> Synthesizable SystemVerilog module
        4. Silicon Signoff Oracle (SiliconSignoffVerifier) -> 4 hierarchical verification gates
        5. Targeted Multi-Agent Repair Loop for fast convergence
        """
        self.turn = 0

        # Phase 1: INTAKE
        self._emit_trace(
            PhaseEnum.INTAKE,
            {
                "task_prompt": task_prompt,
                "workspace": str(self.workspace),
                "pipeline": "silicon_multi_agent_pipeline",
            },
        )

        # Phase 2: ROUTE
        self._emit_trace(
            PhaseEnum.ROUTE,
            {
                "domain": "RTL",
                "verifier": "SiliconSignoffVerifier",
                "max_repairs": self.max_repairs,
                "pipeline": "decoupled_multi_agent",
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

        # Stage 1: Lead Silicon Architect -> Extract InterfaceContract
        contract_prompt = ContractSynthesizer.build_prompt(task_prompt)
        self._emit_trace(
            PhaseEnum.MODEL_CALL,
            {"role": "Lead Silicon Architect", "stage": "contract_synthesis"},
        )
        arch_messages = self._build_prompt_messages(
            system_instruction=contract_prompt["system"],
            task_prompt=contract_prompt["user"],
        )
        try:
            raw_contract = self._query_model(arch_messages)
            cleaned_contract_json = _sanitize_json_output(raw_contract)
            contract = InterfaceContract.model_validate_json(cleaned_contract_json)
            self._emit_trace(
                PhaseEnum.PARSE,
                {"role": "Lead Silicon Architect", "module_name": contract.module_name, "ports": len(contract.ports)},
            )
        except Exception as exc:
            self._emit_trace(
                PhaseEnum.PARSE,
                {"error": f"Architect contract synthesis failed: {exc}"},
            )
            self._restore_snapshot()
            return False

        # Stage 2: Verification Lead -> Generate Harnesses & SVA Bind (Zero RTL access)
        sva_bind_content = VerificationHarnessGenerator.build_sva_bind_module(contract)
        sby_content = VerificationHarnessGenerator.build_sby_config(
            contract, depth=25, include_sva_file=bool(contract.sva_properties)
        )
        cpp_tb_content = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        sdc_content = contract.timing.to_sdc()

        harness_files = [
            WriteFileAction(path=f"{contract.module_name}_sva.sv", content=sva_bind_content),
            WriteFileAction(path=f"{contract.module_name}.sby", content=sby_content),
            WriteFileAction(path=f"{contract.module_name}_tb.cpp", content=cpp_tb_content),
            WriteFileAction(path=f"{contract.module_name}.sdc", content=sdc_content),
        ]
        batch_harness_action = WriteBatchFilesAction(files=harness_files)
        self._policy_check(batch_harness_action)
        exec_harness = self._execute_action(batch_harness_action)
        self._emit_trace(PhaseEnum.EXECUTE, {"role": "Verification Lead", "staged_artifacts": exec_harness})

        # Stage 3: Principal RTL Design Engineer -> Synthesize SystemVerilog (Zero harness access)
        rtl_prompt = RTLGenerator.build_prompt(contract)
        self._emit_trace(
            PhaseEnum.MODEL_CALL,
            {"role": "Principal RTL Design Engineer", "module": contract.module_name},
        )
        rtl_messages = self._build_prompt_messages(
            system_instruction=rtl_prompt["system"],
            task_prompt=rtl_prompt["user"],
        )
        try:
            raw_rtl = self._query_model(rtl_messages)
            cleaned_rtl = _sanitize_json_output(raw_rtl)
            try:
                action_obj = agent_action_adapter.validate_json(cleaned_rtl)
                rtl_code = action_obj.content if isinstance(action_obj, WriteFileAction) else cleaned_rtl
            except Exception:
                rtl_code = cleaned_rtl

            rtl_action = WriteFileAction(path=f"{contract.module_name}.sv", content=rtl_code)
            self._policy_check(rtl_action)
            exec_rtl = self._execute_action(rtl_action)
            self._emit_trace(PhaseEnum.EXECUTE, {"role": "Principal RTL Design Engineer", "rtl_file": exec_rtl})
        except Exception as exc:
            self._emit_trace(
                PhaseEnum.EXECUTE,
                {"error": f"RTL design synthesis failed: {exc}"},
            )
            self._restore_snapshot()
            return False

        # Stage 4: Silicon Signoff Oracle Evaluation & Repair Loop
        signoff_verifier = (
            self.verifier
            if isinstance(self.verifier, SiliconSignoffVerifier)
            else SiliconSignoffVerifier(
                top_module=contract.module_name,
                contract=contract,
                liberty_path=liberty_path or getattr(self.verifier, "liberty_paths", None),
                allow_mock_fallback=True,
            )
        )

        repair_guidance: str | None = None

        while self.turn < self.max_repairs:
            if repair_guidance is not None:
                self._emit_trace(
                    PhaseEnum.MODEL_CALL,
                    {"role": "Targeted RTL Repair Loop", "turn": self.turn, "guidance": repair_guidance},
                )
                repair_messages = self._build_prompt_messages(
                    system_instruction=rtl_prompt["system"],
                    task_prompt=f"{rtl_prompt['user']}\n\n{repair_guidance}",
                )
                try:
                    raw_repair = self._query_model(repair_messages)
                    cleaned_repair = _sanitize_json_output(raw_repair)
                    try:
                        action_rep = agent_action_adapter.validate_json(cleaned_repair)
                        repaired_code = action_rep.content if isinstance(action_rep, WriteFileAction) else cleaned_repair
                    except Exception:
                        repaired_code = cleaned_repair

                    rep_action = WriteFileAction(path=f"{contract.module_name}.sv", content=repaired_code)
                    self._policy_check(rep_action)
                    self._execute_action(rep_action)
                except Exception as exc:
                    self.turn += 1
                    repair_guidance = f"Model call failed: {exc}"
                    continue

            # Phase 9: VERIFY
            v_result: VerificationResult = signoff_verifier.verify(self.workspace, self.sandbox)
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
                    "netlist_path": v_result.netlist_path,
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
                        "silicon_verified": v_result.silicon_verified,
                        "gate_reports": v_result.gate_reports,
                        "netlist_path": v_result.netlist_path,
                    },
                )
                self._emit_trace(
                    PhaseEnum.TRACE,
                    {
                        "final_status": status_label,
                        "total_steps": self.step_index,
                        "session_id": self.session_id,
                    },
                )
                return True

            if v_result.error_category in NON_REPAIRABLE_CATEGORIES:
                self._restore_snapshot()
                self._emit_trace(
                    PhaseEnum.REPAIR_OR_FINISH,
                    {"status": "ABORTED_NON_REPAIRABLE", "error_category": v_result.error_category},
                )
                return False

            self.turn += 1

            if v_result.error_category == "LATCH_INFERRED":
                repair_guidance = (
                    "GATE 1 SIGN-OFF FAILURE: Unintended latch inferred in combinational logic.\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Ensure every 'if' has an explicit 'else' branch and all case statements have 'default'."
                )
            elif v_result.error_category == "FORMAL_INVARIANT_BREACH":
                repair_guidance = (
                    "GATE 2 SIGN-OFF FAILURE: Formal SVA invariant breached in SymbiYosys BMC.\n"
                    f"Counterexample Trace: {v_result.failure_reason}\n"
                    "Fix Invariant: Correct sequential transition condition to prevent illegal state activation."
                )
            elif v_result.error_category == "TIMING_SLACK_VIOLATION":
                repair_guidance = (
                    "GATE 4 SIGN-OFF FAILURE: OpenSTA setup timing violation (WNS < 0 ps).\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Pipeline logic or reduce combinational depth along the critical path."
                )
            elif v_result.error_category == "HOLD_SLACK_VIOLATION":
                repair_guidance = (
                    "GATE 4 SIGN-OFF FAILURE: OpenSTA hold timing violation (hold WNS < min threshold).\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Add buffer insertion on short hold-critical paths or reduce clock skew."
                )
            elif v_result.error_category == "CDC_VIOLATION":
                cdc_msgs = "; ".join(v_result.cdc_violations[:3]) if v_result.cdc_violations else "(see stdout)"
                repair_guidance = (
                    "GATE 6 SIGN-OFF FAILURE: Yosys CDC analysis detected unregistered clock-domain crossings.\n"
                    f"Violations: {cdc_msgs}\n"
                    "Fix Invariant: Add 2-FF synchronizer registers on all signals crossing clock domains."
                )
            elif v_result.error_category == "PNR_PLACEMENT_FAILED":
                repair_guidance = (
                    "GATE 5 SIGN-OFF FAILURE: OpenROAD place-and-route failed.\n"
                    f"Details: {v_result.failure_reason}\n"
                    "Fix Invariant: Reduce logic density, increase floorplan utilization margin, "
                    "or simplify combinational fanout."
                )
            else:
                repair_guidance = f"Verification failure ({v_result.error_category}): {v_result.failure_reason}"

        # If budget exhausted
        self._restore_snapshot()
        self._emit_trace(
            PhaseEnum.REPAIR_OR_FINISH,
            {"status": "ROLLED_BACK", "reason": f"Max repairs ({self.max_repairs}) exhausted."},
        )
        self._emit_trace(
            PhaseEnum.TRACE,
            {"final_status": "ROLLED_BACK", "session_id": self.session_id},
        )
        return False


@dataclass(frozen=True)
class PPAPoint:
    """Evaluation point along the Power, Performance, Area Pareto frontier."""

    turn: int
    frequency_mhz: float
    setup_wns_ps: float
    power_mw: float | None = None
    area_um2: float | None = None
    passes_timing: bool = True
    passes_physical: bool = True


class PPAOptimizer:
    """Tracks multi-objective PPA metrics and identifies Pareto-optimal designs."""

    def __init__(self) -> None:
        self.points: list[PPAPoint] = []

    def record_point(
        self,
        turn: int,
        frequency_mhz: float,
        setup_wns_ps: float,
        power_mw: float | None = None,
        area_um2: float | None = None,
        passes_timing: bool = True,
        passes_physical: bool = True,
    ) -> PPAPoint:
        point = PPAPoint(
            turn=turn,
            frequency_mhz=frequency_mhz,
            setup_wns_ps=setup_wns_ps,
            power_mw=power_mw,
            area_um2=area_um2,
            passes_timing=passes_timing,
            passes_physical=passes_physical,
        )
        self.points.append(point)
        return point

    def get_pareto_frontier(self) -> list[PPAPoint]:
        """Compute the Pareto-optimal frontier (higher freq, lower power, lower area)."""
        valid_points = [p for p in self.points if p.passes_timing and p.passes_physical]
        if not valid_points:
            return []

        frontier: list[PPAPoint] = []
        for p1 in valid_points:
            dominated = False
            for p2 in valid_points:
                if p1 == p2:
                    continue
                power1 = p1.power_mw if p1.power_mw is not None else float("inf")
                power2 = p2.power_mw if p2.power_mw is not None else float("inf")
                area1 = p1.area_um2 if p1.area_um2 is not None else float("inf")
                area2 = p2.area_um2 if p2.area_um2 is not None else float("inf")

                if (
                    p2.frequency_mhz >= p1.frequency_mhz
                    and power2 <= power1
                    and area2 <= area1
                    and (p2.frequency_mhz > p1.frequency_mhz or power2 < power1 or area2 < area1)
                ):
                    dominated = True
                    break
            if not dominated:
                frontier.append(p1)

        return frontier

    @staticmethod
    def suggest_repair_strategy(error_category: str, failure_reason: str, wns_ps: float | None = None) -> str:
        """Select microarchitectural repair invariant based on error category and PPA feedback."""
        if error_category == "TIMING_SLACK_VIOLATION" or (wns_ps is not None and wns_ps < 0):
            deficit = abs(wns_ps) if wns_ps is not None else 0.0
            if deficit > 500:
                return "CRITICAL SETUP VIOLATION: Add pipeline register stages to slice critical datapath in half."
            else:
                return "MODERATE SETUP VIOLATION: Apply register retiming, reduce logic fanout, or isolate operands."
        elif error_category == "HOLD_SLACK_VIOLATION":
            return "HOLD VIOLATION: Insert minimum-delay buffer cells along short fast-paths; do not increase logic depth."
        elif error_category == "PNR_PLACEMENT_FAILED":
            return "CONGESTION/OVERFLOW: Lower target core utilization by 10%, widen placement halos, or decouple wide muxes."
        elif error_category == "CDC_VIOLATION":
            return "CLOCK DOMAIN CROSSING: Insert 2-stage flip-flop synchronizers or asynchronous FIFO on cross-clock signals."
        return f"REPAIR: Address {error_category} - {failure_reason}"


__all__ = [
    "PhaseDriver",
    "OpenRouterModelRegistry",
    "OpenRouterModelRegistryError",
    "fetch_openrouter_free_models",
    "PPAPoint",
    "PPAOptimizer",
]
