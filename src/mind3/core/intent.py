"""Intent gate: GENERAL (answer directly) vs GENERATE (full RTL pipeline).

Fail-safe default is GENERATE: ambiguous input always takes the gated path
so unverified RTL is never delivered as an answer. This module is stdlib-only
so chat frontends can reuse the keyword gate without importing the driver.
"""

from __future__ import annotations

import re
from typing import Any, Callable

GENERAL = "GENERAL"
GENERATE = "GENERATE"

_KEYWORDS = (
    "verilog",
    "systemverilog",
    "rtl",
    "testbench",
    "synthesis",
    "synthesize",
    "module",
    "endmodule",
    "always_ff",
    "always_comb",
    "fifo",
    "arbiter",
    "counter",
    "fsm",
    "uart",
    "spi",
    "axi",
    "apb",
)
# NOTE: tool names (yosys, verilator, sby, sta, openroad, cdc, formal) are
# deliberately absent: "what does WIDTHEXPAND mean" asks ABOUT a tool and must
# reach the classifier, not the pipeline. Design nouns above + action verbs
# are the GENERATE signal.
_VERBS = (
    "write",
    "generate",
    "create",
    "design",
    "build",
    "fix",
    "verify",
    "implement",
    "make",
)


def _word_re(word: str) -> str:
    return r"\b" + re.escape(word) + r"\b"


_KEYWORD_RES = [re.compile(_word_re(k), re.IGNORECASE) for k in _KEYWORDS]
_VERB_RES = [re.compile(_word_re(v), re.IGNORECASE) for v in _VERBS]

CLASSIFY_SYSTEM = (
    "Reply with exactly one word and nothing else: GENERAL or GENERATE. "
    "GENERAL means the request only asks for explanation, docs, or error interpretation, "
    "even when it mentions tools, latches, warnings, or code concepts. "
    "GENERATE means the request asks to write, repair, complete, or verify hardware RTL. "
    "Examples: 'Why does Yosys infer a latch from an if without else?' is GENERAL. "
    "'What does WIDTHEXPAND mean?' is GENERAL. "
    "'Write a FIFO in Verilog' is GENERATE. 'Fix my uart module' is GENERATE. "
    "When unsure, reply GENERATE."
)
# Tight decode: single-word answer, minimal latency.
CLASSIFY_OPTIONS: dict[str, Any] = {"temperature": 0.0, "num_predict": 8, "stop": ["\n", " "]}

# Boundary for direct answers: explain, never deliver synthesizable modules,
# never claim verification status.
ASK_BOUNDARY = (
    "Answer the question directly and concisely. "
    "Do not output a complete production synthesizable RTL module; short illustrative "
    "snippets under 10 lines are acceptable when explaining. "
    "If the user needs a full module, tell them to request module generation, which runs verification. "
    "Never claim verification status and never use the words SILICON_VERIFIED or VERIFIED_SUCCESS."
)

# Verdict tokens that must never appear in direct-answer output.
VERDICT_TOKENS = ("SILICON_VERIFIED", "VERIFIED_SUCCESS")


def keyword_hint(prompt: str) -> str | None:
    """Word-boundary keyword pre-filter. Returns GENERATE or None (no opinion).

    Both a hardware keyword and an action verb must match, so "modular
    design principles" stays GENERAL while "fix my verilog module" routes out.
    """
    text = prompt or ""
    if any(r.search(text) for r in _KEYWORD_RES) and any(r.search(text) for r in _VERB_RES):
        return GENERATE
    return None


def parse_intent(raw: str) -> str:
    """Aggressive single-word parse; anything but a clean GENERAL is GENERATE."""
    token = re.sub(r"[^a-zA-Z]", "", raw or "").upper()
    if token == GENERAL:
        return GENERAL
    return GENERATE


def route_intent(
    prompt: str,
    query_fn: Callable[[list[dict[str, str]], dict[str, Any]], str],
) -> str:
    """Single orchestration: keyword gate, then model classifier, then fallback.

    Every caller (PhaseDriver.classify_request, chat frontends) delegates here
    so routing logic exists exactly once. Never raises: any error, including a
    failed model call, falls back to GENERATE (the gated path).
    """
    try:
        if keyword_hint(prompt) == GENERATE:
            return GENERATE
        messages = [
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {"role": "user", "content": f"Request: {(prompt or '')[:2000]}"},
        ]
        return parse_intent(query_fn(messages, CLASSIFY_OPTIONS))
    except Exception:
        return GENERATE


def classify(
    prompt: str,
    query_fn: Callable[[list[dict[str, str]], dict[str, Any]], str],
) -> str:
    """Classify a user request. Kept for compatibility; delegates to route_intent."""
    return route_intent(prompt, query_fn)


def assert_no_verdict(text: str) -> None:
    """Fail-closed guard: direct answers must never carry verification verdicts."""
    for token in VERDICT_TOKENS:
        if token in (text or ""):
            raise ValueError("Direct answers must never emit verification verdicts.")
