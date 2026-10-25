"""R5 evidence decoder and repair guard (flag-gated, default OFF).

When Gate 2 fails with a VCD witness trace, the raw VCD ASCII text is too
large and too low-level to guide a repair model. This module deterministically
decodes the counterexample into a compact cycle-aligned Markdown table over
exactly the signals the failure can involve:

- all ports declared in the InterfaceContract, plus
- top-level DUT state/internal signals referenced by the failing property.

Nothing is invented: every cell quotes a VCD sample, every row maps to a
solver step, and out-of-scope signals are omitted rather than guessed.

A second, independent guard detects duplicate net drivers (continuous
``assign`` + procedural ``always_*`` on the same signal) in repair
candidates — the exact arbiter_02 failure mode — before an EDA turn is
spent on them.
"""

from __future__ import annotations

import os
import re
from typing import Any

#: Environment flag enabling R5 evidence decoding and the repair guard.
#: Anything else (including unset) keeps legacy behavior byte-identical.
EVIDENCE_V2_ON_VALUES = frozenset({"1", "true", "yes", "on"})

#: Cap on decoded table rows (most recent cycles ending at t_fail).
DECODE_MAX_CYCLES = 10

#: Cap on raw VCD text ingested for decoding (traces can be megabytes).
VCD_MAX_CHARS = 300_000

#: Cap on decoded Markdown placed into evidence (field limit is 6000).
DECODED_MAX_CHARS = 5900

_SV_KEYWORDS = frozenset(
    {
        "if",
        "else",
        "for",
        "while",
        "case",
        "endcase",
        "begin",
        "end",
        "assign",
        "always",
        "always_ff",
        "always_comb",
        "always_latch",
        "module",
        "endmodule",
        "input",
        "output",
        "inout",
        "wire",
        "reg",
        "logic",
        "int",
        "integer",
        "return",
    }
)


def evidence_v2_enabled() -> bool:
    """MIND3_EVIDENCE_V2 master flag for R5 (default OFF).

    Read at call time (never cached) so tests can toggle it per case.
    """
    return os.environ.get("MIND3_EVIDENCE_V2", "").strip().lower() in EVIDENCE_V2_ON_VALUES


def parse_vcd(text: str) -> dict[str, Any]:
    """Parse VCD text into signal definitions and ordered solver steps.

    Returns {"signals": {id: {"width", "scope", "name"}}, "steps":
    [{"step": int|None, "time": int, "values": {id: str}}]}. Steps follow the
    ``smt_step`` counter when present (one row per solver cycle), otherwise
    one row per timestep. Malformed input yields empty steps, never an
    exception.
    """
    signals: dict[str, dict[str, Any]] = {}
    raw_steps: list[dict[str, Any]] = []
    scope: list[str] = []
    current: dict[str, str] = {}
    current_time = 0
    in_definitions = True

    def flush() -> None:
        if current:
            raw_steps.append({"time": current_time, "values": dict(current)})
            current.clear()

    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("$scope"):
            parts = stripped.split()
            if len(parts) >= 3:
                scope.append(parts[2])
            in_definitions = True
            continue
        if stripped.startswith("$upscope"):
            if scope:
                scope.pop()
            continue
        if stripped.startswith("$var"):
            parts = stripped.split()
            # $var <type> <width> <idcode> <reference> [$end]
            if len(parts) >= 5:
                try:
                    width = int(parts[2])
                except ValueError:
                    width = 1
                signals[parts[3]] = {
                    "width": width,
                    "scope": ".".join(scope),
                    "name": parts[4],
                }
            continue
        if stripped.startswith("$enddefinitions"):
            in_definitions = False
            continue
        if in_definitions:
            continue
        if stripped.startswith("#"):
            flush()
            try:
                current_time = int(stripped[1:])
            except ValueError:
                continue
            continue
        if stripped.startswith("b"):
            body = stripped[1:].split()
            if len(body) == 2:
                current[body[1]] = body[0]
            continue
        if len(stripped) >= 2 and stripped[0] in ("0", "1", "x", "X", "z", "Z", "?"):
            current[stripped[1:]] = stripped[0]
            continue
    flush()
    # Group snapshots by the smt_step counter when the trace carries one.
    step_ids = [sid for sid, meta in signals.items() if meta["name"] == "smt_step"]
    steps: list[dict[str, Any]] = []
    if step_ids:
        sid = step_ids[0]
        current_step: int | None = None
        acc: dict[str, str] = {}
        for snap in raw_steps:
            raw = snap["values"].get(sid)
            try:
                num = int(raw, 2) if isinstance(raw, str) and set(raw) <= set("01") else None
            except ValueError:
                num = None
            if num is not None and num != current_step:
                if acc or current_step is not None:
                    steps.append(
                        {"step": current_step, "time": snap["time"], "values": dict(acc)}
                    )
                current_step = num
                acc = {}
            acc.update(snap["values"])
        steps.append({"step": current_step, "time": raw_steps[-1]["time"] if raw_steps else 0, "values": dict(acc)})
        # Drop a leading empty pre-step row when the counter was already set.
        steps = [s for s in steps if s["values"]]
    else:
        steps = [
            {"step": idx, "time": snap["time"], "values": snap["values"]}
            for idx, snap in enumerate(raw_steps)
        ]
    return {"signals": signals, "steps": steps}


def _preferred_scope_ids(
    signals: dict[str, dict[str, Any]], wanted: list[str]
) -> dict[str, str]:
    """Map wanted signal names to VCD ids, preferring DUT scope.

    Later scopes win on ties unless an earlier id lives under a `.dut.`
    path segment; exact reference match only (no guessing).
    """
    chosen: dict[str, str] = {}
    for want in wanted:
        candidates = [
            (sid, meta)
            for sid, meta in signals.items()
            if meta["name"] == want
        ]
        if not candidates:
            continue
        dut_hits = [sid for sid, meta in candidates if ".dut." in f".{meta['scope']}."]
        chosen[want] = dut_hits[0] if dut_hits else candidates[0][0]
    return chosen


def property_signal_names(property_text: str | None) -> list[str]:
    """Identifiers referenced by a failing property expression (ordered, deduped)."""
    if not property_text:
        return []
    names: list[str] = []
    for match in re.finditer(r"[A-Za-z_]\w*", property_text):
        word = match.group(0)
        if word not in _SV_KEYWORDS and word not in names:
            names.append(word)
    return names


def decode_counterexample(
    vcd_text: str,
    *,
    port_names: list[str],
    extra_names: list[str] | None = None,
    t_fail: int | None = None,
    clock_name: str = "clk",
    reset_name: str = "rst_n",
    reset_active_low: bool = True,
    max_cycles: int = DECODE_MAX_CYCLES,
    failing_assertion: str | None = None,
    source: str = "trace.vcd",
) -> dict[str, Any]:
    """Decode a VCD witness into a compact cycle-aligned Markdown table.

    Rows cover solver steps 0..t_fail (capped to the last ``max_cycles``
    when deep). Every cell quotes a VCD sample; reset cells are annotated
    asserted/released; the t_fail row names the violated assertion. Returns
    {"markdown", "rows", "signals", "t_fail", "truncated"} — never raises on
    malformed input (yields an explicit undecodable note instead).
    """
    parsed = parse_vcd(vcd_text[:VCD_MAX_CHARS])
    signals = parsed["signals"]
    steps = parsed["steps"]
    if not signals or not steps:
        return {
            "markdown": f"VCD undecodable: no signals or steps parsed from {source}.",
            "rows": [],
            "signals": [],
            "t_fail": t_fail,
            "truncated": False,
        }
    wanted: list[str] = []
    for name in list(port_names) + list(extra_names or []):
        if name not in wanted:
            wanted.append(name)
    if clock_name not in wanted:
        wanted.append(clock_name)
    if reset_name not in wanted:
        wanted.append(reset_name)
    chosen = _preferred_scope_ids(signals, wanted)
    ordered = [name for name in wanted if name in chosen]
    if t_fail is None:
        known = [s["step"] for s in steps if isinstance(s.get("step"), int)]
        t_fail = max(known) if known else len(steps) - 1
    window = [s for s in steps if isinstance(s.get("step"), int) and s["step"] <= t_fail]
    truncated = len(window) > max_cycles
    if truncated:
        window = window[-max_cycles:]
    if not window:
        window = steps[-max_cycles:]

    def fmt(name: str, value: str | None) -> str:
        if value is None:
            return "?"
        if name == reset_name:
            asserted = (value == "0") if reset_active_low else (value == "1")
            return f"{value} ({'asserted' if asserted else 'released'})"
        return value

    header = ["step", *ordered]
    lines = [
        f"Decoded counterexample from {source} (solver steps, signal values quoted from VCD).",
    ]
    if failing_assertion:
        lines.append(f"Violated assertion: {failing_assertion}.")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    rows: list[dict[str, Any]] = []
    for snap in window:
        step = snap.get("step")
        values = snap.get("values", {})
        row: dict[str, Any] = {"step": step}
        cells = [str(step)]
        for name in ordered:
            raw = values.get(chosen[name])
            row[name] = raw
            cells.append(fmt(name, raw))
        marker = ""
        if step == t_fail:
            marker = f" <-- t_fail{f': {failing_assertion}' if failing_assertion else ''}"
        lines.append("| " + " | ".join(cells) + " |" + marker)
        rows.append(row)
    markdown = "\n".join(lines)
    if len(markdown) > DECODED_MAX_CHARS:
        markdown = markdown[:DECODED_MAX_CHARS] + "\n…(truncated)"
        truncated = True
    return {
        "markdown": markdown,
        "rows": rows,
        "signals": ordered,
        "t_fail": t_fail,
        "truncated": truncated,
    }


def _strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", code)


def _block_spans(code: str) -> list[tuple[int, int]]:
    """Spans of procedural block bodies (always blocks to their end), nesting-aware."""
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"\balways(?:_ff|_comb|_latch)?\b", code):
        i = match.end()
        depth = 0
        begin_at: int | None = None
        while i < len(code):
            inner = re.match(r"\b(begin|end)\b", code[i:])
            if inner:
                if inner.group(1) == "begin":
                    if begin_at is None:
                        begin_at = i
                    depth += 1
                else:
                    depth -= 1
                    if depth == 0 and begin_at is not None:
                        spans.append((begin_at, i + inner.end()))
                        break
                i += inner.end()
                continue
            i += 1
    return spans


def detect_multidriven_nets(rtl_text: str) -> list[dict[str, Any]]:
    """Nets driven both continuously (`assign`) and procedurally (`always_*`).

    Returns [{"signal", "continuous": True, "procedural_blocks": n}] sorted
    by signal. Block-local temporaries and loop iterators are excluded, so
    only real multi-driver defects report. Pure function, no EDA.
    """
    clean = _strip_comments(rtl_text)
    continuous: set[str] = set()
    for match in re.finditer(r"\bassign\b(.*?);", clean, flags=re.DOTALL):
        lhs = match.group(1).split("=", 1)[0]
        for ident in re.finditer(r"[A-Za-z_]\w*", lhs):
            continuous.add(ident.group(0))
    procedural: dict[str, int] = {}
    for start, end in _block_spans(clean):
        body = clean[start:end]
        declared: set[str] = set()
        for decl in re.finditer(
            r"\b(?:logic|bit|reg|int|integer|byte|shortint|longint)\b([^;]*);", body
        ):
            declared.update(re.findall(r"[A-Za-z_]\w*", decl.group(1)))
        driven: set[str] = set()
        for assign in re.finditer(
            r"([A-Za-z_]\w*(?:\s*\[[^\[\];]*\])?)\s*(?:<=|=(?![=>]))", body
        ):
            base = re.match(r"[A-Za-z_]\w*", assign.group(1))
            if base and base.group(0) not in declared:
                driven.add(base.group(0))
        for name in driven:
            procedural[name] = procedural.get(name, 0) + 1
    return [
        {"signal": name, "continuous": True, "procedural_blocks": procedural[name]}
        for name in sorted(continuous & set(procedural))
    ]


def repair_guard_block() -> str:
    """System-prompt addition enforcing the single-driver repair discipline."""
    return (
        "EVIDENCE-V2 REPAIR GUARD (hard constraints):\n"
        "- When failure evidence with a decoded cycle table is present, base every "
        "claim about signal values, cycles, and reset state ONLY on that table.\n"
        "- Modify the existing always_ff / always_comb driver blocks IN PLACE. NEVER "
        "attach a continuous `assign` to a net already driven procedurally (or vice "
        "versa): one net, one driver kind. A second driver is a certain Gate-1 "
        "multidriven failure, not a repair.\n"
        "- Keep the diff minimal: preserve ports, parameters, and unrelated logic; "
        "change only the logic the decoded evidence implicates."
    )


def required_sensitivity_header(contract: Any) -> str:
    """Exact `always_ff` sensitivity header the contract requires.

    Synchronous reset: `always_ff @(posedge <clk>)` — reset tested inside.
    Asynchronous reset: `always_ff @(posedge <clk> or <edge> <rst>)`.
    Mirrors the Gate-1 structural validation defaults (clk/posedge) so the
    pre-check never disagrees with the gate on clockless contracts.
    """
    clock = getattr(contract, "clock", None)
    reset = getattr(contract, "reset", None)
    clock_name = getattr(clock, "name", None) or "clk"
    edge = getattr(clock, "edge", None) or "posedge"
    if reset is not None and not bool(getattr(reset, "synchronous", True)):
        reset_name = getattr(reset, "name", None) or "rst_n"
        reset_edge = (
            "negedge" if str(getattr(reset, "polarity", "active_low")) == "active_low"
            else "posedge"
        )
        return f"always_ff @({edge} {clock_name} or {reset_edge} {reset_name})"
    return f"always_ff @({edge} {clock_name})"


def sensitivity_mismatch(
    rtl_text: str, contract: Any
) -> dict[str, Any] | None:
    """Async/sync sensitivity mismatch against the contract (pure).

    Mirrors the Gate-1 structural validation regexes exactly so the
    pre-check never disagrees with the gate: sync contract + reset edge in
    a clocked sensitivity list, or async contract + missing reset edge.
    Returns None when compliant or inapplicable (no reset declared).
    Otherwise {"direction", "required", "detail"} with the exact required
    header for repair feedback.
    """
    reset = getattr(contract, "reset", None)
    if reset is None:
        return None
    reset_name = str(getattr(reset, "name", "") or "")
    if not reset_name:
        return None
    clock = getattr(contract, "clock", None)
    clock_name = getattr(clock, "name", None) or "clk"
    clean = _strip_comments(rtl_text)
    has_reset_edge = bool(
        re.search(
            rf"always(?:_ff)?\s*@\s*\(\s*(?:posedge|negedge)\s+{re.escape(clock_name)}\b"
            rf"[^)]*\bor\s+(?:negedge|posedge)\s+{re.escape(reset_name)}",
            clean,
        )
    )
    required = required_sensitivity_header(contract)
    if bool(getattr(reset, "synchronous", True)):
        if has_reset_edge:
            return {
                "direction": "async-in-sync",
                "required": required,
                "detail": (
                    f"Synchronous reset '{reset_name}' must not appear in the "
                    "clocked sensitivity list."
                ),
            }
        return None
    if clock is not None and not has_reset_edge:
        return {
            "direction": "sync-in-async",
            "required": required,
            "detail": (
                f"Asynchronous reset '{reset_name}' must be included in the "
                "clocked sensitivity list."
            ),
        }
    return None


def sensitivity_guard_block(contract: Any) -> str | None:
    """Prompt block stating the exact required sensitivity header (flag-gated).

    Returns None when the contract declares no clock (nothing to require).
    """
    if getattr(contract, "clock", None) is None:
        return None
    required = required_sensitivity_header(contract)
    reset = getattr(contract, "reset", None)
    if reset is not None and not bool(getattr(reset, "synchronous", True)):
        return (
            "REQUIRED SENSITIVITY (copy exactly):\n"
            f"- {required}\n"
            f"Asynchronous reset '{reset.name}' MUST appear in every clocked "
            "sensitivity list."
        )
    reset_name = getattr(reset, "name", "rst_n") if reset is not None else "rst_n"
    return (
        "REQUIRED SENSITIVITY (copy exactly):\n"
        f"- {required}\n"
        f"Forbidden: `or negedge {reset_name}` / `or posedge {reset_name}` (or any "
        "reset edge) in any sensitivity list — the contract reset is synchronous "
        "and must be tested INSIDE the block.\n"
        f"{required} is required WHEN sequential/registered state is used; it is "
        "NOT a mandate to register purely combinational outputs. Outputs that "
        "must respond in the same cycle drive combinationally via `assign` or "
        "`always_comb` (no `always_ff` needed for them)."
    )


def _identifiers(text: str) -> list[str]:
    """Ordered, deduplicated identifiers in a text fragment."""
    names: list[str] = []
    for match in re.finditer(r"[A-Za-z_]\w*", text):
        word = match.group(0)
        if word not in names:
            names.append(word)
    return names


def _output_driven_in_always_ff(candidate_rtl: str, output_name: str) -> bool:
    """True when an always_ff/posedge block assigns `output_name` with `<=`."""
    clean = _strip_comments(candidate_rtl)
    for start, end in _block_spans(clean):
        head = clean[max(0, start - 200):start]
        if not re.search(r"always_ff\b|always\s*@\s*\(\s*posedge\b", head):
            continue
        body = clean[start:end]
        for assign in re.finditer(
            r"([A-Za-z_]\w*(?:\s*\[[^\[\];]*\])?)\s*<=", body
        ):
            base = re.match(r"[A-Za-z_]\w*", assign.group(1))
            if base and base.group(0) == output_name:
                return True
    return False


def latency_hint_for_repair(
    contract: Any, candidate_rtl: str | None, property_source: str | None
) -> str | None:
    """Same-cycle `|->` vs `always_ff` latency hint (flag-gated, else None).

    Fires only when every fact is established: the mapped property uses
    overlapping same-cycle implication (`|->`, no `|=>`, no `$past`) from an
    input port to an output port, and the failed candidate drives that
    output inside `always_ff` (`<=`) — a structural 1-cycle delay against a
    0-cycle requirement. Anything else abstains (returns None), so flag-off
    behavior is byte-identical.
    """
    if not evidence_v2_enabled():
        return None
    if not property_source or not candidate_rtl:
        return None
    if "|=>" in property_source or "$past" in property_source:
        return None
    if property_source.count("|->") != 1:
        return None
    antecedent, _, consequent = property_source.partition("|->")
    input_ports = {
        str(getattr(p, "name", ""))
        for p in (getattr(contract, "ports", None) or [])
        if str(getattr(p, "direction", "")) == "PortDirection.INPUT"
        or "input" in str(getattr(p, "direction", "")).lower()
    }
    output_ports = {
        str(getattr(p, "name", ""))
        for p in (getattr(contract, "ports", None) or [])
        if "output" in str(getattr(p, "direction", "")).lower()
    }
    antecedent_names = set(_identifiers(antecedent))
    consequent_names = set(_identifiers(consequent))
    if not (antecedent_names & input_ports):
        return None
    driven_outputs = sorted(consequent_names & output_ports)
    if not driven_outputs:
        return None
    latched = [name for name in driven_outputs if _output_driven_in_always_ff(candidate_rtl, name)]
    if not latched:
        return None
    return (
        "TIMING LATENCY HINT: Violated property "
        f"'{property_source.strip()}' requires same-cycle (0-cycle combinational) "
        "response via '|->', but candidate RTL registers the output inside "
        "'always_ff' (causing a 1-cycle delay). Drive same-cycle outputs "
        "combinationally using 'always_comb' or 'assign' instead of 'always_ff'."
    )
