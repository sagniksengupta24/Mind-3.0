"""Deterministic, bounded formal-property templates for Mind 3.0.

The architect model selects a typed template and supplies only bounded expressions.
Mind 3.0 owns the SystemVerilog rendering. Legacy free-form SVA is accepted only
when a conservative classifier can map it without changing clock/reset semantics;
otherwise the property fails closed.
"""

from __future__ import annotations

from enum import StrEnum
import os
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FormalTemplateKind(StrEnum):
    BOOLEAN = "boolean"
    SAME_CYCLE_IMPLICATION = "same_cycle_implication"
    NEXT_CYCLE_IMPLICATION = "next_cycle_implication"
    RESET_ASSERTION = "reset_assertion"
    ONEHOT = "onehot"
    ONEHOT0 = "onehot0"
    ONEHOT_OR_EQUALS = "onehot_or_equals"
    PAST_EQUALS = "past_equals"
    PAST_STABLE = "past_stable"
    PAST_EXPRESSION = "past_expression"
    TAUTOLOGY = "tautology"


_SAFE_BOOL_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\s*\[[0-9]+(?::[0-9]+)?\])?"
    r"|(?:\d+'[bBoOdDhHxX][0-9a-fA-F_xXzZ]+)"
    r"|(?:\d+(?:\.\d+)?)"
    r"|(?:1'b[01xzXZ])"
)


def _strip_comments(expr: str) -> str:
    return re.sub(r"//.*?$|/\*.*?\*/", "", expr, flags=re.MULTILINE | re.DOTALL).strip()


def _validate_expression(expr: str, *, allow_past: bool = False) -> str:
    """Validate the tiny expression grammar accepted by deterministic templates."""
    cleaned = _strip_comments(expr).strip()
    if not cleaned:
        raise ValueError("Formal expression cannot be empty.")
    if len(cleaned) > 512:
        raise ValueError("Formal expression exceeds deterministic 512-character limit.")
    forbidden = (
        r";|`|\bmodule\b|\bendmodule\b|\balways\b|\bbegin\b|\bend\b|"
        r"\bassert\b|\bassume\b|\bcover\b|\bproperty\b|\bsequence\b|"
        r"##|\|->|\|=>|\$rose\s*\(|\$fell\s*\(|\$changed\s*\(|"
        r"\$toggle\s*\(|\$onehot0\s*\(|\buntil\b|\beventually\b"
    )
    if re.search(forbidden, cleaned, re.IGNORECASE):
        raise ValueError(f"Expression contains an unsupported construct: {cleaned}")

    if allow_past:
        past_calls = re.findall(r"\$past\s*\(\s*([A-Za-z_]\w*(?:\[[0-9]+(?::[0-9]+)?\])?)\s*(?:,\s*([0-8]))?\s*\)", cleaned, re.I)
        replaced = re.sub(
            r"\$past\s*\(\s*[A-Za-z_]\w*(?:\[[0-9]+(?::[0-9]+)?\])?\s*(?:,\s*[0-8])?\s*\)",
            "PASTVAL",
            cleaned,
            flags=re.I,
        )
        if "$past" in replaced.lower():
            raise ValueError("Only $past(identifier[, 1..8]) is allowed.")
        cleaned_for_lex = replaced
    else:
        if "$past" in cleaned.lower():
            raise ValueError("$past is only allowed in past_history templates.")
        cleaned_for_lex = cleaned

    # Ban string literals, calls other than the bounded $past form, and unusual operators.
    if re.search(r"[{};:`]|\b(?:fork|join|disable|wait|force|release|task|function)\b", cleaned_for_lex, re.I):
        raise ValueError("Expression contains syntax outside the bounded formal grammar.")
    if re.search(r"(?<![<>=!])=(?!=)|(?<![<>=!])>(?!=)|(?<![<>=!])<(?![<=>])", cleaned_for_lex):
        # Relational operators are allowed; a standalone assignment-like operator is not.
        raise ValueError("Expression contains a standalone assignment/comparison operator outside the bounded grammar.")
    if not re.fullmatch(
        r"[A-Za-z0-9_\[\]'\.\s\(\)\!\&\|\+\-\*\/\%<>=~\^]+",
        cleaned_for_lex,
    ):
        raise ValueError(f"Expression uses characters outside the bounded grammar: {cleaned}")

    # Identifiers/slices/literals must be token-like; operators and parentheses can separate them.
    tokens = re.findall(
        r"PASTVAL|[A-Za-z_]\w*(?:\[[0-9]+(?::[0-9]+)?\])?|[0-9]+(?:'[bBoOdDhHxX][0-9a-fA-F_xXzZ]+)?|==|!=|<=|>=|&&|\|\||<<|>>|[!~&|+\-*/%<>=^()]",
        cleaned_for_lex,
    )
    residue = re.sub(
        r"PASTVAL|[A-Za-z_]\w*(?:\[[0-9]+(?::[0-9]+)?\])?|[0-9]+(?:'[bBoOdDhHxX][0-9a-fA-F_xXzZ]+)?|==|!=|<=|>=|&&|\|\||<<|>>|[!~&|+\-*/%<>=^()]|\s+",
        "",
        cleaned_for_lex,
    )
    if residue:
        raise ValueError(f"Expression contains invalid token text: {residue}")
    return cleaned


class FormalPropertySpec(BaseModel):
    """Typed, bounded representation of one property selected by the architect agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=96)
    kind: FormalTemplateKind
    clock: str | None = Field(default="clk")
    reset: str | None = None
    antecedent: str | None = None
    consequent: str | None = None
    expression: str | None = None
    signal: str | None = None
    value: str | None = None
    cycles: int = Field(default=1, ge=1, le=8)
    description: str = Field(default="", max_length=512)
    disable_iff_reset: bool = Field(
        default=False,
        description=(
            "True when the source SVA carried `disable iff` on the active reset. "
            "The compiled checker must then evaluate only while the reset is "
            "inactive, mirroring the source semantics instead of asserting "
            "through the reset window (unprovable for synchronous resets)."
        ),
    )

    @model_validator(mode="after")
    def validate_shape(self) -> "FormalPropertySpec":
        if self.clock is not None and not re.fullmatch(r"[A-Za-z_]\w*", self.clock):
            raise ValueError(f"Invalid formal clock identifier: {self.clock}")
        if self.reset is not None:
            if ":" not in self.reset:
                raise ValueError("Reset must use '<identifier>:active_low|active_high'.")
            reset_name, polarity = self.reset.split(":", 1)
            if not re.fullmatch(r"[A-Za-z_]\w*", reset_name) or polarity not in {"active_low", "active_high"}:
                raise ValueError(f"Invalid reset descriptor: {self.reset}")

        required_by_kind: dict[FormalTemplateKind, list[str]] = {
            FormalTemplateKind.BOOLEAN: ["expression"],
            FormalTemplateKind.SAME_CYCLE_IMPLICATION: ["antecedent", "consequent"],
            FormalTemplateKind.NEXT_CYCLE_IMPLICATION: ["antecedent", "consequent"],
            FormalTemplateKind.RESET_ASSERTION: ["consequent"],
            FormalTemplateKind.ONEHOT: ["signal"],
            FormalTemplateKind.ONEHOT0: ["signal"],
            FormalTemplateKind.ONEHOT_OR_EQUALS: ["signal", "value"],
            FormalTemplateKind.PAST_EQUALS: ["signal", "value"],
            FormalTemplateKind.PAST_STABLE: ["signal"],
            FormalTemplateKind.PAST_EXPRESSION: ["expression"],
            FormalTemplateKind.TAUTOLOGY: [],
        }
        for field_name in required_by_kind[self.kind]:
            if not getattr(self, field_name):
                raise ValueError(f"Formal template '{self.kind.value}' requires '{field_name}'.")

        if self.kind in (FormalTemplateKind.NEXT_CYCLE_IMPLICATION, FormalTemplateKind.ONEHOT, FormalTemplateKind.ONEHOT0, FormalTemplateKind.ONEHOT_OR_EQUALS, FormalTemplateKind.PAST_EQUALS, FormalTemplateKind.PAST_STABLE, FormalTemplateKind.PAST_EXPRESSION) and self.clock is None:
            raise ValueError(f"Formal template '{self.kind.value}' requires a clock.")

        if self.kind == FormalTemplateKind.RESET_ASSERTION and self.reset is None:
            raise ValueError("reset_assertion requires a reset descriptor.")

        if self.signal:
            if not re.fullmatch(r"[A-Za-z_]\w*(?:\[[0-9]+(?::[0-9]+)?\])?", self.signal.strip()):
                raise ValueError(f"Invalid signal identifier: {self.signal}")
        if self.value:
            _validate_expression(self.value)
        if self.antecedent:
            _validate_expression(self.antecedent, allow_past=False)
        if self.consequent:
            _validate_expression(self.consequent, allow_past=False)
        if self.expression:
            _validate_expression(self.expression, allow_past=self.kind == FormalTemplateKind.PAST_EXPRESSION)
        return self


class UnsupportedFormalTemplate(ValueError):
    """Raised when a property cannot be reduced to the deterministic template DSL."""


def _strip_sva_wrappers(raw: str) -> tuple[str, str | None, str | None, bool]:
    expr = raw.strip()
    clock = None
    reset = None
    disable_iff_reset = False
    m_clock = re.search(r"@\(\s*posedge\s+([A-Za-z_]\w*)\s*\)", expr, re.I)
    if m_clock:
        clock = m_clock.group(1)
    m_reset = re.search(r"disable\s+iff\s*\(\s*(!?)([A-Za-z_]\w*)\s*\)", expr, re.I)
    if m_reset:
        negated = bool(m_reset.group(1))
        reset = f"{m_reset.group(2)}:{'active_low' if negated else 'active_high'}"
        # `disable iff` on the asserted reset (e.g. `disable iff (!rst_n)`)
        # suspends evaluation while reset is active; the compiled checker
        # must preserve that suspension instead of asserting through it.
        disable_iff_reset = True
    m_prop = re.search(r"(?:assert\s+)?property\s*\(\s*(.*)\)\s*;?\s*$", expr, re.I | re.S)
    if m_prop:
        expr = m_prop.group(1).strip()
        expr = re.sub(r"^@\([^)]*\)\s*", "", expr).strip()
        expr = re.sub(r"^disable\s+iff\s*\([^)]*\)\s*", "", expr, flags=re.I).strip()
    return expr.rstrip(";").strip(), clock, reset, disable_iff_reset


def _split_implication(expr: str) -> tuple[str, str, bool] | None:
    if "|=>" in expr:
        left, right = expr.split("|=>", 1)
        return left.strip(), right.strip(), True
    if "|->" in expr:
        left, right = expr.split("|->", 1)
        return left.strip(), right.strip(), False
    return None


def classify_legacy_property(
    name: str,
    raw_expression: str,
    default_clock: str | None = "clk",
    default_reset: str | None = "rst_n:active_low",
) -> FormalPropertySpec:
    """Classify only a conservative subset of legacy SVA expressions."""
    expr, clock_hint, reset_hint, disable_iff_reset = _strip_sva_wrappers(raw_expression)
    clock = clock_hint if clock_hint is not None else default_clock
    reset = reset_hint if reset_hint is not None else default_reset

    # P3-COMPLETE (flag-gated): boolean tautologies classify to TAUTOLOGY so
    # they are dropped with an explicit audit reason instead of compiling to
    # vacuous assertions. Flag off: skipped entirely (legacy behavior).
    if gate_fixes_enabled() and is_tautological_property_text(expr):
        return FormalPropertySpec(
            name=name,
            kind=FormalTemplateKind.TAUTOLOGY,
            clock=clock,
            reset=reset,
            description="P3-COMPLETE: boolean tautology dropped at classification.",
            disable_iff_reset=disable_iff_reset,
        )

    unsupported = (
        r"\bsequence\b|\bendsequence\b|\bproperty\b|\bendproperty\b|"
        r"##\s*(?:[2-9]|\[[^\]]+\])|\[\*\d+\]|\buntil\b|\beventually\b|"
        r"\bs_eventually\b|\bfirst_match\b|\bthroughout\b|\bwithin\b"
    )
    if re.search(unsupported, expr, re.I):
        raise UnsupportedFormalTemplate(f"Unsupported temporal construct in '{name}': {expr}")

    implication = _split_implication(expr)
    if implication:
        left, right, next_cycle = implication
        # A delay chained onto a non-overlapping implication (e.g. `a |=> ##1 b`,
        # which means `a |-> ##2 b`) is outside the supported bounded subset.
        # It must fail closed here: silently rewriting it to same-cycle `|->`
        # would alter its temporal meaning.
        if next_cycle and re.search(r"##", right, re.I):
            raise UnsupportedFormalTemplate(
                f"Delayed non-overlapping implication in '{name}' is outside the bounded subset: {expr}"
            )
        if "$past" in right.lower() and not next_cycle:
            try:
                _validate_expression(right, allow_past=True)
                _validate_expression(left, allow_past=False)
            except ValueError as exc:
                raise UnsupportedFormalTemplate(f"Unsupported historical expression in '{name}': {exc}") from exc
            return FormalPropertySpec(
                name=name,
                kind=FormalTemplateKind.PAST_EXPRESSION,
                clock=clock,
                reset=reset,
                expression=f"(!({left}) || ({right}))",
                description="Legacy SVA implication reduced to a bounded historical boolean expression.",
                disable_iff_reset=disable_iff_reset,
            )
        try:
            _validate_expression(left, allow_past=False)
            _validate_expression(right, allow_past=False)
        except ValueError as exc:
            raise UnsupportedFormalTemplate(f"Unsupported expression in '{name}': {exc}") from exc
        return FormalPropertySpec(
            name=name,
            kind=FormalTemplateKind.NEXT_CYCLE_IMPLICATION if next_cycle else FormalTemplateKind.SAME_CYCLE_IMPLICATION,
            clock=clock,
            reset=reset,
            antecedent=left,
            consequent=right,
            description="Classified deterministically from the bounded legacy SVA subset.",
            disable_iff_reset=disable_iff_reset,
        )

    onehot_match = re.fullmatch(r"\$onehot\s*\(\s*([^()]+)\s*\)", expr, re.I)
    if onehot_match:
        return FormalPropertySpec(
            name=name, kind=FormalTemplateKind.ONEHOT, clock=clock, reset=reset,
            signal=onehot_match.group(1).strip(),
            disable_iff_reset=disable_iff_reset,
        )

    onehot0_match = re.fullmatch(r"\$onehot0\s*\(\s*([^()]+)\s*\)", expr, re.I)
    if onehot0_match:
        return FormalPropertySpec(
            name=name, kind=FormalTemplateKind.ONEHOT0, clock=clock, reset=reset,
            signal=onehot0_match.group(1).strip(),
            disable_iff_reset=disable_iff_reset,
        )

    onehot_or = re.fullmatch(r"\$onehot\s*\(\s*([^()]+)\s*\)\s*\|\|\s*([^=]+)==\s*(.+)", expr, re.I)
    if onehot_or and onehot_or.group(1).strip() == onehot_or.group(2).strip():
        return FormalPropertySpec(
            name=name,
            kind=FormalTemplateKind.ONEHOT_OR_EQUALS,
            clock=clock,
            reset=reset,
            signal=onehot_or.group(1).strip(),
            value=onehot_or.group(3).strip(),
            disable_iff_reset=disable_iff_reset,
        )

    past_terms = re.findall(r"\$past\s*\(\s*[A-Za-z_]\w*(?:\[[0-9]+(?::[0-9]+)?\])?\s*(?:,\s*[0-8])?\s*\)", expr, re.I)
    if past_terms:
        try:
            _validate_expression(expr, allow_past=True)
        except ValueError as exc:
            raise UnsupportedFormalTemplate(f"Could not safely classify historical property '{name}': {exc}") from exc
        return FormalPropertySpec(
            name=name, kind=FormalTemplateKind.PAST_EXPRESSION, clock=clock, reset=reset,
            expression=expr,
            disable_iff_reset=disable_iff_reset,
        )

    stable_match = re.fullmatch(r"\$stable\s*\(\s*([A-Za-z_]\w*)\s*\)", expr, re.I)
    if stable_match:
        signal = stable_match.group(1)
        return FormalPropertySpec(
            name=name, kind=FormalTemplateKind.PAST_STABLE, clock=clock, reset=reset, signal=signal,
            disable_iff_reset=disable_iff_reset,
        )

    if not re.search(r"\$past|\$rose|\$fell|\$stable|\$changed|\$toggle|\$onehot|\|->|\|=>|##", expr, re.I):
        try:
            return FormalPropertySpec(name=name, kind=FormalTemplateKind.BOOLEAN, clock=clock, reset=reset, expression=expr, disable_iff_reset=disable_iff_reset)
        except ValueError as exc:
            raise UnsupportedFormalTemplate(f"Could not classify property '{name}': {exc}") from exc

    raise UnsupportedFormalTemplate(f"Could not classify property '{name}' into deterministic templates: {expr}")


def _guard(prop: FormalPropertySpec, *, references_reset: bool = False) -> str:
    if prop.clock is None:
        return "1'b1"
    if prop.disable_iff_reset and prop.reset:
        # The source SVA suspended evaluation while reset was asserted
        # (`disable iff` on the active reset). Mirror that suspension: check
        # only while reset is inactive. Without this, synchronous-reset
        # designs fail spuriously on the entry edge before logic can respond.
        reset_name, polarity = prop.reset.split(":", 1)
        inactive = reset_name if polarity == "active_low" else f"!{reset_name}"
        return f"!init && {inactive}"
    if not prop.reset or references_reset:
        return "!init"
    reset_name, polarity = prop.reset.split(":", 1)
    inactive = reset_name if polarity == "active_low" else f"!{reset_name}"
    return f"!init && {inactive}"


_GATE_FIXES_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def gate_fixes_enabled() -> bool:
    """MIND3_GATE_FIXES master flag for P3/P5/P6/P7 (default ON).

    Read at call time (never cached) so tests can toggle it per case.
    Empty/unset means ON; 0/false/no/off means OFF (exact V0/V1 behavior).
    """
    return os.environ.get("MIND3_GATE_FIXES", "").strip().lower() not in _GATE_FIXES_OFF_VALUES


class NoGenuineProperty(ValueError):
    """Raised when every specified property was dropped as vacuous-by-text."""


def _strip_outer_parens(expr: str) -> str:
    e = expr.strip()
    while len(e) >= 2 and e.startswith("(") and e.endswith(")"):
        depth = 0
        balanced = True
        for i, ch in enumerate(e):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(e) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        e = e[1:-1].strip()
    return e


def _split_top_level(expr: str, op: str) -> list[str]:
    """Split on operator occurrences outside parentheses (post-validation text)."""
    parts: list[str] = []
    depth = 0
    cur: list[str] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
            cur.append(ch)
            i += 1
        elif ch == ")":
            depth -= 1
            cur.append(ch)
            i += 1
        elif depth == 0 and expr.startswith(op, i):
            parts.append("".join(cur))
            cur = []
            i += len(op)
        else:
            cur.append(ch)
            i += 1
    parts.append("".join(cur))
    return parts


def is_tautology_expression(expr: str) -> bool:
    """Structural tautology check (P3): `x == x`, `a || !a` / `!a || a`.

    Deterministic and conservative: only exact self-equality and two-operand
    negation pairs (prefix `!` or `~`) count. Anything else returns False.
    """
    e = _strip_outer_parens(expr.strip())
    if not e:
        return False
    eq = _split_top_level(e, "==")
    if len(eq) == 2:
        left, right = eq[0].strip(), eq[1].strip()
        if left and left == right:
            return True
    ors = _split_top_level(e, "||")
    if len(ors) == 2:
        left = _strip_outer_parens(ors[0].strip())
        right = _strip_outer_parens(ors[1].strip())

        def _negated(a: str, b: str) -> bool:
            return (
                a.startswith("!")
                and a[1:].strip() == b
                or a.startswith("~")
                and a[1:].strip() == b
            )

        if left and right and (_negated(left, right) or _negated(right, left)):
            return True
    return False


# ── P3-COMPLETE: classifier-level tautology detection ────────────────────────
# Decides boolean tautologies that the structural P3 check cannot see
# (`1'b1`, `X |-> X`, multi-variable propositional tautologies). Deliberately
# conservative: anything outside the decidable subset below (arithmetic,
# slices, cross-signal comparisons, calls, temporal operators, >8 variables)
# is NOT a tautology here and keeps flowing to the normal template path
# (render-level P3 remains as defense in depth). Callers must gate on
# gate_fixes_enabled() so flag-0 behavior is byte-identical.

_P3C_MAX_VARIABLES = 8

_P3C_TRUE_CONSTANTS = frozenset({"1'b1", "1"})
_P3C_FALSE_CONSTANTS = frozenset({"1'b0", "0"})

_P3C_TOKEN_RE = re.compile(
    r"(?P<impl>\|->)"
    r"|(?P<and>&&)"
    r"|(?P<or>\|\|)"
    r"|(?P<eq>==)"
    r"|(?P<ne>!=)"
    r"|(?P<not>!)"
    r"|(?P<lp>\()"
    r"|(?P<rp>\))"
    r"|(?P<ident>[A-Za-z_]\w*)"
    r"|(?P<number>\d[\d_]*(?:'[bBoOdDhH][0-9a-fA-F_xXzZ?]+)?)"
    r"|(?P<ws>\s+)"
    r"|(?P<bad>.)"
)


class _P3CAbstain(Exception):
    """Raised when text leaves the conservative decidable subset."""


def _p3c_normalize(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip())
    prev = None
    cur = collapsed
    while prev != cur:
        prev = cur
        if cur.startswith("(") and cur.endswith(")"):
            depth = 0
            balanced = True
            for i, ch in enumerate(cur):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                if depth == 0 and i < len(cur) - 1:
                    balanced = False
                    break
            if balanced and depth == 0:
                cur = cur[1:-1].strip()
                continue
        break
    return cur


def _p3c_tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for match in _P3C_TOKEN_RE.finditer(text):
        kind = match.lastgroup or "bad"
        if kind in ("ws",):
            continue
        if kind == "bad":
            raise _P3CAbstain(f"outside decidable alphabet: {match.group()!r}")
        tokens.append((kind, match.group()))
    return tokens


def _p3c_parse(text: str) -> tuple:
    """Parse decidable boolean text into an AST. Raises _P3CAbstain."""
    tokens = _p3c_tokenize(text)
    if not tokens:
        raise _P3CAbstain("empty expression")
    pos = 0

    def peek() -> tuple[str, str] | None:
        return tokens[pos] if pos < len(tokens) else None

    def next_token() -> tuple[str, str]:
        nonlocal pos
        tok = peek()
        if tok is None:
            raise _P3CAbstain("unexpected end of expression")
        pos += 1
        return tok

    def parse_or() -> tuple:
        left = parse_and()
        while peek() is not None and peek()[0] == "or":
            next_token()
            left = ("or", left, parse_and())
        return left

    def parse_and() -> tuple:
        left = parse_not()
        while peek() is not None and peek()[0] == "and":
            next_token()
            left = ("and", left, parse_not())
        return left

    def parse_not() -> tuple:
        tok = peek()
        if tok is not None and tok[0] == "not":
            next_token()
            return ("not", parse_not())
        return parse_cmp()

    def fold_number(raw: str) -> tuple:
        key = raw.replace("_", "")
        low = key.lower()
        if low in ("1'b1", "1"):
            return ("const", True)
        if low in ("1'b0", "0"):
            return ("const", False)
        # Any other bare literal (multi-bit values, x/z digits): opaque
        # proposition keyed by normalized text. A constant never varies, so
        # requiring all-true over a free variable is a strictly stronger
        # condition — proofs stay sound, misses stay conservative.
        return ("var", "lit:" + re.sub(r"\s+", "", low))

    def parse_cmp() -> tuple:
        left = parse_primary()
        tok = peek()
        if tok is not None and tok[0] in ("eq", "ne"):
            next_token()
            right = parse_primary()
            if left[0] == "const" and right[0] == "const":
                val = (left[1] == right[1]) if tok[0] == "eq" else (left[1] != right[1])
                return ("const", val)
            if left[0] == "var" and right[0] == "var" and left[1] == right[1]:
                # Self-comparison is width-independent: identical operands are
                # equal (==) / not-unequal (!=) in two-state formal semantics.
                return ("const", True) if tok[0] == "eq" else ("const", False)
            # Cross-operand == / != are commutative: canonicalize operand order
            # so `(b == a) || !(a == b)` atomizes to P || !P. Ordering
            # comparisons (<=, >=, <, >) are never built here.
            lkey = left[1] if left[0] == "var" else repr(left)
            rkey = right[1] if right[0] == "var" else repr(right)
            if tok[0] in ("eq", "ne") and lkey > rkey:
                lkey, rkey = rkey, lkey
            return ("var", f"cmp:{tok[0]}:{lkey}:{rkey}")
        return left

    def parse_primary() -> tuple:
        tok = next_token()
        if tok[0] == "ident":
            return ("var", tok[1])
        if tok[0] == "number":
            return fold_number(tok[1])
        if tok[0] == "lp":
            node = parse_or()
            closing = next_token()
            if closing[0] != "rp":
                raise _P3CAbstain("unbalanced parenthesis")
            return node
        raise _P3CAbstain(f"unexpected token: {tok[1]!r}")

    node = parse_or()
    if peek() is not None:
        raise _P3CAbstain(f"trailing tokens: {peek()[1]!r}")
    return node


def _p3c_variables(node: tuple) -> set[str]:
    kind = node[0]
    if kind == "const":
        return set()
    if kind == "var":
        return {node[1]}
    if kind == "not":
        return _p3c_variables(node[1])
    return _p3c_variables(node[1]) | _p3c_variables(node[2])


def _p3c_evaluate(node: tuple, env: dict[str, bool]) -> bool:
    kind = node[0]
    if kind == "const":
        return node[1]
    if kind == "var":
        return env[node[1]]
    if kind == "not":
        return not _p3c_evaluate(node[1], env)
    if kind == "and":
        return _p3c_evaluate(node[1], env) and _p3c_evaluate(node[2], env)
    # kind == "or"
    return _p3c_evaluate(node[1], env) or _p3c_evaluate(node[2], env)


def _p3c_table_tautology(text: str) -> bool:
    """True only if text is a boolean tautology over <= 8 variables.

    Alphabet is restricted to identifiers, !, &&, ||, ==, !=, parens and
    foldable 0/1 constants. Slices, arithmetic, shifts, bitwise, calls ($),
    temporal operators and |=> never reach the table (tokenizer abstains).
    Bare identifiers abstract whole signals: sound here because every
    remaining operator is truth-functional (!, &&, ||) or atomized (==/!=),
    so skeleton-all-true implies real-all-true.
    """
    try:
        if "|=>" in text:
            return False
        if text.count("|->") > 1:
            return False
        if "|->" in text:
            left, _, right = text.partition("|->")
            body = f"(!({left})) || ({right})"
        else:
            body = text
        node = _p3c_parse(body)
        variables = sorted(_p3c_variables(node))
        if len(variables) > _P3C_MAX_VARIABLES:
            return False
        for bits in range(1 << len(variables)):
            env = {name: bool((bits >> i) & 1) for i, name in enumerate(variables)}
            if not _p3c_evaluate(node, env):
                return False
        return True
    except _P3CAbstain:
        return False


def is_tautological_property_text(text: str) -> bool:
    """P3-COMPLETE classifier-level tautology decision.

    Conservative: True only for (a) constant-true, (b) structural P3 forms
    (`x == x`, `a || !a`), (c) identical-normalized `X |-> X`, or (d) a
    truth-table proof over the decidable subset. Everything else is False
    (normal template path). Callers must check gate_fixes_enabled() first.
    """
    expr = _p3c_normalize(text)
    if not expr:
        return False
    if expr.lower() in _P3C_TRUE_CONSTANTS:
        return True
    if is_tautology_expression(expr):
        return True
    if "|->" in expr and "|=>" not in expr and expr.count("|->") == 1:
        left, _, right = expr.partition("|->")
        if _p3c_normalize(left) and _p3c_normalize(left) == _p3c_normalize(right):
            return True
        # A false antecedent or true consequent decides the implication
        # regardless of the other side (slices and widths cannot matter).
        if _p3c_normalize(left).lower() in _P3C_FALSE_CONSTANTS:
            return True
        if _p3c_normalize(right).lower() in _P3C_TRUE_CONSTANTS:
            return True
    return _p3c_table_tautology(expr)


def _reset_asserted_form(prop: FormalPropertySpec) -> str | None:
    """Source-text form of 'reset asserted' for this property, if any."""
    if prop.reset is None:
        return None
    name, polarity = prop.reset.split(":", 1)
    return f"!{name}" if polarity == "active_low" else name


def _is_reset_asserted_antecedent(prop: FormalPropertySpec) -> bool:
    """P5 detection: implication whose antecedent is exactly reset-asserted."""
    if prop.kind not in (
        FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
    ):
        return False
    if prop.antecedent is None or prop.reset is None:
        return False
    target = _reset_asserted_form(prop)
    candidate = _strip_outer_parens(prop.antecedent.strip())
    return bool(target) and candidate == target


_P6_KINDS = frozenset({
    FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
    FormalTemplateKind.PAST_EQUALS,
    FormalTemplateKind.PAST_STABLE,
    FormalTemplateKind.PAST_EXPRESSION,
})


def _render_guard(prop: FormalPropertySpec, *, references_reset: bool = False) -> str:
    """Guard renderer shared by the assert and cover paths (P5b/P6).

    Guards must match exactly between assertion and cover point. With
    MIND3_GATE_FIXES on: reset-asserted-antecedent NEXT-cycle implications keep
    the init-only guard (P5b leaves non-same-cycle timing to the sites below);
    P6 additionally requires reset deasserted in the previous cycle for
    $past/|=> properties. P6 is never applied to P5b-rewritten properties
    (their sites return before reaching the P6 branch). Flag off (or
    inapplicable): byte-identical to the legacy `_guard`.
    """
    if prop.clock is None:
        return "1'b1"
    if gate_fixes_enabled() and prop.reset is not None:
        if prop.kind == FormalTemplateKind.NEXT_CYCLE_IMPLICATION and _is_reset_asserted_antecedent(prop):
            return "!init"
        if prop.kind in _P6_KINDS:
            reset_name, polarity = prop.reset.split(":", 1)
            prev_quiet = (
                f"$past({reset_name})"
                if polarity == "active_low"
                else f"$past(!{reset_name})"
            )
            base = _guard(prop, references_reset=references_reset)
            return f"({base}) && {prev_quiet}"
    return _guard(prop, references_reset=references_reset)


_WITNESS_SVA_LINE_RE = re.compile(r"check_assert_(.+)_sva_sv_(\d+)_(\d+)$")
_TEMPLATE_MARKER_RE = re.compile(r"\[MIND3-TEMPLATE:([A-Za-z0-9_]+)\]\s+(\S+)")


def resolve_witness_property(witness_name: str | None, sva_text: str | None) -> str | None:
    """Map a SymbiYosys witness name to the rendered contract property name.

    Witnesses embed the checker file and assert location
    (`check_assert_<stem>_sva_sv_<line>_<col>`); the generated checker marks
    each property block with `// [MIND3-TEMPLATE:<kind>] <name>`, so the
    nearest marker above the assert line names the violated property.
    Returns None when the name is not a witness, the line is out of range,
    or no marker precedes it (caller keeps the legacy uncertain path).
    """
    if not witness_name or not sva_text:
        return None
    match = _WITNESS_SVA_LINE_RE.search(witness_name.strip())
    if match is None:
        return None
    try:
        line_no = int(match.group(2))
    except ValueError:
        return None
    lines = sva_text.splitlines()
    if line_no < 1 or line_no > len(lines):
        return None
    for idx in range(line_no - 1, -1, -1):
        marker = _TEMPLATE_MARKER_RE.search(lines[idx])
        if marker is not None:
            return marker.group(2)
    return None


def contract_property_source(contract: Any, prop_name: str | None) -> tuple[str, str] | None:
    """(kind_value, source_text) for a named contract property, or None.

    Source text restates the property in the boolean/implication subset the
    repair prompt already uses (e.g. `req[0] |-> gnt[0]`), drawn from the
    typed spec — never invented. Duck-typed on the contract; works for both
    structured templates and legacy SVA entries.
    """
    if not prop_name:
        return None
    for prop in list(getattr(contract, "formal_properties", []) or []):
        if getattr(prop, "name", "") != prop_name:
            continue
        kind = getattr(prop, "kind", None)
        kind_value = str(getattr(kind, "value", kind) or "")
        antecedent = getattr(prop, "antecedent", None)
        consequent = getattr(prop, "consequent", None)
        expression = getattr(prop, "expression", None)
        signal = getattr(prop, "signal", None)
        value = getattr(prop, "value", None)
        if kind_value == "same_cycle_implication" and antecedent and consequent:
            return (kind_value, f"{antecedent} |-> {consequent}")
        if kind_value == "next_cycle_implication" and antecedent and consequent:
            return (kind_value, f"{antecedent} |=> {consequent}")
        if kind_value in ("boolean", "past_expression") and expression:
            return (kind_value, str(expression))
        if kind_value == "reset_assertion" and consequent:
            return (kind_value, str(consequent))
        if kind_value == "onehot" and signal:
            return (kind_value, f"$onehot({signal})")
        if kind_value == "onehot0" and signal:
            return (kind_value, f"$onehot0({signal})")
        if kind_value == "onehot_or_equals" and signal and value:
            return (kind_value, f"$onehot({signal}) || ({signal} == {value})")
        if kind_value == "past_equals" and signal and value:
            cycles = getattr(prop, "cycles", 1)
            return (kind_value, f"$past({signal}, {cycles}) == {value}")
        if kind_value == "past_stable" and signal:
            cycles = getattr(prop, "cycles", 1)
            return (kind_value, f"{signal} == $past({signal}, {cycles})")
        return None
    for prop in list(getattr(contract, "sva_properties", []) or []):
        if getattr(prop, "name", "") != prop_name:
            continue
        expr = getattr(prop, "property_expr", None) or getattr(prop, "expression", None)
        if expr:
            return ("legacy_sva", str(expr))
        return None
    return None


def _reset_asserted_past(prop: FormalPropertySpec) -> str:
    """P5b rewritten antecedent `$past(reset asserted)` for sync contracts."""
    assert prop.reset is not None
    reset_name, polarity = prop.reset.split(":", 1)
    if polarity == "active_low":
        return f"$past(!{reset_name})"
    return f"$past({reset_name})"


def compile_formal_property(
    prop: FormalPropertySpec, *, reset_synchronous: bool | None = None
) -> str:
    """Render a typed property as deterministic procedural SystemVerilog.

    `reset_synchronous` carries the contract's declared reset style (None when
    unknown; callers without a contract keep the legacy behavior). P5b: with
    MIND3_GATE_FIXES on, a same-cycle implication whose antecedent is the
    reset asserted renders as `$past(reset asserted) |-> consequent` under an
    init-only guard for synchronous contracts, and keeps the same-cycle form
    under an init-only guard for asynchronous (or unknown-style) contracts.
    """
    if prop.clock is None:
        event = "always @*"
    else:
        event = f"always @(posedge {prop.clock})"
    reset_name = prop.reset.split(":", 1)[0] if prop.reset else None
    references_reset = bool(reset_name and any(
        reset_name in (field or "")
        for field in (prop.antecedent, prop.consequent, prop.expression, prop.signal, prop.value)
    ))
    g = _render_guard(prop, references_reset=references_reset)

    if prop.kind == FormalTemplateKind.BOOLEAN:
        return f"  // [MIND3-TEMPLATE:boolean] {prop.name}\n  {event} begin\n    if ({g}) assert ({prop.expression});\n  end\n"
    if prop.kind == FormalTemplateKind.SAME_CYCLE_IMPLICATION:
        if gate_fixes_enabled() and _is_reset_asserted_antecedent(prop):
            if reset_synchronous is True:
                past_ant = _reset_asserted_past(prop)
                return (
                    f"  // [MIND3-TEMPLATE:same_cycle_implication] {prop.name}\n"
                    f"  {event} begin\n    if (!init) begin\n      if ({past_ant}) assert ({prop.consequent});\n    end\n  end\n"
                )
            return (
                f"  // [MIND3-TEMPLATE:same_cycle_implication] {prop.name}\n"
                f"  {event} begin\n    if (!init) begin\n      if ({prop.antecedent}) assert ({prop.consequent});\n    end\n  end\n"
            )
        return (
            f"  // [MIND3-TEMPLATE:same_cycle_implication] {prop.name}\n"
            f"  {event} begin\n    if ({g}) begin\n      if ({prop.antecedent}) assert ({prop.consequent});\n    end\n  end\n"
        )
    if prop.kind == FormalTemplateKind.NEXT_CYCLE_IMPLICATION:
        if prop.clock is None:
            raise UnsupportedFormalTemplate(f"Next-cycle property '{prop.name}' has no clock.")
        return (
            f"  // [MIND3-TEMPLATE:next_cycle_implication] {prop.name}\n"
            f"  {event} begin\n    if ({g}) begin\n      if ($past({prop.antecedent})) assert ({prop.consequent});\n    end\n  end\n"
        )
    if prop.kind == FormalTemplateKind.RESET_ASSERTION:
        if not prop.reset:
            raise UnsupportedFormalTemplate(f"Reset assertion '{prop.name}' has no reset descriptor.")
        reset_name, polarity = prop.reset.split(":", 1)
        active = f"!{reset_name}" if polarity == "active_low" else reset_name
        return (
            f"  // [MIND3-TEMPLATE:reset_assertion] {prop.name}\n"
            f"  {event} begin\n    if ({active}) assert ({prop.consequent});\n  end\n"
        )
    if prop.kind == FormalTemplateKind.ONEHOT:
        return (
            f"  // [MIND3-TEMPLATE:onehot] {prop.name}\n"
            f"  {event} begin\n    if ({g}) assert ($onehot({prop.signal}));\n  end\n"
        )
    if prop.kind == FormalTemplateKind.ONEHOT0:
        return (
            f"  // [MIND3-TEMPLATE:onehot0] {prop.name}\n"
            f"  {event} begin\n    if ({g}) assert ($onehot0({prop.signal}));\n  end\n"
        )
    if prop.kind == FormalTemplateKind.ONEHOT_OR_EQUALS:
        return (
            f"  // [MIND3-TEMPLATE:onehot_or_equals] {prop.name}\n"
            f"  {event} begin\n    if ({g}) assert ($onehot({prop.signal}) || ({prop.signal} == {prop.value}));\n  end\n"
        )
    if prop.kind == FormalTemplateKind.PAST_EQUALS:
        return (
            f"  // [MIND3-TEMPLATE:past_equals] {prop.name}\n"
            f"  {event} begin\n    if ({g}) assert ($past({prop.signal}, {prop.cycles}) == {prop.value});\n  end\n"
        )
    if prop.kind == FormalTemplateKind.PAST_STABLE:
        return (
            f"  // [MIND3-TEMPLATE:past_stable] {prop.name}\n"
            f"  {event} begin\n    if ({g}) assert ({prop.signal} == $past({prop.signal}, {prop.cycles}));\n  end\n"
        )
    if prop.kind == FormalTemplateKind.PAST_EXPRESSION:
        return (
            f"  // [MIND3-TEMPLATE:past_expression] {prop.name}\n"
            f"  {event} begin\n    if ({g}) assert ({prop.expression});\n  end\n"
        )
    raise UnsupportedFormalTemplate(f"No renderer exists for {prop.kind}")


def _tautology_checked_expression(prop: FormalPropertySpec) -> str | None:
    """Boolean text subject to P3 dropping, or None when inapplicable."""
    if prop.kind == FormalTemplateKind.BOOLEAN:
        return prop.expression
    if prop.kind == FormalTemplateKind.PAST_EXPRESSION:
        return prop.expression
    return None


def tautology_audit_for_contract(
    structured: list[FormalPropertySpec],
    legacy: list[Any],
    default_clock: str | None = "clk",
    default_reset: str | None = "rst_n:active_low",
) -> dict[str, Any]:
    """P3 audit: which specified properties are vacuous-by-text tautologies.

    Total function: legacy entries that cannot be classified are skipped here
    (the harness build still fails closed on them first). Returns
    {"total", "dropped", "kept"} where dropped holds property names.
    """
    dropped: list[str] = []
    total = len(structured) + len(legacy)
    for prop in structured:
        if not gate_fixes_enabled():
            break
        if prop.kind == FormalTemplateKind.TAUTOLOGY:
            dropped.append(prop.name)
            continue
        text = _tautology_checked_expression(prop)
        if text is not None and is_tautology_expression(text):
            dropped.append(prop.name)
    for prop in legacy:
        if not gate_fixes_enabled():
            break
        try:
            classified = classify_legacy_property(
                name=getattr(prop, "name", "?"),
                raw_expression=getattr(prop, "property_expr", ""),
                default_clock=default_clock,
                default_reset=default_reset,
            )
        except (UnsupportedFormalTemplate, ValueError):
            continue
        if classified.kind == FormalTemplateKind.TAUTOLOGY:
            dropped.append(getattr(prop, "name", "?"))
            continue
        text = _tautology_checked_expression(classified)
        if text is not None and is_tautology_expression(text):
            dropped.append(getattr(prop, "name", "?"))
    return {"total": total, "dropped": dropped, "kept": total - len(dropped)}


def compile_contract_properties(
    structured: list[FormalPropertySpec],
    legacy: list[Any],
    default_clock: str | None = "clk",
    default_reset: str | None = "rst_n:active_low",
    *,
    reset_synchronous: bool | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Compile structured properties or safely classify legacy properties."""
    compiled: list[str] = []
    audit: list[dict[str, Any]] = []
    if structured:
        for prop in structured:
            if gate_fixes_enabled():
                if prop.kind == FormalTemplateKind.TAUTOLOGY:
                    audit.append({
                        "name": prop.name,
                        "kind": prop.kind.value,
                        "source": "p3_complete_classifier",
                        "supported": False,
                        "dropped": True,
                        "drop_reason": "tautology",
                    })
                    continue
                text = _tautology_checked_expression(prop)
                if text is not None and is_tautology_expression(text):
                    audit.append({
                        "name": prop.name,
                        "kind": prop.kind.value,
                        "source": "structured_template",
                        "supported": False,
                        "dropped": True,
                        "drop_reason": "tautology",
                    })
                    continue
            compiled.append(compile_formal_property(prop, reset_synchronous=reset_synchronous))
            audit.append({
                "name": prop.name,
                "kind": prop.kind.value,
                "source": "structured_template",
                "supported": True,
            })
        if (structured or legacy) and not compiled:
            raise NoGenuineProperty(
                "Every specified property was dropped as vacuous-by-text."
            )
        return "\n".join(compiled), audit

    for prop in legacy:
        # When the contract is demonstrably combinational, ignore SVAProperty's historical
        # default clock so the renderer cannot invent a clock that is not in the interface.
        prop_default_clock = default_clock
        prop_default_reset = default_reset
        classified = classify_legacy_property(
            name=prop.name,
            raw_expression=prop.property_expr,
            default_clock=prop_default_clock,
            default_reset=prop_default_reset,
        )
        if gate_fixes_enabled():
            if classified.kind == FormalTemplateKind.TAUTOLOGY:
                audit.append({
                    "name": prop.name,
                    "kind": classified.kind.value,
                    "source": "p3_complete_classifier",
                    "supported": False,
                    "dropped": True,
                    "drop_reason": "tautology",
                })
                continue
            text = _tautology_checked_expression(classified)
            if text is not None and is_tautology_expression(text):
                audit.append({
                    "name": prop.name,
                    "kind": classified.kind.value,
                    "source": "legacy_bounded_classifier",
                    "supported": False,
                    "dropped": True,
                    "drop_reason": "tautology",
                })
                continue
        compiled.append(compile_formal_property(classified, reset_synchronous=reset_synchronous))
        audit.append({
            "name": prop.name,
            "kind": classified.kind.value,
            "source": "legacy_bounded_classifier",
            "supported": True,
        })
    if (structured or legacy) and not compiled:
        raise NoGenuineProperty(
            "Every specified property was dropped as vacuous-by-text."
        )
    return "\n".join(compiled), audit


def compile_cover_point(
    prop: FormalPropertySpec, *, reset_synchronous: bool | None = None
) -> tuple[str, str] | None:
    """Render a bounded antecedent-reachability cover for one implication property.

    Returns (cover_expression, cover_guard) or None when the property kind has
    no antecedent (boolean, onehot, reset_assertion, past_*). The guard mirrors
    the assert renderer's guard exactly, and next-cycle properties cover
    ``$past(antecedent)`` — precisely the condition under which the matching
    assertion is evaluated. A cover point reached within the BMC bound proves
    the implication was exercised; an unreached one proves nothing was tested.
    """
    if prop.kind not in (
        FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        FormalTemplateKind.NEXT_CYCLE_IMPLICATION,
    ):
        return None
    if prop.kind == FormalTemplateKind.NEXT_CYCLE_IMPLICATION and prop.clock is None:
        raise UnsupportedFormalTemplate(f"Next-cycle cover for '{prop.name}' has no clock.")
    # Identical references_reset computation to compile_formal_property: the
    # cover guard must equal the assert guard exactly, never stricter or looser.
    reset_name = prop.reset.split(":", 1)[0] if prop.reset else None
    references_reset = bool(reset_name and any(
        reset_name in (field or "")
        for field in (prop.antecedent, prop.consequent, prop.expression, prop.signal, prop.value)
    ))
    guard = _render_guard(prop, references_reset=references_reset)
    if prop.kind == FormalTemplateKind.SAME_CYCLE_IMPLICATION:
        # P5b: the cover must check the rewritten antecedent, reachable under
        # the same init-only guard as the assertion.
        if gate_fixes_enabled() and _is_reset_asserted_antecedent(prop):
            if reset_synchronous is True:
                return (_reset_asserted_past(prop), "!init")
            return (prop.antecedent or "", "!init")
        return (prop.antecedent or "", guard)
    return (f"$past({prop.antecedent})", guard)


__all__ = [
    "FormalTemplateKind",
    "FormalPropertySpec",
    "UnsupportedFormalTemplate",
    "NoGenuineProperty",
    "classify_legacy_property",
    "compile_formal_property",
    "compile_contract_properties",
    "compile_cover_point",
    "gate_fixes_enabled",
    "is_tautological_property_text",
    "is_tautology_expression",
    "tautology_audit_for_contract",
    "resolve_witness_property",
    "contract_property_source",
]
