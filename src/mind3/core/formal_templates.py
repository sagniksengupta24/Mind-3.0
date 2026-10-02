"""Deterministic, bounded formal-property templates for Mind 3.0.

The architect model selects a typed template and supplies only bounded expressions.
Mind 3.0 owns the SystemVerilog rendering. Legacy free-form SVA is accepted only
when a conservative classifier can map it without changing clock/reset semantics;
otherwise the property fails closed.
"""

from __future__ import annotations

from enum import StrEnum
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
            FormalTemplateKind.BOOLEAN: ("expression",),
            FormalTemplateKind.SAME_CYCLE_IMPLICATION: ("antecedent", "consequent"),
            FormalTemplateKind.NEXT_CYCLE_IMPLICATION: ("antecedent", "consequent"),
            FormalTemplateKind.RESET_ASSERTION: ("consequent",),
            FormalTemplateKind.ONEHOT: ("signal",),
            FormalTemplateKind.ONEHOT0: ("signal",),
            FormalTemplateKind.ONEHOT_OR_EQUALS: ("signal", "value"),
            FormalTemplateKind.PAST_EQUALS: ("signal", "value"),
            FormalTemplateKind.PAST_STABLE: ("signal",),
            FormalTemplateKind.PAST_EXPRESSION: ("expression",),
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


def _strip_sva_wrappers(raw: str) -> tuple[str, str | None, str | None]:
    expr = raw.strip()
    clock = None
    reset = None
    m_clock = re.search(r"@\(\s*posedge\s+([A-Za-z_]\w*)\s*\)", expr, re.I)
    if m_clock:
        clock = m_clock.group(1)
    m_reset = re.search(r"disable\s+iff\s*\(\s*(!?)([A-Za-z_]\w*)\s*\)", expr, re.I)
    if m_reset:
        reset = f"{m_reset.group(2)}:{'active_low' if m_reset.group(1) else 'active_high'}"
    m_prop = re.search(r"(?:assert\s+)?property\s*\(\s*(.*)\)\s*;?\s*$", expr, re.I | re.S)
    if m_prop:
        expr = m_prop.group(1).strip()
        expr = re.sub(r"^@\([^)]*\)\s*", "", expr).strip()
        expr = re.sub(r"^disable\s+iff\s*\([^)]*\)\s*", "", expr, flags=re.I).strip()
    return expr.rstrip(";").strip(), clock, reset


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
    expr, clock_hint, reset_hint = _strip_sva_wrappers(raw_expression)
    clock = clock_hint if clock_hint is not None else default_clock
    reset = reset_hint if reset_hint is not None else default_reset

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
        )

    if re.fullmatch(r"\$onehot\s*\(\s*([^()]+)\s*\)", expr, re.I):
        return FormalPropertySpec(
            name=name, kind=FormalTemplateKind.ONEHOT, clock=clock, reset=reset,
            signal=re.fullmatch(r"\$onehot\s*\(\s*([^()]+)\s*\)", expr, re.I).group(1).strip(),
        )

    if re.fullmatch(r"\$onehot0\s*\(\s*([^()]+)\s*\)", expr, re.I):
        return FormalPropertySpec(
            name=name, kind=FormalTemplateKind.ONEHOT0, clock=clock, reset=reset,
            signal=re.fullmatch(r"\$onehot0\s*\(\s*([^()]+)\s*\)", expr, re.I).group(1).strip(),
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
        )

    if re.fullmatch(r"\$stable\s*\(\s*([A-Za-z_]\w*)\s*\)", expr, re.I):
        signal = re.fullmatch(r"\$stable\s*\(\s*([A-Za-z_]\w*)\s*\)", expr, re.I).group(1)
        return FormalPropertySpec(
            name=name, kind=FormalTemplateKind.PAST_STABLE, clock=clock, reset=reset, signal=signal,
        )

    if not re.search(r"\$past|\$rose|\$fell|\$stable|\$changed|\$toggle|\$onehot|\|->|\|=>|##", expr, re.I):
        try:
            return FormalPropertySpec(name=name, kind=FormalTemplateKind.BOOLEAN, clock=clock, reset=reset, expression=expr)
        except ValueError as exc:
            raise UnsupportedFormalTemplate(f"Could not classify property '{name}': {exc}") from exc

    raise UnsupportedFormalTemplate(f"Could not classify property '{name}' into deterministic templates: {expr}")


def _guard(prop: FormalPropertySpec, *, references_reset: bool = False) -> str:
    if prop.clock is None:
        return "1'b1"
    if not prop.reset or references_reset:
        return "!init"
    reset_name, polarity = prop.reset.split(":", 1)
    inactive = reset_name if polarity == "active_low" else f"!{reset_name}"
    return f"!init && {inactive}"


def compile_formal_property(prop: FormalPropertySpec) -> str:
    """Render a typed property as deterministic procedural SystemVerilog."""
    if prop.clock is None:
        event = "always @*"
    else:
        event = f"always @(posedge {prop.clock})"
    reset_name = prop.reset.split(":", 1)[0] if prop.reset else None
    references_reset = bool(reset_name and any(
        reset_name in (field or "")
        for field in (prop.antecedent, prop.consequent, prop.expression, prop.signal, prop.value)
    ))
    g = _guard(prop, references_reset=references_reset)

    if prop.kind == FormalTemplateKind.BOOLEAN:
        return f"  // [MIND3-TEMPLATE:boolean] {prop.name}\n  {event} begin\n    if ({g}) assert ({prop.expression});\n  end\n"
    if prop.kind == FormalTemplateKind.SAME_CYCLE_IMPLICATION:
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


def compile_contract_properties(
    structured: list[FormalPropertySpec],
    legacy: list[Any],
    default_clock: str | None = "clk",
    default_reset: str | None = "rst_n:active_low",
) -> tuple[str, list[dict[str, Any]]]:
    """Compile structured properties or safely classify legacy properties."""
    compiled: list[str] = []
    audit: list[dict[str, Any]] = []
    if structured:
        for prop in structured:
            compiled.append(compile_formal_property(prop))
            audit.append({
                "name": prop.name,
                "kind": prop.kind.value,
                "source": "structured_template",
                "supported": True,
            })
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
        compiled.append(compile_formal_property(classified))
        audit.append({
            "name": prop.name,
            "kind": classified.kind.value,
            "source": "legacy_bounded_classifier",
            "supported": True,
        })
    return "\n".join(compiled), audit


def compile_cover_point(prop: FormalPropertySpec) -> tuple[str, str] | None:
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
    guard = _guard(prop, references_reset=references_reset)
    if prop.kind == FormalTemplateKind.SAME_CYCLE_IMPLICATION:
        return (prop.antecedent or "", guard)
    return (f"$past({prop.antecedent})", guard)


__all__ = [
    "FormalTemplateKind",
    "FormalPropertySpec",
    "UnsupportedFormalTemplate",
    "classify_legacy_property",
    "compile_formal_property",
    "compile_contract_properties",
    "compile_cover_point",
]
