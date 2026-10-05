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
from typing import Any, Literal

import httpx

from ..sandbox.bwrap import BubblewrapSandbox
from ..sandbox.macos import MacOSSandbox
from ..sandbox.platform import get_local_sandbox
from ..skills import SkillMatch, SkillRegistry, SkillRouter
from .contracts import (
    ContractSynthesizer,
    InterfaceContract,
    RTLGenerator,
    validate_contract_consistency,
    UnsupportedFormalPropertyError,
    VerificationFailureEvidence,
    VerificationHarnessGenerator,
    VerificationRepairer,
)
from .formal_templates import UnsupportedFormalTemplate
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


class ModelResponseParseError(ValueError):
    """Raised when model response cannot be parsed into valid RTL."""


REPAIR_MAX_CHANGED_LINE_RATIO = 0.65
REPAIR_MAX_LINE_GROWTH = 3.0


def _repair_diff_stats(before: str, after: str) -> dict[str, float | int]:
    """Compute change-budget statistics for a proposed RTL repair."""
    import difflib

    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    removed = 0
    added = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            removed += i2 - i1
        if tag in {"insert", "replace"}:
            added += j2 - j1
    baseline = max(1, len(before_lines))
    changed = removed + added
    return {
        "before_lines": len(before_lines),
        "after_lines": len(after_lines),
        "added_lines": added,
        "removed_lines": removed,
        "changed_lines": changed,
        "changed_line_ratio": changed / baseline,
        "line_growth_ratio": len(after_lines) / baseline,
    }


_FENCE_REGEX = re.compile(
    r"```(?:verilog|systemverilog|sv)?\s*\n?(.*?)\n?```",
    re.DOTALL | re.IGNORECASE,
)
_MODULE_REGEX = re.compile(
    r"((?:/\*[\s\S]*?\*/\s*|//[^\n]*\n\s*|`[^\n]*\n\s*)*\bmodule\s+[a-zA-Z_]\w*\s*(?:#|\(|;)[\s\S]*?\bendmodule\b)",
    re.DOTALL,
)


ParserMode = Literal["strict", "lenient"]

LENIENT_KNOWN_KEYS = (
    "module_code",
    "verilog_code",
    "code",
    "content",
    "response",
    "rtl",
    "text",
)
"""Documented JSON keys eligible for lenient-mode recovery.

Only these keys are ever inspected. Any other JSON key — even one whose value
contains a complete module — is rejected. There is intentionally no
any-key/any-value scan.
"""


def _parse_model_code_response(
    raw_output: str,
    default_module_name: str | None = None,
    base_code: str | None = None,
    parser_mode: str = "strict",
) -> str:
    """Deterministically parse RTL from model output under an explicit parser mode.

    STRICT mode (default) accepts only clearly identifiable, contract-valid output:
    1. A valid WriteFileAction schema object (content used verbatim).
    2. A clearly fenced Verilog/SystemVerilog block (fenced content used verbatim).
    3. A repair-loop patch object, but only when the caller supplies ``base_code``
       (initial generation never does; this branch is unreachable outside repair).
    4. Raw text that is exactly one Verilog module block, verbatim.
    Anything else raises ModelResponseParseError. Strict mode never searches
    arbitrary JSON keys, never reconstructs modules from AST parts, and never
    applies unicode_escape decoding.

    LENIENT mode (explicit opt-in for local-model formatting deviations) adds
    bounded recovery, in order:
    1-2. Same WriteFileAction and fenced-block handling as strict.
    3. JSON-dict recovery limited to documented shapes: structural AST dicts
       (module/pinout/implementation) and the LENIENT_KNOWN_KEYS values.
       JSON string values in this branch are unescaped once because local
       models frequently double-escape newlines.
    4. Repair-loop patch objects when ``base_code`` is supplied.
    5. Deterministic verbatim extraction of the first complete module block.
    Ambiguous lenient input still raises ModelResponseParseError.

    The ``parser_mode`` argument must be exactly "strict" or "lenient"; any
    other value raises ValueError. The mode is never inferred from provider,
    model name, failure count, or environment.
    """
    if parser_mode not in ("strict", "lenient"):
        raise ValueError(
            f"Unknown parser_mode {parser_mode!r}. Expected 'strict' or 'lenient'."
        )
    cleaned = _sanitize_json_output(raw_output)

    def _unescape(val: str) -> str:
        """Decode literal \\n, \\t, \\\" sequences in a string value structurally."""
        if not isinstance(val, str):
            return ""
        if "\\n" in val or "\\t" in val or '\\"' in val or "\\\\" in val:
            try:
                return val.encode("utf-8").decode("unicode_escape")
            except Exception:
                return val.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")
        return val

    def _reconstruct_from_ast(data: dict) -> str | None:
        """Reconstruct module from structural AST dict: {module, pinout, implementation, etc.}."""
        mod_name = (
            data.get("module")
            or data.get("name")
            or data.get("module_name")
            or data.get("label")
            or data.get("task_id")
            or default_module_name
        )
        if not mod_name or not isinstance(mod_name, str):
            return None

        # Check for implementation key or structural RTL components
        impl_key = None
        for k in (
            "synthesizable_code",
            "implementation",
            "code",
            "body",
            "source_code",
            "source",
            "rtl",
            "design",
            "verilog",
            "systemverilog",
        ):
            if k in data:
                impl_key = k
                break

        impl = ""
        if impl_key is not None:
            impl_raw = data[impl_key]
            if not isinstance(impl_raw, str):
                return None
            impl = _unescape(impl_raw).strip()
        else:
            # Check for structural RTL elements
            internal_signals = data.get("internal_signals") or data.get("signals") or data.get("registers") or {}
            always_blocks = data.get("always_blocks") or data.get("processes") or []
            assign_statements = data.get("assign_statements") or data.get("assigns") or []

            if not internal_signals and not always_blocks and not assign_statements:
                return None

            body_lines = []

            # Internal signals
            if isinstance(internal_signals, dict):
                for sig_name, sig_info in internal_signals.items():
                    if isinstance(sig_info, dict):
                        stype = sig_info.get("type", "logic")
                        swidth = sig_info.get("width") or sig_info.get("bits") or 1
                        sdepth = sig_info.get("depth")
                        width_str = f"[{swidth-1}:0] " if (isinstance(swidth, int) and swidth > 1) else ""
                        depth_str = f" [0:{sdepth-1}]" if (isinstance(sdepth, int) and sdepth > 1) else ""
                        body_lines.append(f"  {stype} {width_str}{sig_name}{depth_str};")
                    elif isinstance(sig_info, str):
                        clean_sig = sig_info.strip().rstrip(";")
                        body_lines.append(f"  {clean_sig};")
            elif isinstance(internal_signals, list):
                for s in internal_signals:
                    if isinstance(s, dict):
                        sname = s.get("name")
                        stype = s.get("type", "logic")
                        swidth = s.get("width") or s.get("bits") or 1
                        sdepth = s.get("depth")
                        width_str = f"[{swidth-1}:0] " if (isinstance(swidth, int) and swidth > 1) else ""
                        depth_str = f" [0:{sdepth-1}]" if (isinstance(sdepth, int) and sdepth > 1) else ""
                        if sname:
                            body_lines.append(f"  {stype} {width_str}{sname}{depth_str};")
                    elif isinstance(s, str):
                        clean_s = s.strip().rstrip(";")
                        body_lines.append(f"  {clean_s};")

            # Assign statements
            if isinstance(assign_statements, list):
                for a in assign_statements:
                    if isinstance(a, str):
                        clean_a = a.strip().rstrip(";")
                        body_lines.append(f"  {clean_a};")
            elif isinstance(assign_statements, str):
                body_lines.append(f"  {assign_statements.strip()};")

            # Always blocks
            if isinstance(always_blocks, list):
                for blk in always_blocks:
                    if isinstance(blk, dict):
                        trigger = blk.get("trigger", "").strip()
                        b_content = blk.get("body", "").strip()
                        if trigger:
                            body_lines.append(f"\n  always @({trigger}) begin\n    {b_content}\n  end")
                        else:
                            body_lines.append(f"\n  always_comb begin\n    {b_content}\n  end")
                    elif isinstance(blk, str):
                        body_lines.append(f"\n  {blk.strip()}")

            impl = "\n".join(body_lines)

        target_name = default_module_name if default_module_name else mod_name

        if "endmodule" in impl:
            res = impl
            if default_module_name:
                res = re.sub(r"\bmodule\s+\w+", f"module {default_module_name}", res, count=1)
            return res

        # Parameters
        param_str = ""
        params = data.get("parameters")
        if isinstance(params, dict) and params:
            param_decls = [f"  parameter {k} = {v}" for k, v in params.items()]
            param_str = f" #(\n" + ",\n".join(param_decls) + "\n)"
        elif isinstance(params, list) and params:
            param_decls = []
            for p in params:
                if isinstance(p, dict) and "name" in p:
                    default_val = p.get("default", p.get("value", 0))
                    param_decls.append(f"  parameter {p['name']} = {default_val}")
            if param_decls:
                param_str = f" #(\n" + ",\n".join(param_decls) + "\n)"

        # Pinout / ports / pins
        ports_list = (
            data.get("pinout")
            or data.get("ports")
            or data.get("pins")
            or data.get("port_declarations")
            or data.get("interfaces")
            or []
        )
        rendered_ports = []
        if isinstance(ports_list, list):
            for p in ports_list:
                if isinstance(p, dict):
                    pname = p.get("name", "")
                    if not pname:
                        continue
                    ptype_raw = str(p.get("type", "")).strip()
                    if ptype_raw.startswith(("input", "output", "inout")):
                        parts = ptype_raw.split(maxsplit=1)
                        pdir = parts[0]
                        prest = f" logic {parts[1]}" if len(parts) > 1 else " logic"
                        rendered_ports.append(f"  {pdir}{prest} {pname}")
                        continue
                    pdir = p.get("direction", "input")
                    if pdir not in ("input", "output", "inout"):
                        pdir = "input"
                    ptype = p.get("data_type") or p.get("net_type") or "logic"
                    if ptype in ("input", "output", "inout", "wire", "reg"):
                        ptype = "logic"
                    if "range" in p and p["range"]:
                        prange = str(p["range"]).strip()
                        if not prange.startswith("["):
                            prange = f"[{prange}]"
                        rendered_ports.append(f"  {pdir} {ptype} {prange} {pname}")
                    else:
                        width_val = p.get("width") if p.get("width") is not None else p.get("bits")
                        if width_val is not None:
                            try:
                                pwidth = int(width_val)
                                if pwidth > 1:
                                    rendered_ports.append(f"  {pdir} {ptype} [{pwidth-1}:0] {pname}")
                                else:
                                    rendered_ports.append(f"  {pdir} {ptype} {pname}")
                            except (ValueError, TypeError):
                                rendered_ports.append(f"  {pdir} {ptype} {pname}")
                        else:
                            rendered_ports.append(f"  {pdir} {ptype} {pname}")
        elif isinstance(ports_list, dict):
            for pname, pinfo in ports_list.items():
                if isinstance(pinfo, dict):
                    pdir = pinfo.get("direction") or pinfo.get("type", "input")
                    if pdir not in ("input", "output", "inout"):
                        pdir = "input"
                    ptype = pinfo.get("data_type") or pinfo.get("net_type") or "logic"
                    if ptype in ("input", "output", "inout", "wire", "reg"):
                        ptype = "logic"
                    width_val = pinfo.get("width") if pinfo.get("width") is not None else pinfo.get("bits")
                    if width_val is not None:
                        try:
                            pwidth = int(width_val)
                            if pwidth > 1:
                                rendered_ports.append(f"  {pdir} {ptype} [{pwidth-1}:0] {pname}")
                            else:
                                rendered_ports.append(f"  {pdir} {ptype} {pname}")
                        except (ValueError, TypeError):
                            rendered_ports.append(f"  {pdir} {ptype} {pname}")
                    else:
                        rendered_ports.append(f"  {pdir} {ptype} {pname}")
                elif isinstance(pinfo, str):
                    rendered_ports.append(f"  {pinfo} {pname}")

        ports_block = ",\n".join(rendered_ports)
        body = f"\n\n{impl}\n\n" if impl else "\n"
        if rendered_ports:
            return f"module {target_name}{param_str} (\n{ports_block}\n);{body}endmodule"
        else:
            return f"module {target_name}{param_str} ();{body}endmodule"

    def _apply_naming(code: str) -> str:
        if not default_module_name:
            return code
        # Mask comments with spaces so declaration matching keeps the original source offsets.
        masked = re.sub(r"/\*.*?\*/|//[^\n]*", lambda m: " " * len(m.group(0)), code, flags=re.DOTALL)
        match = re.search(r"\bmodule\s+[A-Za-z_]\w*", masked)
        if not match:
            return code
        replacement = f"module {default_module_name}"
        return code[:match.start()] + replacement + code[match.end():]

    def _apply_repair_patch(data: dict, base: str) -> str | None:
        """Bounded repair-loop patch application.

        This is a repair-loop mechanism, not initial-parse recovery: it is only
        reachable when the caller explicitly supplies ``base_code`` (initial
        generation never does). Patch text is used verbatim; no escape decoding
        is applied because json.loads already decoded standard JSON escapes.
        """
        if "patch" not in data and "replacement" not in data:
            return None
        patch_str = data.get("patch") or data.get("replacement")
        if not isinstance(patch_str, str):
            return None
        patch_str = patch_str.strip()
        if re.search(r"\bmodule\b", patch_str) and re.search(r"\bendmodule\b", patch_str):
            return _apply_naming(patch_str)

        patched_lines = base.splitlines()
        target_line = data.get("line") or data.get("line_number")
        if isinstance(target_line, int) and 1 <= target_line <= len(patched_lines):
            patched_lines[target_line - 1] = patch_str
            candidate = "\n".join(patched_lines)
            if re.search(r"\bmodule\b", candidate) and re.search(r"\bendmodule\b", candidate):
                return _apply_naming(candidate)

        source_ctx = data.get("source_context") or data.get("search") or data.get("find")
        if isinstance(source_ctx, str) and source_ctx.strip() and source_ctx.strip() in base:
            candidate = base.replace(source_ctx.strip(), patch_str, 1)
            if re.search(r"\bmodule\b", candidate) and re.search(r"\bendmodule\b", candidate):
                return _apply_naming(candidate)
        return None

    # 1. Structured WriteFileAction schema (both modes; content used verbatim).
    try:
        action_obj = agent_action_adapter.validate_json(cleaned)
        if isinstance(action_obj, WriteFileAction):
            return _apply_naming(action_obj.content)
    except Exception:
        action_obj = None

    # 2. Markdown code fences for non-JSON-dict responses (both modes; verbatim).
    fence_match = _FENCE_REGEX.search(raw_output)
    if fence_match and not (cleaned.startswith("{") and cleaned.endswith("}")):
        fenced = fence_match.group(1).strip()
        if "module" in fenced and "endmodule" in fenced:
            return _apply_naming(fenced)

    if parser_mode == "strict":
        # 3. Repair-loop patch objects, only when the caller supplies base_code.
        if base_code:
            try:
                strict_parsed = json.loads(cleaned)
            except Exception:
                strict_parsed = None
            if isinstance(strict_parsed, dict):
                patched = _apply_repair_patch(strict_parsed, base_code)
                if patched is not None:
                    return patched
        # 4. Raw module verbatim: the entire response must be exactly one
        #    module block (leading comments/headers allowed, nothing else).
        full_match = _MODULE_REGEX.fullmatch(cleaned.strip())
        if full_match:
            return _apply_naming(full_match.group(1).strip())
        raise ModelResponseParseError(
            "Strict parsing rejected the model response: it is not a WriteFileAction, "
            "a fenced Verilog block, a repair patch, or exactly one Verilog module."
        )

    # LENIENT mode: bounded recovery for local-model formatting deviations.
    # 3. JSON-dict recovery limited to documented shapes. Arbitrary keys are
    #    never scanned.
    try:
        parsed_json = json.loads(cleaned)
    except Exception:
        parsed_json = None
    if isinstance(parsed_json, dict):
        # 3a. Documented structural AST shapes (module/pinout/implementation).
        ast_result = _reconstruct_from_ast(parsed_json)
        if ast_result is not None:
            return _apply_naming(ast_result)

        # 3b. Documented known keys only.
        for key in LENIENT_KNOWN_KEYS:
            val = parsed_json.get(key)
            if isinstance(val, str) and "module" in val and "endmodule" in val:
                val = _unescape(val)
                sub_fence = _FENCE_REGEX.search(val)
                if sub_fence:
                    return _apply_naming(_unescape(sub_fence.group(1).strip()))
                return _apply_naming(val.strip())

        # 3c. Repair-loop patch objects, only when the caller supplies base_code.
        if base_code:
            patched = _apply_repair_patch(parsed_json, base_code)
            if patched is not None:
                return patched

        # A JSON object that matches no documented shape is rejected here.
        # Free-text extraction below must never inspect arbitrary JSON values.
        raise ModelResponseParseError(
            "Lenient parsing rejected the JSON response: it matches no documented "
            "recovery shape (WriteFileAction, structural AST, documented known key, "
            "or repair patch)."
        )

    # 4. Raw SystemVerilog passthrough: begins with a comment/header/module and
    #    contains a complete module block. Returned verbatim.
    raw_search = _MODULE_REGEX.search(cleaned)
    if re.match(r"\s*(?:/\*|//|module\b)", cleaned, flags=re.I) and raw_search:
        return _apply_naming(raw_search.group(1).strip())

    # 5. Fence fallback when the JSON-dict branch matched nothing.
    if fence_match:
        fenced = fence_match.group(1).strip()
        if "module" in fenced and "endmodule" in fenced:
            return _apply_naming(fenced)

    # 6. First module-to-endmodule block, verbatim.
    mod_match = _MODULE_REGEX.search(raw_output)
    if mod_match:
        return _apply_naming(mod_match.group(1).strip())

    # 7. Fail closed.
    raise ModelResponseParseError("Failed to extract valid synthesizable SystemVerilog module from model response")


NON_REPAIRABLE_CATEGORIES: set[str] = {
    "EDA_BINARY_MISSING",
    "TIMING_REPORT_UNPARSEABLE",
    "MISSING_SOURCE_FILES",
    "MISSING_NETLIST_FOR_PNR",
    "MISSING_LIBERTY_FOR_PNR",
    "CDC_ANALYSIS_FAILED",
    "CDC_TOOLING_UNAVAILABLE",
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
        sandbox: BubblewrapSandbox | MacOSSandbox | None = None,
        transcript_path: Path | None = None,
        skills_dir: Path | str | None = None,
        model: str = "qwen2.5-coder:7b",
        provider: str = "ollama",
        api_key: str | None = None,
        base_url: str | None = None,
        loopback_only: bool = False,
        air_gapped: bool | None = None,
        parser_mode: str = "strict",
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
            loopback_only: When True, enforces loopback-only inference endpoint enforcement (127.0.0.1 or localhost) and forbids cloud LLM providers.
            air_gapped: Alias for loopback_only.
            parser_mode: Model-response parser mode, exactly "strict" (default) or
                "lenient". Lenient recovery must be explicitly opted in here; it is
                never inferred from provider, model name, failure count,
                environment, or hostname.
        """
        if parser_mode not in ("strict", "lenient"):
            raise ValueError(
                f"Unknown parser_mode {parser_mode!r}. Expected 'strict' or 'lenient'."
            )
        self.parser_mode: str = parser_mode
        self.session_id: str = session_id
        self.workspace: Path = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.verifier: BaseVerifier = verifier
        self.max_repairs: int = max_repairs
        self.ollama_url: str = ollama_url.rstrip("/")
        self.model: str = model
        resolved_loopback_only = air_gapped if air_gapped is not None else loopback_only
        self.loopback_only: bool = resolved_loopback_only
        self.air_gapped: bool = resolved_loopback_only

        self.provider: str = provider.lower()
        if self.provider not in {"ollama", "openrouter"}:
            raise ValueError(f"Unsupported provider '{provider}'. Must be 'ollama' or 'openrouter'.")

        if self.loopback_only and self.provider == "openrouter":
            raise ValueError(
                "Loopback-only endpoint violation (air-gapped): external cloud provider 'openrouter' is forbidden when loopback_only=True. "
                "Use local inference engine ('ollama') with localhost/loopback address."
            )

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

        if self.loopback_only:
            base_lower = self.base_url.lower()
            if not ("127.0.0.1" in base_lower or "localhost" in base_lower or "::1" in base_lower):
                raise ValueError(
                    f"Loopback-only endpoint violation (air-gapped): endpoint '{self.base_url}' is not a local loopback interface. "
                    "Loopback-only inference endpoint enforcement requires 127.0.0.1 or localhost."
                )

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
        self.total_repair_calls: int = 0
        self.last_verification_result: Any | None = None
        # Initialize benchmark/accounting state at construction time so baseline
        # and exceptional paths can safely read it before the silicon pipeline
        # has started.  run_silicon_pipeline() resets these values per task.
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.model_usage_known: bool = False
        self.model_cost_usd: float = 0.0
        self.model_cost_known: bool = False
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

        self.sandbox = sandbox if sandbox is not None else get_local_sandbox(self.workspace)
        timeout_env = os.environ.get("MIND3_HTTP_TIMEOUT")
        http_timeout = float(timeout_env) if timeout_env else 300.0
        self.client: httpx.Client = httpx.Client(timeout=http_timeout)

    def close(self) -> None:
        """Close the underlying HTTP client resources."""
        self.client.close()

    def __enter__(self) -> PhaseDriver:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ── Trace & Canonical Hashing (Invariant 4) ──────────────────────────

    def _emit_trace(self, phase: PhaseEnum, payload: dict[str, Any]) -> TraceRecord:
        """Construct, hash, and persist a hash-chained, tamper-evident trace record to transcript.jsonl."""
        if self.loopback_only:
            attestation_content = f"{self.session_id}|{self.turn}|{self.step_index}|LOOPBACK_ONLY_NO_EGRESS|{self.prev_hash}"
            attestation_hash = hashlib.sha256(attestation_content.encode("utf-8")).hexdigest()
            payload["loopback_attestation"] = attestation_hash
            payload["air_gapped_attestation"] = attestation_hash  # Backwards compatibility alias

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

    def _query_ollama(self, messages: list[dict[str, str]], *, response_format: str = "json") -> str:
        """Invoke Ollama API, constraining to JSON only when the caller needs it.

        RTL generation and repair prompts require the textual representation
        already expected by the strict parser (fenced/single-module Verilog),
        so those callers use ``response_format="text"`` to omit the
        ``"format": "json"`` constraint. Contract synthesis and the agent
        action loop keep the default: their parsers consume JSON.
        """
        endpoint = f"{self.ollama_url}/api/chat"
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if response_format == "json":
            payload["format"] = "json"
        response = self.client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        message = data.get("message", {})
        raw_content = str(message.get("content", "")).strip()
        usage = data.get("prompt_eval_count"), data.get("eval_count")
        if all(isinstance(v, int) for v in usage):
            self._record_model_usage(int(usage[0]), int(usage[1]))
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

        usage = data.get("usage", {})
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
                self._record_model_usage(prompt_tokens, completion_tokens)
        return _sanitize_json_output(raw_content)

    def _record_model_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.total_prompt_tokens += max(0, prompt_tokens)
        self.total_completion_tokens += max(0, completion_tokens)
        self.model_usage_known = True
        in_rate = os.getenv("MIND_COST_PER_MILLION_INPUT_USD")
        out_rate = os.getenv("MIND_COST_PER_MILLION_OUTPUT_USD")
        try:
            if in_rate is None or out_rate is None:
                return
            self.model_cost_usd += (prompt_tokens / 1_000_000.0) * float(in_rate)
            self.model_cost_usd += (completion_tokens / 1_000_000.0) * float(out_rate)
            self.model_cost_known = True
        except ValueError:
            self.model_cost_known = False

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def _query_model(
        self,
        prompt_or_messages: str | list[dict[str, str]],
        system_instruction: str | None = None,
        *,
        response_format: str = "json",
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
            if response_format == "json":
                return self._query_ollama(messages)
            return self._query_ollama(messages, response_format=response_format)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    # ── Policy Enforcement (Invariant 2) ─────────────────────────────────

    def _policy_check(self, action: AgentAction) -> None:
        """Enforce canonical path resolution and sandbox policy boundaries."""
        if action.action == "write_file":
            if "\x00" in action.path:
                raise ValueError("Security violation: null bytes in path are forbidden.")
            resolved_ws = self.workspace.resolve()
            target_path = (self.workspace / action.path).resolve()

            if (
                not target_path.is_relative_to(resolved_ws)
                or os.path.commonpath([str(resolved_ws), str(target_path)]) != str(resolved_ws)
            ):
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
            # POSIX file hygiene, not RTL rewriting: a missing trailing newline
            # makes Verilator -Wall fail the coverage build (EOFNEWLINE) on
            # otherwise valid output. Appending one byte has no Verilog semantics.
            content = action.content if action.content.endswith("\n") else action.content + "\n"
            target_path.write_text(content, encoding="utf-8")
            return {
                "operation": "write_file",
                "path": str(target_path.relative_to(self.workspace.resolve())),
                "bytes_written": len(content.encode("utf-8")),
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
                    "GATE 2 SIGN-OFF FAILURE: Formal invariant (typed bounded-property template) breached in SymbiYosys BMC.\n"
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

        # Unreachable with the default repair budget, but required by the
        # declared ``-> bool`` contract when the repair loop never executes.
        return False

    def run_silicon_pipeline(
        self,
        task_prompt: str,
        liberty_path: str | list[str] | None = None,
        contract_override: InterfaceContract | None = None,
    ) -> bool:
        """Run contract-first RTL generation with independent, stage-bounded verification repair.

        ``contract_override`` is the benchmark/evaluator path: the immutable contract is built
        from structured benchmark metadata and is never reinterpreted by the model.
        """
        self.turn = 0
        self.total_repair_calls = 0
        self._stage_repair_attempts: dict[str, int] = {"compile": 0, "simulation": 0, "formal": 0, "timing": 0, "other": 0}
        self.last_verification_result = None
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.model_usage_known = False
        self.model_cost_usd = 0.0
        self.model_cost_known = False

        self._emit_trace(
            PhaseEnum.INTAKE,
            {"task_prompt": task_prompt, "workspace": str(self.workspace), "pipeline": "silicon_multi_agent_pipeline"},
        )
        self._emit_trace(
            PhaseEnum.ROUTE,
            {
                "domain": "RTL",
                "verifier": "SiliconSignoffVerifier",
                "max_repairs": self.max_repairs,
                "stage_repair_limits": {"compile": 3, "simulation": 3, "formal": 3},
                "pipeline": "contract_first_compile_first",
            },
        )
        copied_items = self._create_snapshot()
        self._emit_trace(
            PhaseEnum.SNAPSHOT,
            {"snapshot_path": str(self.snapshot_dir), "items_captured": copied_items},
        )

        # Contract stage. Benchmarks use immutable structured metadata; general requests retain
        # the existing architect model but the resulting contract is persisted and enforced.
        if contract_override is not None:
            contract = contract_override
            self._emit_trace(
                PhaseEnum.PARSE,
                {
                    "role": "Lead Silicon Architect",
                    "source": "immutable_benchmark_contract",
                    "module_name": contract.module_name,
                    "ports": len(contract.ports),
                    "contract": contract.model_dump(mode="json"),
                },
            )
        else:
            contract_prompt = ContractSynthesizer.build_prompt(task_prompt)
            self._emit_trace(PhaseEnum.MODEL_CALL, {"role": "Lead Silicon Architect", "stage": "contract_synthesis"})
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
                    {
                        "role": "Lead Silicon Architect",
                        "module_name": contract.module_name,
                        "ports": len(contract.ports),
                        "contract": contract.model_dump(mode="json"),
                    },
                )
            except Exception as exc:
                self._emit_trace(PhaseEnum.PARSE, {"error": f"Architect contract synthesis failed: {exc}"})
                self._restore_snapshot()
                return False

        contract_violations = validate_contract_consistency(contract)
        if contract_violations:
            self._emit_trace(
                PhaseEnum.VERIFY,
                {
                    "passed": False,
                    "domain": "RTL",
                    "exit_code": 1,
                    "failure_reason": "Immutable contract is internally inconsistent.",
                    "error_category": "SPECIFICATION_ERROR",
                    "diagnostic": {
                        "stage": "contract",
                        "tool": "deterministic_contract_validator",
                        "error": "\n".join(v.get("message", "") for v in contract_violations),
                        "source_context": "",
                        "violations": contract_violations,
                    },
                },
            )
            self._restore_snapshot()
            self._emit_trace(
                PhaseEnum.REPAIR_OR_FINISH,
                {
                    "status": "ABORTED_NON_REPAIRABLE",
                    "error_category": "SPECIFICATION_ERROR",
                    "contract_violations": contract_violations,
                },
            )
            return False

        # Verification artifacts are derived only from the immutable contract.
        try:
            sva_bind_content = VerificationHarnessGenerator.build_sva_bind_module(contract)
        except (UnsupportedFormalPropertyError, UnsupportedFormalTemplate) as exc:
            sva_bind_content = (
                f"// Formal property construct unsupported by toolchain\n"
                f"// unsupported: {exc}\n"
                f"module {contract.module_name}_sva;\n"
                f"  UNSUPPORTED_FORMAL_PROPERTY_ERROR;\n"
                f"endmodule\n"
            )
        sby_content = VerificationHarnessGenerator.build_sby_config(
            contract, depth=25, include_sva_file=bool(contract.formal_properties or contract.sva_properties)
        )
        wrapper_content = VerificationHarnessGenerator.build_formal_wrapper(contract)
        cpp_tb_content = VerificationHarnessGenerator.build_verilator_cpp_testbench(contract)
        sdc_content = contract.timing.to_sdc()
        harness_files = [
            WriteFileAction(path=f"{contract.module_name}_sva.sv", content=sva_bind_content),
            WriteFileAction(path=f"{contract.module_name}.sby", content=sby_content),
            WriteFileAction(path=f"{contract.module_name}_formal_top.sv", content=wrapper_content),
            WriteFileAction(path=f"{contract.module_name}_tb.cpp", content=cpp_tb_content),
            WriteFileAction(path=f"{contract.module_name}.sdc", content=sdc_content),
        ]
        batch_harness_action = WriteBatchFilesAction(files=harness_files)
        self._policy_check(batch_harness_action)
        exec_harness = self._execute_action(batch_harness_action)
        self._emit_trace(PhaseEnum.EXECUTE, {"role": "Verification Lead", "staged_artifacts": exec_harness})

        rtl_prompt = RTLGenerator.build_prompt(contract)
        repair_system_instruction = VerificationRepairer.build_prompt(
            contract,
            "",
            VerificationFailureEvidence(
                gate="generation", category="generation", stage="compile", tool="model", error="initial generation"
            ),
        )["system"]

        self._emit_trace(
            PhaseEnum.MODEL_CALL,
            {"role": "Principal RTL Design Engineer", "module": contract.module_name, "stage": "rtl_generation", "parser_mode": self.parser_mode},
        )
        rtl_messages = self._build_prompt_messages(system_instruction=rtl_prompt["system"], task_prompt=rtl_prompt["user"])
        try:
            raw_rtl = self._query_model(rtl_messages, response_format="text")
            rtl_code = _parse_model_code_response(raw_rtl, default_module_name=contract.module_name, parser_mode=self.parser_mode)
            rtl_action = WriteFileAction(path=f"{contract.module_name}.sv", content=rtl_code)
            self._policy_check(rtl_action)
            exec_rtl = self._execute_action(rtl_action)
            self._emit_trace(
                PhaseEnum.EXECUTE,
                {"role": "Principal RTL Design Engineer", "rtl_file": exec_rtl, "content": rtl_code},
            )
        except (ModelResponseParseError, Exception) as exc:
            # Treat malformed generation or invocation error as a bounded compile-stage repair opportunity.
            evidence = VerificationFailureEvidence(
                gate="RTL generation/parser",
                category="SYNTAX_ERROR",
                stage="compile",
                tool="model-response-parser",
                error=str(exc),
                details="The model did not return a parseable synthesizable module.",
                contract=contract.model_dump(mode="json"),
                attempt=1,
            )
            repair_messages = VerificationRepairer.build_prompt(contract, "", evidence)
            repair_guidance = repair_messages["user"]
            repair_system_instruction = repair_messages["system"]
            rtl_code = ""
            self._emit_trace(
                PhaseEnum.VERIFY,
                {
                    "passed": False,
                    "domain": "RTL",
                    "exit_code": 1,
                    "failure_reason": str(exc),
                    "error_category": "RESPONSE_PARSE_FAILURE",
                    "gate": "RTL generation/parser",
                    "parser_mode": self.parser_mode,
                    "diagnostic": evidence.model_dump(mode="json"),
                },
            )

        if isinstance(self.verifier, SiliconSignoffVerifier):
            signoff_verifier = self.verifier
            signoff_verifier.top_module = contract.module_name
            signoff_verifier.contract = contract
            if liberty_path is not None:
                signoff_verifier.liberty_paths = (
                    [str(liberty_path)] if isinstance(liberty_path, (str, Path)) else [str(x) for x in liberty_path]
                )
        else:
            signoff_verifier = SiliconSignoffVerifier(
                top_module=contract.module_name,
                contract=contract,
                liberty_path=liberty_path or getattr(self.verifier, "liberty_paths", None),
                allow_mock_fallback=False,
            )

        repair_guidance: str | None = locals().get("repair_guidance")
        repair_history: list[str] = []
        current_rtl_path = self.workspace / f"{contract.module_name}.sv"
        current_rtl = current_rtl_path.read_text(encoding="utf-8") if current_rtl_path.exists() else ""
        stage_limits = {"compile": 3, "simulation": 3, "formal": 3, "timing": self.max_repairs, "other": self.max_repairs}
        initial_failure = repair_guidance is not None

        while True:
            # If a previous generation/repair response failed parsing, verify can still proceed
            # once a repair produces actual RTL. Otherwise run the independent verifier now.
            if repair_guidance is not None:
                current_rtl_path = self.workspace / f"{contract.module_name}.sv"
                current_rtl = current_rtl_path.read_text(encoding="utf-8") if current_rtl_path.exists() else ""
                stage_key = "compile"
                self._stage_repair_attempts[stage_key] += 1
                attempt = self._stage_repair_attempts[stage_key]
                if attempt > stage_limits[stage_key]:
                    self._restore_snapshot()
                    self._emit_trace(
                        PhaseEnum.REPAIR_OR_FINISH,
                        {"status": "ROLLED_BACK", "reason": f"compile repair limit ({stage_limits[stage_key]}) exhausted."},
                    )
                    return False
                self.turn += 1
                self.total_repair_calls += 1
                self._emit_trace(
                    PhaseEnum.MODEL_CALL,
                    {"role": "Independent RTL Verification Repair Engineer", "turn": self.turn, "stage": stage_key, "attempt": attempt, "guidance": repair_guidance, "parser_mode": self.parser_mode},
                )
                repair_messages = self._build_prompt_messages(
                    system_instruction=repair_system_instruction,
                    task_prompt=repair_guidance,
                )
                try:
                    raw_repair = self._query_model(repair_messages, response_format="text")
                    repaired_code = _parse_model_code_response(raw_repair, default_module_name=contract.module_name, base_code=current_rtl, parser_mode=self.parser_mode)
                    diff_stats = _repair_diff_stats(current_rtl, repaired_code) if current_rtl else {"changed_line_ratio": 0.0, "line_growth_ratio": 1.0}
                    if current_rtl and len(current_rtl.splitlines()) >= 12 and (
                        diff_stats["changed_line_ratio"] > REPAIR_MAX_CHANGED_LINE_RATIO
                        or diff_stats["line_growth_ratio"] > REPAIR_MAX_LINE_GROWTH
                    ):
                        repair_history.append("REPAIR_PATCH_TOO_LARGE")
                        repair_guidance = (
                            f"Your last repair was rejected because it exceeded the bounded change budget. "
                            f"Keep changed lines <= {REPAIR_MAX_CHANGED_LINE_RATIO:.0%} of current RTL and growth <= {REPAIR_MAX_LINE_GROWTH:.1f}x."
                        )
                        self._emit_trace(
                            PhaseEnum.VERIFY,
                            {
                                "passed": False,
                                "domain": "RTL",
                                "exit_code": 1,
                                "failure_reason": "Repair patch exceeded bounded change budget.",
                                "error_category": "REPAIR_PATCH_TOO_LARGE",
                                "diff_stats": diff_stats,
                                "gate_reports": [],
                            },
                        )
                        continue
                    rep_action = WriteFileAction(path=f"{contract.module_name}.sv", content=repaired_code)
                    self._policy_check(rep_action)
                    exec_rep = self._execute_action(rep_action)
                    self._emit_trace(
                        PhaseEnum.EXECUTE,
                        {"role": "Independent RTL Verification Repair Engineer", "rtl_file": exec_rep, "content": repaired_code, "diff_stats": diff_stats, "attempt": attempt},
                    )
                    repair_guidance = None
                except ModelResponseParseError as exc:
                    repair_history.append("RESPONSE_PARSE_FAILURE")
                    self._emit_trace(
                        PhaseEnum.VERIFY,
                        {
                            "passed": False,
                            "domain": "RTL",
                            "exit_code": 1,
                            "failure_reason": str(exc),
                            "error_category": "RESPONSE_PARSE_FAILURE",
                            "gate": "RTL repair/parser",
                            "parser_mode": self.parser_mode,
                        },
                    )
                    repair_guidance = (
                        f"The previous repair response could not be parsed: {exc}.\n"
                        "Return ONLY the complete SystemVerilog module, including its module declaration and endmodule."
                    )
                    continue
                except Exception as exc:
                    repair_history.append("REPAIR_CALL_FAILURE")
                    repair_guidance = f"Repair model invocation failed: {exc}. Return the complete SystemVerilog module only."
                    continue

            v_result: VerificationResult = signoff_verifier.verify(self.workspace, self.sandbox)
            self.last_verification_result = v_result
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
            if v_result.passed:
                self._purge_snapshot()
                status_label = "SILICON_VERIFIED" if v_result.silicon_verified else "VERIFIED_SUCCESS"
                self._emit_trace(
                    PhaseEnum.REPAIR_OR_FINISH,
                    {"status": status_label, "turns_taken": self.turn + 1, "silicon_verified": v_result.silicon_verified, "gate_reports": v_result.gate_reports, "netlist_path": v_result.netlist_path},
                )
                self._emit_trace(PhaseEnum.TRACE, {"final_status": status_label, "total_steps": self.step_index, "session_id": self.session_id})
                return True

            last_report = v_result.gate_reports[-1] if v_result.gate_reports else {}
            category = v_result.error_category or "UNKNOWN_ERROR"
            lower_category = category.lower()
            if category in NON_REPAIRABLE_CATEGORIES or category in {"SPECIFICATION_ERROR", "ENVIRONMENT_FAILURE"}:
                self._restore_snapshot()
                self._emit_trace(PhaseEnum.REPAIR_OR_FINISH, {"status": "ABORTED_NON_REPAIRABLE", "error_category": category})
                return False

            if category in {"SYNTAX_ERROR", "INTERFACE_ERROR", "TYPE_WIDTH_ERROR", "CLOCK_RESET_ERROR", "LATCH_INFERRED", "COMBINATIONAL_LOOP", "RTL_SYNTAX_ERROR", "RTL_SEMANTIC_ERROR", "RESPONSE_PARSE_FAILURE", "EDA_BINARY_MISSING"}:
                stage_key = "compile"
            elif category.startswith("SIMULATION") or category.startswith("COVERAGE") or category in {"MISSING_VERIFICATION_ARTIFACT"} and "Gate 3" in str(last_report.get("gate", "")):
                stage_key = "simulation"
            elif "FORMAL" in category or category in {"UNSUPPORTED_FORMAL_PROPERTY", "EMPTY_FORMAL_PROPERTY_SET"}:
                stage_key = "formal"
            elif "TIMING" in category:
                stage_key = "timing"
            else:
                stage_key = "other"
            repair_count = self._stage_repair_attempts.get(stage_key, 0)
            if repair_count >= stage_limits.get(stage_key, self.max_repairs):
                self._restore_snapshot()
                self._emit_trace(
                    PhaseEnum.REPAIR_OR_FINISH,
                    {"status": "ROLLED_BACK", "reason": f"{stage_key} repair limit ({stage_limits.get(stage_key, self.max_repairs)}) exhausted.", "failure_category": category},
                )
                return False

            diagnostic = last_report.get("diagnostic", {}) if isinstance(last_report, dict) else {}
            compile_diag = diagnostic if isinstance(diagnostic, dict) else {}
            file_name = compile_diag.get("file")
            line = compile_diag.get("line")
            column = compile_diag.get("column")
            source_context = compile_diag.get("source_context", "")
            property_source = None
            if last_report.get("failing_property"):
                prop_name = str(last_report.get("failing_property"))
                for prop in [*contract.formal_properties, *contract.sva_properties]:
                    pname = getattr(prop, "name", "")
                    if pname == prop_name or prop_name in pname:
                        property_source = getattr(prop, "expression", None) or getattr(prop, "property_expr", None)
                        break
            evidence = VerificationFailureEvidence(
                gate=str(last_report.get("gate", "verification gate")),
                category=category,
                stage=stage_key,
                tool=str(last_report.get("compile_tool") or diagnostic.get("tool") or ("sby" if stage_key == "formal" else "verilator" if stage_key == "simulation" else "")),
                error=str(last_report.get("details") or v_result.failure_reason or "verification failed"),
                file=str(file_name) if file_name else None,
                line=int(line) if isinstance(line, int) else (int(line) if isinstance(line, str) and line.isdigit() else None),
                column=int(column) if isinstance(column, int) else (int(column) if isinstance(column, str) and column.isdigit() else None),
                source_context=str(source_context or ""),
                stdout_tail=(v_result.stdout or "")[-4000:],
                stderr_tail=(v_result.stderr or "")[-4000:],
                failing_property=str(last_report.get("failing_property")) if last_report.get("failing_property") else None,
                failing_step=str(last_report.get("step")) if last_report.get("step") is not None else None,
                trace_file=str(last_report.get("trace_file")) if last_report.get("trace_file") else None,
                metrics={k: v for k, v in {**v_result.timing_metrics, **v_result.hold_metrics}.items() if isinstance(v, (int, float))},
                artifact_paths=[str(p) for p in [v_result.netlist_path, last_report.get("trace_file")] if p],
                contract=contract.model_dump(mode="json"),
                attempt=repair_count + 1,
                failing_test=str(last_report.get("failing_test")) if last_report.get("failing_test") else None,
                cycle=int(cycle_v) if isinstance((cycle_v := last_report.get("cycle")), int) else None,
                expected_behavior=str(last_report.get("expected_behavior")) if last_report.get("expected_behavior") else None,
                observed_behavior=str(last_report.get("observed_behavior")) if last_report.get("observed_behavior") else None,
                relevant_signals={k: v for k, v in last_report.get("relevant_signals", {}).items() if isinstance(k, str)} if isinstance(last_report.get("relevant_signals"), dict) else {},
                reset_state=str(last_report.get("reset_state")) if last_report.get("reset_state") else None,
                clock_state=str(last_report.get("clock_state")) if last_report.get("clock_state") else None,
                property_source=property_source,
                counterexample_trace=str(last_report.get("counterexample_trace")) if last_report.get("counterexample_trace") else None,
                repair_history=repair_history[-3:],
            )
            repair_prompt = VerificationRepairer.build_prompt(contract, current_rtl, evidence)
            repair_system_instruction = repair_prompt["system"]
            repair_guidance = repair_prompt["user"]
            repair_history.append(category)


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
    "ParserMode",
    "LENIENT_KNOWN_KEYS",
    "_parse_model_code_response",
    "ModelResponseParseError",
    "OpenRouterModelRegistry",
    "OpenRouterModelRegistryError",
    "fetch_openrouter_free_models",
    "PPAPoint",
    "PPAOptimizer",
]
