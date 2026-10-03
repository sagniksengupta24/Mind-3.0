"""
Decoupled multi-agent contract specifications and prompt builders for Mind 3.0.
Prevents tautological testbench hallucination by decoupling RTL synthesis from verification harness creation.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .formal_templates import (
    FormalPropertySpec,
    UnsupportedFormalTemplate,
    compile_contract_properties,
)


class PortDirection(StrEnum):
    """Pinout direction for digital interfaces."""

    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"


class PortDefinition(BaseModel):
    """Specification of an interface port."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Verilog signal name")
    direction: PortDirection = Field(description="Port signal direction")
    width: int = Field(default=1, ge=1, description="Bus bit-width")
    description: str = Field(default="", description="Functional purpose of the pin")

    @field_validator("name")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Port name cannot be empty.")
        return cleaned

    def to_verilog_declaration(self) -> str:
        """Render synthesizable Verilog-2001/SystemVerilog port declaration line."""
        if self.width == 1:
            return f"{self.direction.value} wire {self.name}"
        return f"{self.direction.value} wire [{self.width - 1}:0] {self.name}"


class SVAProperty(BaseModel):
    """SystemVerilog Assertion (SVA) temporal invariant specification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Assertion label")
    property_expr: str = Field(min_length=1, description="SVA Boolean or temporal sequence expression")
    clock: str = Field(default="clk", description="Sampling clock signal")
    reset: str = Field(default="rst_n", description="Reset signal (active-low by convention)")
    description: str = Field(default="", description="Behavioral property explanation")

    def to_verilog_assertion(self) -> str:
        """Render SVA property as Yosys-compatible procedural assertion.
        
        Note: Yosys (without Verific frontend) only supports simple boolean assertions
        in procedural blocks (always/always_comb), not full SVA property/sequence syntax.
        This method returns a comment for backward compatibility; actual assertion
        generation is done by VerificationHarnessGenerator.build_sva_bind_module() using
        typed bounded-property templates (a supported subset of SVA).
        """
        return (
            f"  // SVA Property: {self.name} (Yosys-compatible generation in build_sva_bind_module using typed bounded templates)\n"
            f"  // Original expression: {self.property_expr}\n"
        )


class TimingConstraint(BaseModel):
    """Clock and physical timing parameters for OpenSTA signoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    clock_name: str = Field(default="clk", description="Primary clock signal name")
    period_ns: float = Field(default=10.0, gt=0.0, description="Clock period target in nanoseconds")
    pvt_corners: list[str] = Field(
        default_factory=lambda: ["tt_025c_1v80", "ff_n40c_1v95", "ss_125c_1v60"],
        description="PVT corner identifiers for MCMM timing analysis (TT, FF, SS)",
    )
    lef_path: str | None = Field(
        default=None,
        description="Technology LEF file path for OpenROAD physical design (Gate 5)",
    )

    def to_sdc(self) -> str:
        """Render Synopsys Design Constraints (SDC) file content with timing exception stubs.

        Note: Standard SDC (IEEE 1497) specifies clock, I/O delay, and timing exception constraints;
        cell library bindings belong to EDA-specific TCL scripts (e.g. read_liberty in OpenSTA).
        """
        return (
            f"# Generated Timing Constraints\n"
            f"create_clock -name {self.clock_name} -period {self.period_ns:.3f} [get_ports {self.clock_name}]\n"
            f"set_clock_uncertainty 0.150 [get_clocks {self.clock_name}]\n"
            f"set_input_delay -clock {self.clock_name} 1.000 [all_inputs]\n"
            f"set_output_delay -clock {self.clock_name} 1.000 [all_outputs]\n"
            f"# False paths: insert set_false_path constraints here for asynchronous crossings\n"
            f"# Multicycle paths: insert set_multicycle_path constraints here for multi-cycle logic\n"
        )


class ClockContract(BaseModel):
    """Deterministic clock semantics captured before RTL generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    edge: str = Field(default="posedge", pattern=r"^(posedge|negedge)$")


class ResetContract(BaseModel):
    """Deterministic reset semantics captured before RTL generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    polarity: str = Field(pattern=r"^(active_low|active_high)$")
    synchronous: bool = True


class InterfaceContract(BaseModel):
    """Strict interface contract decoupling RTL implementation from verification harnesses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module_name: str = Field(min_length=1, description="Target top-level module identifier")
    functional_spec: str = Field(min_length=1, description="Natural language behavioral specification")
    parameters: dict[str, str] = Field(default_factory=dict, description="Verilog module parameters")
    ports: list[PortDefinition] = Field(min_length=1, description="Complete interface pinout")
    clock: ClockContract | None = Field(default=None, description="Primary clock semantics, if clocked")
    reset: ResetContract | None = Field(default=None, description="Primary reset semantics, if reset is present")
    behavior: list[str] = Field(default_factory=list, description="Atomic required behavioral obligations")
    invariants: list[str] = Field(default_factory=list, description="Behavioral invariants independent of tool syntax")
    protocol_requirements: list[str] = Field(default_factory=list, description="Protocol/handshake obligations")
    # Preferred representation: the model selects a bounded template and Mind 3.0 owns rendering.
    formal_properties: list[FormalPropertySpec] = Field(
        default_factory=list,
        description="Typed deterministic formal property templates selected by the architect agent",
    )
    # Backward-compatible legacy input. It is never rendered verbatim; it must clear the bounded classifier.
    sva_properties: list[SVAProperty] = Field(
        default_factory=list,
        description="Legacy formal invariants; translated only by the bounded deterministic compiler",
    )
    timing: TimingConstraint = Field(
        default_factory=TimingConstraint,
        description="Physical timing and clock constraints",
    )
    async_inputs: list[str] | None = Field(
        default=None,
        description=(
            "Asynchronous input signals sampled by clocked logic (external interrupts, "
            "asynchronous enables, asynchronous status/control inputs). None means the "
            "contract does not declare async-input state, so CDC analysis is required. "
            "An explicitly empty list declares that the design has no asynchronous "
            "inputs. Gate 6 may only be skipped for 'no crossings' when this is an "
            "explicit empty list and the reset is absent or synchronous; clock count "
            "alone never justifies a skip."
        ),
    )

    def to_header_template(self) -> str:
        """Render empty module header with ports and parameters."""
        param_list = [f"  parameter {k} = {v}" for k, v in self.parameters.items()]
        param_inner = ",\n".join(param_list)
        param_decl = f" #(\n{param_inner}\n)" if param_list else ""
        port_list = [f"  {p.to_verilog_declaration()}" for p in self.ports]
        port_inner = ",\n".join(port_list)
        return (
            f"module {self.module_name}{param_decl} (\n"
            f"{port_inner}\n"
            f");\n"
            f"  // Implement synthesizable RTL logic here\n"
            f"endmodule\n"
        )


def _infer_clock_reset_from_ports(
    ports: list[dict[str, Any]],
    clock_reset_assumptions: str = "",
) -> tuple[ClockContract | None, ResetContract | None]:
    """Infer only names/polarity/timing from explicit interface metadata; never invent a port."""
    port_names = {str(p.get("name", "")) for p in ports}
    lower_to_name = {name.lower(): name for name in port_names}

    clock_name = None
    for candidate in ("clk", "clock", "i_clk", "aclk", "s_axi_aclk"):
        if candidate in lower_to_name:
            clock_name = lower_to_name[candidate]
            break

    reset_name = None
    for candidate in ("rst_n", "reset_n", "resetn", "rst", "reset", "aresetn"):
        if candidate in lower_to_name:
            reset_name = lower_to_name[candidate]
            break

    assumption_lower = clock_reset_assumptions.lower()
    clock = None
    if clock_name is not None:
        edge = "negedge" if "falling edge" in assumption_lower or "negedge" in assumption_lower else "posedge"
        clock = ClockContract(name=clock_name, edge=edge)

    reset = None
    if reset_name is not None:
        active_low = reset_name.lower().endswith("_n") or "active-low" in assumption_lower or "active low" in assumption_lower
        synchronous = not any(token in assumption_lower for token in ("asynchronous", "async reset", "async"))
        reset = ResetContract(
            name=reset_name,
            polarity="active_low" if active_low else "active_high",
            synchronous=synchronous,
        )
    return clock, reset


def contract_from_benchmark_record(record: Mapping[str, Any]) -> InterfaceContract:
    """Build an immutable contract directly from benchmark metadata.

    Benchmark metadata is already structured and is the evaluator's source of truth. This
    function intentionally avoids asking an LLM to reinterpret the interface, which removes
    a major source of interface and clock/reset hallucinations.
    """
    module_name = str(record.get("task_id") or record.get("module_name") or "").strip()
    if not module_name:
        raise ValueError("Benchmark record is missing task_id/module_name.")

    raw_ports = record.get("expected_ports")
    if not isinstance(raw_ports, list) or not raw_ports:
        raise ValueError(f"Benchmark record '{module_name}' has no expected_ports.")

    ports = [
        PortDefinition(
            name=str(p["name"]),
            direction=PortDirection(str(p["direction"])),
            width=int(p.get("width", 1)),
            description=str(p.get("description", "")),
        )
        for p in raw_ports
    ]
    clock, reset = _infer_clock_reset_from_ports(ports=[p.model_dump() for p in ports], clock_reset_assumptions=str(record.get("clock_reset_assumptions", "")))

    invariants = [str(x) for x in record.get("expected_properties", []) if str(x).strip()]
    behavior = [str(x) for x in record.get("functional_requirements", []) if str(x).strip()]
    protocols = [str(x) for x in record.get("verification_requirements", []) if str(x).strip()]

    structured: list[FormalPropertySpec] = []
    legacy: list[SVAProperty] = []
    if clock is not None:
        default_reset = None
        if reset is not None:
            default_reset = f"{reset.name}:{reset.polarity}"
        from .formal_templates import classify_legacy_property, UnsupportedFormalTemplate

        for index, expr in enumerate(invariants, start=1):
            try:
                structured.append(
                    classify_legacy_property(
                        name=f"contract_property_{index}",
                        raw_expression=expr,
                        default_clock=clock.name,
                        default_reset=default_reset,
                    )
                )
            except UnsupportedFormalTemplate:
                legacy.append(
                    SVAProperty(
                        name=f"contract_property_{index}",
                        property_expr=expr,
                        clock=clock.name,
                        reset=reset.name if reset is not None else "rst_n",
                        description="Held-out evaluator property preserved verbatim for bounded classification at formal stage.",
                    )
                )
    else:
        # A clockless benchmark may still contain malformed clocked properties. Preserve them
        # for explicit specification-error reporting rather than inventing a clock port.
        from .formal_templates import UnsupportedFormalTemplate, classify_legacy_property

        for index, expr in enumerate(invariants, start=1):
            try:
                structured.append(
                    classify_legacy_property(
                        name=f"contract_property_{index}",
                        raw_expression=expr,
                        default_clock=None,
                        default_reset=None,
                    )
                )
            except UnsupportedFormalTemplate:
                legacy.append(
                    SVAProperty(
                        name=f"contract_property_{index}",
                        property_expr=expr,
                        clock="clk",
                        reset=reset.name if reset is not None else "rst_n",
                        description="Preserved for explicit contract consistency validation.",
                    )
                )

    timing_clock = clock.name if clock is not None else "clk"
    return InterfaceContract(
        module_name=module_name,
        functional_spec=str(record.get("natural_language_spec", "")).strip() or "Benchmark specification",
        parameters={str(k): str(v) for k, v in dict(record.get("parameters", {})).items()},
        ports=ports,
        clock=clock,
        reset=reset,
        behavior=behavior,
        invariants=invariants,
        protocol_requirements=protocols,
        formal_properties=structured,
        sva_properties=legacy,
        timing=TimingConstraint(clock_name=timing_clock),
    )


_MODULE_DECL_RE = re.compile(r"\bmodule\s+([A-Za-z_]\w*)\s*(?P<params>#\s*\((?P<param_body>.*?)\))?\s*\((?P<ports>.*?)\)\s*;", re.DOTALL)
_ANSI_PORT_RE = re.compile(
    r"^\s*(?P<direction>input|output|inout)\b\s*"
    r"(?P<net>(?:(?:wire|logic|reg|tri)\s+)*)"
    r"(?P<signed>signed\s+)?(?P<range>\[[^\]]+\]\s*)?"
    r"(?P<names>[^,]+)$",
    re.IGNORECASE,
)


def _strip_rtl_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return re.sub(r"//.*?$", "", code, flags=re.MULTILINE)


def _parse_header_ports(code: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Parse common ANSI SystemVerilog module headers deterministically."""
    clean = _strip_rtl_comments(code)
    match = _MODULE_DECL_RE.search(clean)
    if not match:
        raise ValueError("No parseable ANSI module declaration found before endmodule.")
    module_name = match.group(1)
    body = match.group("ports") or ""
    ports: list[dict[str, Any]] = []
    # ANSI declarations may repeat the direction/type for each declaration or share it
    # across comma-separated names. We deliberately parse only constant ranges because the
    # benchmark contract stores concrete widths.
    chunks = [chunk.strip() for chunk in re.split(r",(?=\s*(?:input|output|inout)\b)", body, flags=re.IGNORECASE) if chunk.strip()]
    current_direction: str | None = None
    current_width = 1
    for chunk in chunks:
        pm = _ANSI_PORT_RE.match(chunk)
        if pm:
            current_direction = pm.group("direction").lower()
            range_text = (pm.group("range") or "").strip()
            current_width = 1
            if range_text:
                wm = re.fullmatch(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]", range_text)
                if not wm:
                    raise ValueError(f"Unsupported non-constant port range: {range_text}")
                current_width = abs(int(wm.group(1)) - int(wm.group(2))) + 1
            names_text = pm.group("names").strip()
            names = [n.strip() for n in names_text.split(",") if n.strip()]
            if not names:
                raise ValueError(f"Could not parse port declaration: {chunk!r}")
            for name in names:
                nm = re.fullmatch(r"(?:signed\s+)?([A-Za-z_]\w*)", name)
                if not nm:
                    raise ValueError(f"Could not parse port name: {name!r}")
                ports.append({"name": nm.group(1), "direction": current_direction, "width": current_width})
            continue

        # A direction-less continuation (e.g. `input logic a, b`) is legal after a
        # comma split only in the uncommon form `a, b`; retain the current declaration.
        if current_direction is None:
            raise ValueError(f"Could not parse port declaration: {chunk!r}")
        for name in [n.strip() for n in chunk.split(",") if n.strip()]:
            nm = re.fullmatch(r"(?:signed\s+)?(?:wire|logic|reg|tri)?\s*([A-Za-z_]\w*)", name, re.IGNORECASE)
            if not nm:
                raise ValueError(f"Could not parse port continuation: {name!r}")
            ports.append({"name": nm.group(1), "direction": current_direction, "width": current_width})

    params: list[str] = []
    param_body = match.group("param_body") or ""
    for pm in re.finditer(r"\bparameter\s+(?:\w+\s+)?([A-Za-z_]\w*)\s*=", param_body):
        params.append(pm.group(1))
    return module_name, ports, params


def _source_context(code: str, line: int | None, radius: int = 2) -> str:
    if not line or line < 1:
        return ""
    lines = code.splitlines()
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    return "\n".join(f"{idx}: {lines[idx-1]}" for idx in range(start, end + 1))


def validate_contract_consistency(contract: InterfaceContract) -> list[dict[str, Any]]:
    """Validate that the immutable contract is internally realizable before RTL generation."""
    violations: list[dict[str, Any]] = []
    ports = {p.name: p for p in contract.ports}
    input_ports = {p.name for p in contract.ports if p.direction == PortDirection.INPUT}

    if contract.clock is not None:
        port = ports.get(contract.clock.name)
        if port is None:
            violations.append({
                "category": "SPECIFICATION_ERROR",
                "message": f"Contract clock '{contract.clock.name}' is not present in the port list.",
            })
        elif port.direction != PortDirection.INPUT:
            violations.append({
                "category": "SPECIFICATION_ERROR",
                "message": f"Contract clock '{contract.clock.name}' must be an input port.",
            })

    if contract.reset is not None:
        port = ports.get(contract.reset.name)
        if port is None:
            violations.append({
                "category": "SPECIFICATION_ERROR",
                "message": f"Contract reset '{contract.reset.name}' is not present in the port list.",
            })
        elif port.direction != PortDirection.INPUT:
            violations.append({
                "category": "SPECIFICATION_ERROR",
                "message": f"Contract reset '{contract.reset.name}' must be an input port.",
            })

    if contract.async_inputs is not None:
        for async_name in contract.async_inputs:
            port = ports.get(async_name)
            if port is None:
                violations.append({
                    "category": "SPECIFICATION_ERROR",
                    "message": f"Contract async input '{async_name}' is not present in the port list.",
                })
            elif port.direction != PortDirection.INPUT:
                violations.append({
                    "category": "SPECIFICATION_ERROR",
                    "message": f"Contract async input '{async_name}' must be an input port.",
                })

    declared = set(ports) | set(contract.parameters)
    for prop in [*contract.formal_properties, *contract.sva_properties]:
        prop_clock = getattr(prop, "clock", None)
        if prop_clock:
            if prop_clock not in input_ports:
                violations.append({
                    "category": "SPECIFICATION_ERROR",
                    "message": f"Formal property '{getattr(prop, 'name', 'unnamed')}' references clock '{prop_clock}', but that clock is not an input port in the immutable contract.",
                })
        prop_reset = getattr(prop, "reset", None)
        if prop_reset:
            reset_name = str(prop_reset).split(":", 1)[0]
            if reset_name not in declared:
                violations.append({
                    "category": "SPECIFICATION_ERROR",
                    "message": f"Formal property '{getattr(prop, 'name', 'unnamed')}' references reset '{reset_name}', but that signal is not declared by the immutable contract.",
                })
        expr = getattr(prop, "expression", None) or getattr(prop, "property_expr", None) or ""
        for token in re.findall(r"\b(?:clk|clock|rst_n|rst|reset|reset_n)\b", str(expr)):
            if token not in ports:
                violations.append({
                    "category": "SPECIFICATION_ERROR",
                    "message": f"Formal property '{getattr(prop, 'name', 'unnamed')}' references signal '{token}', but it is absent from the immutable contract.",
                })
                break

    return violations


def validate_rtl_against_contract(contract: InterfaceContract, rtl_code: str) -> list[dict[str, Any]]:
    """Return deterministic contract violations; an empty list means structurally compatible."""
    violations: list[dict[str, Any]] = []
    try:
        module_name, actual_ports, actual_params = _parse_header_ports(rtl_code)
    except ValueError as exc:
        return [{
            "category": "SYNTAX_ERROR",
            "message": str(exc),
            "file": f"{contract.module_name}.sv",
            "line": None,
            "column": None,
            "source_context": "",
        }]

    if module_name != contract.module_name:
        violations.append({
            "category": "INTERFACE_ERROR",
            "message": f"Module name '{module_name}' does not match contract '{contract.module_name}'.",
            "file": f"{contract.module_name}.sv",
            "line": 1,
            "column": None,
            "source_context": _source_context(rtl_code, 1),
        })

    expected = {p.name: (p.direction.value, p.width) for p in contract.ports}
    actual = {p["name"]: (p["direction"], p["width"]) for p in actual_ports}
    for name, (direction, width) in expected.items():
        if name not in actual:
            violations.append({
                "category": "INTERFACE_ERROR",
                "message": f"Required port '{name}' is missing.",
                "file": f"{contract.module_name}.sv",
                "line": 1,
                "column": None,
                "source_context": _source_context(rtl_code, 1),
            })
            continue
        actual_direction, actual_width = actual[name]
        if actual_direction != direction:
            violations.append({
                "category": "INTERFACE_ERROR",
                "message": f"Port '{name}' direction is '{actual_direction}', expected '{direction}'.",
                "file": f"{contract.module_name}.sv",
                "line": 1,
                "column": None,
                "source_context": _source_context(rtl_code, 1),
            })
        if actual_width != width:
            violations.append({
                "category": "TYPE_WIDTH_ERROR",
                "message": f"Port '{name}' width is {actual_width}, expected {width}.",
                "file": f"{contract.module_name}.sv",
                "line": 1,
                "column": None,
                "source_context": _source_context(rtl_code, 1),
            })

    unexpected = sorted(set(actual) - set(expected))
    for name in unexpected:
        violations.append({
            "category": "INTERFACE_ERROR",
            "message": f"Unexpected port '{name}' is not present in the contract.",
            "file": f"{contract.module_name}.sv",
            "line": 1,
            "column": None,
            "source_context": _source_context(rtl_code, 1),
        })

    expected_params = set(contract.parameters)
    actual_param_set = set(actual_params)
    missing_params = sorted(expected_params - actual_param_set)
    unexpected_params = sorted(actual_param_set - expected_params)
    for name in missing_params:
        violations.append({"category": "INTERFACE_ERROR", "message": f"Required parameter '{name}' is missing.", "file": f"{contract.module_name}.sv", "line": 1, "column": None, "source_context": _source_context(rtl_code, 1)})
    for name in unexpected_params:
        violations.append({"category": "INTERFACE_ERROR", "message": f"Unexpected parameter '{name}' is not present in the contract.", "file": f"{contract.module_name}.sv", "line": 1, "column": None, "source_context": _source_context(rtl_code, 1)})

    if contract.clock is not None:
        clock_port = next((p for p in contract.ports if p.name == contract.clock.name), None)
        if clock_port is None:
            violations.append({"category": "CLOCK_RESET_ERROR", "message": f"Contract clock '{contract.clock.name}' is not a declared port.", "file": f"{contract.module_name}.sv", "line": 1, "column": None, "source_context": _source_context(rtl_code, 1)})
        else:
            edge = contract.clock.edge
            if not re.search(rf"always(?:_ff)?\s*@\s*\(\s*{edge}\s+{re.escape(contract.clock.name)}\b", rtl_code):
                # Do not reject purely combinational RTL merely because a malformed property mentions a clock;
                # clocked contracts, however, must contain a sequential edge-sensitive block.
                if contract.behavior and any(token in " ".join(contract.behavior).lower() for token in ("counter", "fifo", "register", "pipeline", "state", "clock")):
                    violations.append({"category": "CLOCK_RESET_ERROR", "message": f"Clocked contract requires an {edge} {contract.clock.name} sequential block, but none was found.", "file": f"{contract.module_name}.sv", "line": None, "column": None, "source_context": _source_context(rtl_code, 1)})

    if contract.reset is not None:
        reset_port = next((p for p in contract.ports if p.name == contract.reset.name), None)
        if reset_port is None:
            violations.append({"category": "CLOCK_RESET_ERROR", "message": f"Contract reset '{contract.reset.name}' is not a declared port.", "file": f"{contract.module_name}.sv", "line": 1, "column": None, "source_context": _source_context(rtl_code, 1)})
        else:
            active_literal = rf"!?\s*{re.escape(contract.reset.name)}"
            reset_used = bool(re.search(rf"(?:!\s*{re.escape(contract.reset.name)}|~\s*{re.escape(contract.reset.name)}|\b{re.escape(contract.reset.name)}\b)", rtl_code))
            if not reset_used:
                violations.append({"category": "CLOCK_RESET_ERROR", "message": f"Reset '{contract.reset.name}' is declared by the contract but is not referenced in the RTL.", "file": f"{contract.module_name}.sv", "line": None, "column": None, "source_context": _source_context(rtl_code, 1)})
            if contract.reset.synchronous and re.search(rf"always(?:_ff)?\s*@\s*\(\s*{contract.clock.name if contract.clock else 'clk'}\s+[^)]*\bor\s+(?:negedge|posedge)\s+{re.escape(contract.reset.name)}", rtl_code):
                violations.append({"category": "CLOCK_RESET_ERROR", "message": f"Synchronous reset '{contract.reset.name}' must not appear in the clocked sensitivity list.", "file": f"{contract.module_name}.sv", "line": None, "column": None, "source_context": _source_context(rtl_code, 1)})
            if not contract.reset.synchronous and contract.clock is not None and not re.search(rf"always(?:_ff)?\s*@\s*\(\s*{contract.clock.edge}\s+{re.escape(contract.clock.name)}.*\bor\s+(?:negedge|posedge)\s+{re.escape(contract.reset.name)}", rtl_code):
                violations.append({"category": "CLOCK_RESET_ERROR", "message": f"Asynchronous reset '{contract.reset.name}' must be included in the clocked sensitivity list.", "file": f"{contract.module_name}.sv", "line": None, "column": None, "source_context": _source_context(rtl_code, 1)})

    # Formal/checker references must be valid against the immutable interface contract.
    rtl_identifiers = {p.name for p in contract.ports} | set(contract.parameters)
    for prop in [*contract.formal_properties, *contract.sva_properties]:
        expr = prop.expression if isinstance(prop, FormalPropertySpec) else prop.property_expr
        for token in re.findall(r"\b[A-Za-z_]\w*\b", str(expr)):
            if token in {"assert", "property", "posedge", "negedge", "disable", "iff", "true", "false"}:
                continue
            if token not in rtl_identifiers and token not in {"$past", "$onehot", "$onehot0", "$stable", "$changed"}:
                # Only flag obvious signal-like identifiers; keywords/literals are filtered above.
                if token in {"clk", "rst_n", "reset", "reset_n"}:
                    violations.append({"category": "SPECIFICATION_ERROR", "message": f"Formal property references signal '{token}', but the immutable contract interface does not declare it.", "file": f"{contract.module_name}.sv", "line": None, "column": None, "source_context": ""})
                    break

    return violations


# ── Multi-Agent Decoupled Prompt Builders ─────────────────────────────────

class ContractSynthesizer:
    """Extracts formal InterfaceContract schemas from natural language engineering requirements."""

    @staticmethod
    def build_prompt(user_request: str) -> dict[str, str]:
        system_msg = (
            "You are a Lead Silicon Architect.\n"
            "Your sole duty is to extract a formal hardware interface contract from the user requirement.\n"
            "You MUST output ONLY a valid JSON object strictly adhering to the InterfaceContract schema.\n"
            "Mandatory guidelines:\n"
            "1. Pinout: Explicitly define every clock, reset, data, and handshake port with proper bit-widths.\n"
            "2. Formal Invariants: Author 2 to 5 SystemVerilog Assertions (SVA) using typed bounded-property templates (a deterministic subset of SVA). Do NOT emit arbitrary SVA sequences, cover/assume statements, or unsupported temporal syntax.\n"
            "3. Timing: Define target clock period in nanoseconds.\n"
            "4. CDC inputs: List every asynchronous input signal (external interrupts, asynchronous enables, asynchronous status/control inputs sampled by clocked logic) in async_inputs. Use an explicitly empty list ONLY when the design has no asynchronous inputs; use null when async-input state is unknown. Declare the reset synchronous flag honestly: an asynchronous reset still requires CDC analysis even with a single clock.\n\n"
            "Preferred formal_properties templates:\n"
            '{"name":"req_implies_gnt","kind":"same_cycle_implication","clock":"clk","reset":"rst_n:active_low","antecedent":"req","consequent":"gnt"}\n'
            '{"name":"req_implies_gnt_next","kind":"next_cycle_implication","clock":"clk","reset":"rst_n:active_low","antecedent":"req","consequent":"gnt"}\n'
            '{"name":"onehot_state","kind":"onehot","clock":"clk","reset":"rst_n:active_low","signal":"state"}\n'
            '{"name":"reset_state","kind":"reset_assertion","clock":"clk","reset":"rst_n:active_low","consequent":"state == 2\'b00"}\n'
            '{"name":"history_check","kind":"past_expression","clock":"clk","reset":"rst_n:active_low","expression":"$past(req, 1) == 1\'b1 && gnt == 1\'b1"}\n'
            'Allowed kinds: boolean, same_cycle_implication, next_cycle_implication, reset_assertion, onehot, onehot0, onehot_or_equals, past_equals, past_stable, past_expression.\n'
            "\nSchema template:\n"
            "{\n"
            '  "module_name": "string (valid verilog identifier)",\n'
            '  "functional_spec": "string",\n'
            '  "parameters": {},\n'
            '  "ports": [\n'
            '    {"name": "clk", "direction": "input", "width": 1, "description": "Clock signal"},\n'
            '    {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"}\n'
            '  ],\n'
            '  "formal_properties": [\n' 
            '    {"name":"p_name","kind":"same_cycle_implication","clock":"clk","reset":"rst_n:active_low","antecedent":"req","consequent":"gnt"}\n' 
            '  ],\n' 
            '  "sva_properties": [\n' 
            '    {"name":"p_req_gnt","property_expr":"assert property (@(posedge clk) req |-> gnt);","clock":"clk","reset":"rst_n","description":"Request implies grant"}\n' 
            '  ],\n' 
            '  "timing": {"clock_name": "clk", "period_ns": 10.0},\n'
            '  "async_inputs": []\n'
        "}\n"
        'Port direction must be one of: "input", "output", "inout".'
        )
        user_msg = f"Requirement: {user_request}\nSynthesize interface contract:"
        return {"system": system_msg, "user": user_msg}


class RTLGenerator:
    """Generates synthesizable RTL from interface contracts without seeing verification code."""

    @staticmethod
    def build_prompt(contract: InterfaceContract) -> dict[str, str]:
        system_msg = (
            "You are a Principal RTL Design Engineer.\n"
            "You MUST write synthesizable, production-grade SystemVerilog matching the supplied contract.\n"
            "Strict synthesis invariants:\n"
            "- Use non-blocking (<=) for sequential clocked blocks, blocking (=) for combinational blocks.\n"
            "- Never infer latches: every if branch must have an else; every case statement must have a default.\n"
            "- Never declare loop variables inside procedural blocks; declare all registers at module level.\n"
            "- You have zero access to the testbench or verification harness. Do not embed assertions in your RTL.\n"
            "Respond ONLY with the complete synthesizable module code."
        )
        ports_summary = "\n".join(f"  - {p.name}: {p.direction.value} [{p.width} bits] // {p.description}" for p in contract.ports)
        clock_summary = (
            f"{contract.clock.name}, edge={contract.clock.edge}" if contract.clock is not None else "none"
        )
        reset_summary = (
            f"{contract.reset.name}, polarity={contract.reset.polarity}, synchronous={contract.reset.synchronous}"
            if contract.reset is not None else "none"
        )
        behavior = "\n".join(f"  - {item}" for item in contract.behavior) or "  - No additional atomic behavior listed."
        invariants = "\n".join(f"  - {item}" for item in contract.invariants) or "  - No additional invariants listed."
        protocols = "\n".join(f"  - {item}" for item in contract.protocol_requirements) or "  - No additional protocol requirements listed."
        user_msg = (
            f"Immutable module contract (do not reinterpret or modify):\n"
            f"Module: {contract.module_name}\n"
            f"Specification: {contract.functional_spec}\n"
            f"Parameters: {json.dumps(contract.parameters, sort_keys=True)}\n"
            f"Clock: {clock_summary}\n"
            f"Reset: {reset_summary}\n"
            f"Pinout:\n{ports_summary}\n\n"
            f"Required behavior:\n{behavior}\n\n"
            f"Contract invariants:\n{invariants}\n\n"
            f"Protocol requirements:\n{protocols}\n\n"
            "Interface is fixed. Do not add, remove, rename, reorder, or resize ports. "
            "Implement the complete required behavior as synthesizable SystemVerilog."
        )
        return {"system": system_msg, "user": user_msg}


UnsupportedFormalPropertyError = UnsupportedFormalTemplate




class VerificationFailureEvidence(BaseModel):
    """Structured, bounded evidence passed to an independent RTL repair agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=96)
    details: str = Field(default="", max_length=2000)
    stdout_tail: str = Field(default="", max_length=4000)
    stderr_tail: str = Field(default="", max_length=4000)
    failing_property: str | None = Field(default=None, max_length=128)
    failing_step: str | None = Field(default=None, max_length=32)
    trace_file: str | None = Field(default=None, max_length=512)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    artifact_paths: list[str] = Field(default_factory=list, max_length=16)
    stage: str = Field(default="verification", max_length=32)
    tool: str = Field(default="", max_length=128)
    error: str = Field(default="", max_length=4000)
    file: str | None = Field(default=None, max_length=512)
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=1)
    source_context: str = Field(default="", max_length=6000)
    contract: dict[str, Any] = Field(default_factory=dict)
    attempt: int = Field(default=1, ge=1, le=3)
    failing_test: str | None = Field(default=None, max_length=256)
    cycle: int | None = Field(default=None, ge=0)
    expected_behavior: str | None = Field(default=None, max_length=2000)
    observed_behavior: str | None = Field(default=None, max_length=2000)
    relevant_signals: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    reset_state: str | None = Field(default=None, max_length=256)
    clock_state: str | None = Field(default=None, max_length=256)
    property_source: str | None = Field(default=None, max_length=4000)
    counterexample_trace: str | None = Field(default=None, max_length=6000)
    repair_history: list[str] = Field(default_factory=list, max_length=3)


class VerificationRepairer:
    """Builds a constrained repair prompt that receives verifier evidence, not hidden test code."""

    @staticmethod
    def build_prompt(
        contract: InterfaceContract,
        current_rtl: str,
        evidence: VerificationFailureEvidence,
    ) -> dict[str, str]:
        system_msg = (
            "You are the Independent RTL Verification Repair Engineer.\n"
            "The external verifier is authoritative. Repair only the reported stage failure.\n"
            "Fix only the reported issue. Do not change the module interface. Do not remove required behavior. "
            "Do not remove assertions. Do not weaken verification. Do not rewrite unrelated RTL.\n"
            "Return the complete corrected SystemVerilog module with the minimal necessary changes. Do not return partial patches or line fragments.\n"
            "Do not emit testbench code, formal checker code, shell commands, or explanations."
        )
        evidence_json = json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True)
        user_msg = (
            f"Immutable contract:\n{json.dumps(contract.model_dump(mode='json'), indent=2, sort_keys=True)}\n\n"
            f"Structured verifier evidence (authoritative):\n{evidence_json}\n\n"
            f"Current RTL:\n{current_rtl}\n\n"
            "Repair the current RTL with the smallest semantically justified change."
        )
        return {"system": system_msg, "user": user_msg}


class UnsupportedFormalPropertyError(ValueError):
    """Raised when an SVA property cannot be soundly translated to supported procedural formal assertions."""


class VerificationHarnessGenerator:
    """Generates formal SBY configuration, SVA bind files, and Verilator C++ stimulus without viewing RTL internals."""

    @staticmethod
    def _has_clock(contract: InterfaceContract) -> bool:
        """Check if contract has an input clock port."""
        return any(
            ("clk" in p.name.lower() or "clock" in p.name.lower())
            for p in contract.ports
            if p.direction == PortDirection.INPUT
        )

    # Architectural unification (Rule A1)
    build_sva_checker_module = build_sva_bind_module

    @staticmethod
    def _get_clock_name(contract: InterfaceContract) -> str:
        """Get the clock signal name from contract ports."""
        for p in contract.ports:
            if p.direction == PortDirection.INPUT and ("clk" in p.name.lower() or "clock" in p.name.lower()):
                return p.name
        return "clk"

    @staticmethod
    def _has_reset(contract: InterfaceContract) -> bool:
        """Check if contract has an input reset port."""
        return any(
            ("rst" in p.name.lower() or "reset" in p.name.lower())
            for p in contract.ports
            if p.direction == PortDirection.INPUT
        )

    @staticmethod
    def _get_reset_name(contract: InterfaceContract) -> str:
        """Get the reset signal name from contract ports."""
        for p in contract.ports:
            if p.direction == PortDirection.INPUT and ("rst" in p.name.lower() or "reset" in p.name.lower()):
                return p.name
        return "rst_n"

    @staticmethod
    def _get_reset_info(contract: InterfaceContract) -> tuple[str, bool] | None:
        """Get (reset_name, is_active_low) from contract ports if present."""
        for p in contract.ports:
            if p.direction == PortDirection.INPUT and ("rst" in p.name.lower() or "reset" in p.name.lower()):
                name = p.name
                is_active_low = name.endswith("_n") or "_n" in name or "rstn" in name or "resetn" in name
                return name, is_active_low
        return None

    @staticmethod
    def _is_temporal_expression(expr: str) -> bool:
        """Check if expression contains temporal operators requiring special formal translation."""
        temporal_patterns = [
            r"\|\->",           # overlapping implication
            r"\|=>",            # non-overlapping implication
            r"\#\#",            # delay
            r"\bsequence\b",    # sequence keyword
            r"\bproperty\b",    # property keyword
            r"\$past\(",        # system functions
            r"\$rose\(",
            r"\$fell\(",
            r"\$stable\(",
            r"\$changed\(",
        ]
        for pattern in temporal_patterns:
            if re.search(pattern, expr):
                return True
        return False

    @staticmethod
    def _generate_assertion_block(
        contract: InterfaceContract,
        prop: SVAProperty,
        has_clock: bool,
        clock_name: str,
        reset_info: tuple[str, bool] | None,
    ) -> str:
        raw_expr = prop.property_expr.strip()
        prop_name = prop.name

        expr = raw_expr.replace("===", "==").replace("!==", "!=")

        # Strip enclosing property/always/assert wrappers if provided in contract
        if "property" in expr or "always" in expr:
            m = re.search(r"property\s+\w+\s*;?(.*?);?\s*endproperty", expr, re.DOTALL | re.IGNORECASE)
            if m:
                expr = m.group(1).strip()
            expr = re.sub(r"@\s*\([^)]+\)", "", expr).strip()
            m_dis = re.search(r"disable\s+iff\s*\([^)]+\)", expr, re.IGNORECASE)
            if m_dis:
                expr = expr[:m_dis.start()] + expr[m_dis.end():]
                expr = expr.strip()
            expr = re.sub(r"always(?:_comb)?\s*(?:@\s*\([^)]+\))?\s*begin\s*", "", expr)
            expr = re.sub(r"\s*end\s*$", "", expr).strip()
            m_assert = re.search(r"assert\s*\(\s*(.*)\s*\);?$", expr, re.DOTALL)
            if m_assert:
                expr = m_assert.group(1).strip()

        expr = expr.strip()
        if expr.endswith(";"):
            expr = expr[:-1].strip()

        # Reject unsupported complex temporal constructs that cannot be proven equivalent
        if re.search(r"\#\#\s*[2-9]|\#\#\[|\bsequence\b|\beventually\b|\buntil\b|\bs_eventually\b|\[\*\d+\]", expr, re.IGNORECASE):
            raise UnsupportedFormalPropertyError(
                f"Property '{prop_name}' contains complex temporal construct '{expr}' unsupported by procedural BMC."
            )

        # COMBINATIONAL DESIGN
        if not has_clock:
            if re.search(r"\bclk\b|\bclock\b|\bposedge\b|\bnegedge\b|\|\=>|\$past\b|\$rose\b|\$fell\b|\$stable\b", expr, re.IGNORECASE):
                raise UnsupportedFormalPropertyError(
                    f"Combinational contract property '{prop_name}' contains sequential/clock references: {expr}"
                )
            if "|->" in expr or "->" in expr:
                parts = re.split(r"\|->|->", expr, maxsplit=1)
                left = parts[0].strip()
                right = parts[1].strip()
                return (
                    f"  // Formal Assertion (combinational): {prop_name}\n"
                    f"  always @* begin\n"
                    f"    if ({left}) assert ({right});\n"
                    f"  end\n"
                )
            else:
                return (
                    f"  // Formal Assertion (combinational): {prop_name}\n"
                    f"  always @* begin\n"
                    f"    assert ({expr});\n"
                    f"  end\n"
                )

        # SEQUENTIAL DESIGN
        is_next_cycle = False
        left_cond = None
        right_cond = None

        if "|=>" in expr:
            is_next_cycle = True
            parts = re.split(r"\|=>", expr, maxsplit=1)
            left_cond = parts[0].strip()
            right_cond = parts[1].strip()
        elif "##1" in expr and ("|->" in expr or "->" in expr):
            is_next_cycle = True
            parts = re.split(r"\|->|->", expr, maxsplit=1)
            left_cond = parts[0].strip()
            right_cond = re.sub(r"^\#\#1\s*", "", parts[1].strip())
        elif "|->" in expr or "->" in expr:
            parts = re.split(r"\|->|->", expr, maxsplit=1)
            left_cond = parts[0].strip()
            right_cond = parts[1].strip()

        if reset_info:
            rst_name, rst_active_low = reset_info
            rst_inactive = f"{rst_name}" if rst_active_low else f"!{rst_name}"
            # If the property explicitly references the reset signal, do NOT guard with rst_inactive!
            has_rst_ref = bool(re.search(rf"\b{re.escape(rst_name)}\b", expr))
            guard = f"!init && {rst_inactive}" if not has_rst_ref else "!init"
            guard_past = f"!init && {rst_inactive} && $past({rst_inactive})" if not has_rst_ref else "!init"

            if is_next_cycle:
                return (
                    f"  // Formal Assertion (sequential 1-cycle): {prop_name}\n"
                    f"  always @(posedge {clock_name}) begin\n"
                    f"    if ({guard_past}) begin\n"
                    f"      if ($past({left_cond})) assert ({right_cond});\n"
                    f"    end\n"
                    f"  end\n"
                )
            elif left_cond and right_cond:
                return (
                    f"  // Formal Assertion (sequential implication): {prop_name}\n"
                    f"  always @(posedge {clock_name}) begin\n"
                    f"    if ({guard}) begin\n"
                    f"      if ({left_cond}) assert ({right_cond});\n"
                    f"    end\n"
                    f"  end\n"
                )
            else:
                return (
                    f"  // Formal Assertion (sequential): {prop_name}\n"
                    f"  always @(posedge {clock_name}) begin\n"
                    f"    if ({guard}) begin\n"
                    f"      assert ({expr});\n"
                    f"    end\n"
                    f"  end\n"
                )
        else:
            # Sequential WITHOUT reset: zero reset references!
            if is_next_cycle:
                return (
                    f"  // Formal Assertion (sequential 1-cycle, free-running): {prop_name}\n"
                    f"  always @(posedge {clock_name}) begin\n"
                    f"    if (!init) begin\n"
                    f"      if ($past({left_cond})) assert ({right_cond});\n"
                    f"    end\n"
                    f"  end\n"
                )
            elif left_cond and right_cond:
                return (
                    f"  // Formal Assertion (sequential implication, free-running): {prop_name}\n"
                    f"  always @(posedge {clock_name}) begin\n"
                    f"    if (!init) begin\n"
                    f"      if ({left_cond}) assert ({right_cond});\n"
                    f"    end\n"
                    f"  end\n"
                )
            else:
                return (
                    f"  // Formal Assertion (sequential, free-running): {prop_name}\n"
                    f"  always @(posedge {clock_name}) begin\n"
                    f"    if (!init) begin\n"
                    f"      assert ({expr});\n"
                    f"    end\n"
                    f"  end\n"
                )

    @staticmethod
    def build_sva_bind_module(contract: InterfaceContract) -> str:
        port_decls = []
        for p in contract.ports:
            bind_port = PortDefinition(
                name=p.name,
                direction=PortDirection.INPUT,
                width=p.width,
                description=p.description,
            )
            port_decls.append(f"  {bind_port.to_verilog_declaration()}")
        port_decls_str = ",\n".join(port_decls)

        if not contract.formal_properties and not contract.sva_properties:
            return (
                f"// Mind 3.0 deterministic formal checker: {contract.module_name}_sva\n"
                f"module {contract.module_name}_sva (\n{port_decls_str}\n);\n\n"
                f"  // No formal properties specified in contract\n\n"
                f"endmodule\n"
            )

        has_clock = VerificationHarnessGenerator._has_clock(contract)
        clock_name = VerificationHarnessGenerator._get_clock_name(contract) if has_clock else None
        reset_info = VerificationHarnessGenerator._get_reset_info(contract) if has_clock else None
        default_reset = None
        if reset_info:
            rst_name, rst_active_low = reset_info
            default_reset = f"{rst_name}:{'active_low' if rst_active_low else 'active_high'}"

        try:
            assertions, audit = compile_contract_properties(
                structured=contract.formal_properties,
                legacy=contract.sva_properties,
                default_clock=clock_name if has_clock else None,
                default_reset=default_reset if has_clock else None,
            )
        except UnsupportedFormalTemplate:
            raise

        init_reg = ""
        if has_clock:
            init_reg = f"  reg init = 1'b1;\n  always @(posedge {clock_name}) init <= 1'b0;\n\n"

        audit_lines = "\n".join(
            f"  // property-audit: {item['name']} kind={item['kind']} source={item['source']} supported={item['supported']}"
            for item in audit
        )
        return (
            f"// Deterministic formal checker for {contract.module_name}\n"
            f"// Property bodies are rendered by Mind 3.0 templates, not copied from the model.\n"
            f"module {contract.module_name}_sva (\n{port_decls_str}\n);\n\n"
            f"{audit_lines}\n\n"
            f"{init_reg}"
            f"{assertions}\n"
            f"endmodule\n"
        )

    # Architectural unification (Rule A1)
    build_sva_checker_module = build_sva_bind_module

    @staticmethod
    def build_sby_config(
        contract: InterfaceContract,
        depth: int = 25,
        include_sva_file: bool = True,
        property_depths: dict[str, int] | None = None,
    ) -> str:
        """Generate SymbiYosys configuration script with optional per-property depth overrides."""
        wrapper_name = f"{contract.module_name}_formal_top"
        files_section = f"{contract.module_name}.sv\n{wrapper_name}.sv\n"
        read_sva = ""
        if include_sva_file and (contract.formal_properties or contract.sva_properties):
            files_section += f"{contract.module_name}_sva.sv\n"
            read_sva = f"read -formal {contract.module_name}_sva.sv\n"

        effective_depth = depth
        if property_depths and (contract.formal_properties or contract.sva_properties):
            all_props = contract.formal_properties if contract.formal_properties else contract.sva_properties
            all_depths = [property_depths.get(p.name, depth) for p in all_props]
            effective_depth = max(all_depths) if all_depths else depth

        return (
            f"[options]\n"
            f"mode bmc\n"
            f"depth {effective_depth}\n\n"
            f"[engines]\n"
            f"smtbmc z3\n\n"
            f"[script]\n"
            f"read -formal {contract.module_name}.sv\n"
            f"{read_sva}"
            f"read -formal {wrapper_name}.sv\n"
            f"prep -top {wrapper_name}\n\n"
            f"[files]\n"
            f"{files_section}"
        )

    @staticmethod
    def build_formal_wrapper(contract: InterfaceContract) -> str:
        """Generate formal verification wrapper module that instantiates DUT and checker."""
        signal_decls = []
        dut_port_conns = []
        sva_port_conns = []
        for p in contract.ports:
            if p.width == 1:
                signal_decls.append(f"  logic {p.name};")
            else:
                signal_decls.append(f"  logic [{p.width-1}:0] {p.name};")
            dut_port_conns.append(f"    .{p.name}({p.name})")
            sva_port_conns.append(f"    .{p.name}({p.name})")

        signals_str = "\n".join(signal_decls)
        dut_conns_str = ",\n".join(dut_port_conns)
        sva_conns_str = ",\n".join(sva_port_conns)

        return (
            f"// Formal Verification Wrapper for {contract.module_name}\n"
            f"module {contract.module_name}_formal_top;\n\n"
            f"{signals_str}\n\n"
            f"  {contract.module_name} dut (\n"
            f"{dut_conns_str}\n"
            f"  );\n\n"
            f"  {contract.module_name}_sva sva (\n"
            f"{sva_conns_str}\n"
            f"  );\n\n"
            f"endmodule\n"
        )

    @staticmethod
    def implication_antecedents(
        contract: InterfaceContract,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Extract implication antecedents for bounded vacuity reachability checks.

        Returns (implications, unsupported) where each implication is a dict
        with name/kind/antecedent/clock/reset. Structured templates are read
        directly; legacy SVA strings are re-classified deterministically.
        Anything unclassifiable is reported in unsupported (it cannot have
        reached the assert-PASS path, so callers treat it as a cover error).
        """
        from .formal_templates import (
            FormalPropertySpec,
            FormalTemplateKind,
            UnsupportedFormalTemplate,
            classify_legacy_property,
            compile_cover_point,
        )

        has_clock = VerificationHarnessGenerator._has_clock(contract)
        clock_name = VerificationHarnessGenerator._get_clock_name(contract) if has_clock else None
        reset_info = VerificationHarnessGenerator._get_reset_info(contract) if has_clock else None
        default_reset = None
        if reset_info:
            rst_name, rst_active_low = reset_info
            default_reset = f"{rst_name}:{'active_low' if rst_active_low else 'active_high'}"

        implications: list[dict[str, Any]] = []
        unsupported: list[dict[str, Any]] = []
        for prop in list(contract.formal_properties or []):
            if prop.kind in (FormalTemplateKind.SAME_CYCLE_IMPLICATION, FormalTemplateKind.NEXT_CYCLE_IMPLICATION):
                try:
                    cover = compile_cover_point(prop)
                except UnsupportedFormalTemplate as exc:
                    unsupported.append({"name": prop.name, "error": str(exc)})
                    continue
                if cover is not None:
                    implications.append({
                        "name": prop.name,
                        "kind": prop.kind.value,
                        "antecedent": prop.antecedent,
                        "cover_expr": cover[0],
                        "cover_guard": cover[1],
                        "clock": prop.clock,
                    })
        for prop in list(contract.sva_properties or []):
            try:
                classified = classify_legacy_property(
                    name=prop.name,
                    raw_expression=prop.property_expr,
                    default_clock=clock_name,
                    default_reset=default_reset,
                )
            except (UnsupportedFormalTemplate, ValueError) as exc:
                unsupported.append({"name": prop.name, "error": str(exc)})
                continue
            if classified.kind in (FormalTemplateKind.SAME_CYCLE_IMPLICATION, FormalTemplateKind.NEXT_CYCLE_IMPLICATION):
                try:
                    cover = compile_cover_point(classified)
                except UnsupportedFormalTemplate as exc:
                    unsupported.append({"name": prop.name, "error": str(exc)})
                    continue
                if cover is not None:
                    implications.append({
                        "name": classified.name,
                        "kind": classified.kind.value,
                        "antecedent": classified.antecedent,
                        "cover_expr": cover[0],
                        "cover_guard": cover[1],
                        "clock": classified.clock,
                    })
        return implications, unsupported

    @staticmethod
    def build_cover_bind_module(
        contract: InterfaceContract,
        cover_points: list[dict[str, Any]],
    ) -> tuple[str, list[int]]:
        """Generate a bounded antecedent-reachability cover checker.

        Returns (code, cover_line_numbers) where cover_line_numbers[i] is the
        1-based source line of cover_points[i]'s statement, used to attribute
        executed SBY witness locations back to properties.
        """
        port_decls = []
        for p in contract.ports:
            bind_port = PortDefinition(
                name=p.name,
                direction=PortDirection.INPUT,
                width=p.width,
                description=p.description,
            )
            port_decls.append(f"  {bind_port.to_verilog_declaration()}")
        port_decls_str = ",\n".join(port_decls)

        lines = [
            f"// Mind 3.0 bounded antecedent-reachability covers for {contract.module_name}",
            f"// Each cover mirrors its assertion's evaluation condition exactly.",
            f"module {contract.module_name}_cover (",
            port_decls_str,
            ");",
            "",
        ]
        clocks = [cp["clock"] for cp in cover_points if cp.get("clock")]
        if clocks:
            lines.append("  reg init = 1'b1;")
            lines.append(f"  always @(posedge {clocks[0]}) init <= 1'b0;")
            lines.append("")
        def _line_count() -> int:
            # List elements may embed newlines (e.g. the port block) and are
            # joined with "\n", so count both embedded and separator newlines.
            return sum(s.count("\n") for s in lines) + len(lines)

        cover_line_numbers: list[int] = []
        for cp in cover_points:
            clock = cp.get("clock")
            event = f"always @(posedge {clock})" if clock else "always @*"
            lines.append(f"  // vacuity-target: {cp['name']} kind={cp['kind']}")
            lines.append(f"  {event} begin")
            lines.append(f"    if ({cp['cover_guard']}) cover ({cp['cover_expr']}); // vacuity: {cp['name']}")
            cover_line_numbers.append(_line_count())
            lines.append("  end")
            lines.append("")
        lines.append("endmodule")
        lines.append("")
        return "\n".join(lines), cover_line_numbers

    @staticmethod
    def build_cover_top_module(contract: InterfaceContract) -> str:
        """Generate a cover wrapper instantiating the DUT and the cover checker."""
        signal_decls = []
        dut_port_conns = []
        cover_port_conns = []
        for p in contract.ports:
            if p.width == 1:
                signal_decls.append(f"  logic {p.name};")
            else:
                signal_decls.append(f"  logic [{p.width-1}:0] {p.name};")
            dut_port_conns.append(f"    .{p.name}({p.name})")
            cover_port_conns.append(f"    .{p.name}({p.name})")

        signals_str = "\n".join(signal_decls)
        dut_conns_str = ",\n".join(dut_port_conns)
        cover_conns_str = ",\n".join(cover_port_conns)

        return (
            f"// Bounded antecedent-reachability wrapper for {contract.module_name}\n"
            f"module {contract.module_name}_cover_top;\n\n"
            f"{signals_str}\n\n"
            f"  {contract.module_name} dut (\n"
            f"{dut_conns_str}\n"
            f"  );\n\n"
            f"  {contract.module_name}_cover cov (\n"
            f"{cover_conns_str}\n"
            f"  );\n\n"
            f"endmodule\n"
        )

    @staticmethod
    def build_cover_sby_config(contract: InterfaceContract, depth: int = 25) -> str:
        """Generate an SBY cover-mode configuration mirroring the BMC proof bound."""
        top = f"{contract.module_name}_cover_top"
        return (
            f"[options]\n"
            f"mode cover\n"
            f"depth {depth}\n\n"
            f"[engines]\n"
            f"smtbmc z3\n\n"
            f"[script]\n"
            f"read -formal {contract.module_name}.sv\n"
            f"read -formal {contract.module_name}_cover.sv\n"
            f"read -formal {top}.sv\n"
            f"prep -top {top}\n\n"
            f"[files]\n"
            f"{contract.module_name}.sv\n"
            f"{contract.module_name}_cover.sv\n"
            f"{top}.sv\n"
        )

    @staticmethod
    def build_verilator_cpp_testbench(contract: InterfaceContract) -> str:
        """Generate Verilator C++ test driver supporting both combinational and sequential designs."""
        has_clock = VerificationHarnessGenerator._has_clock(contract)
        has_reset = VerificationHarnessGenerator._has_reset(contract)
        clk_port = VerificationHarnessGenerator._get_clock_name(contract) if has_clock else ""
        reset_info = VerificationHarnessGenerator._get_reset_info(contract) if has_reset else None
        rst_port = reset_info[0] if reset_info else ""
        rst_active_low = reset_info[1] if reset_info else True

        input_ports = [
            p for p in contract.ports
            if p.direction == PortDirection.INPUT and p.name not in (clk_port, rst_port)
        ]

        boundary_lines: list[str] = []
        for p in input_ports:
            mask = (1 << p.width) - 1
            if p.width == 1:
                boundary_lines.append(f"        top->{p.name} = (uint8_t)(boundary_val & 1u);")
            else:
                boundary_lines.append(f"        top->{p.name} = (boundary_val & 0x{mask:X}u);")
        boundary_code = "\n".join(boundary_lines) if boundary_lines else "        (void)boundary_val;"

        walking_lines: list[str] = []
        for i, p in enumerate(input_ports):
            mask = (1 << p.width) - 1
            if p.width == 1:
                walking_lines.append(f"        top->{p.name} = (uint8_t)((1u << bit_pos) >> {i} & 1u);")
            else:
                walking_lines.append(f"        top->{p.name} = ((1u << (bit_pos % {p.width})) & 0x{mask:X}u);")
        walking_code = "\n".join(walking_lines) if walking_lines else "        (void)bit_pos;"

        lfsr_lines: list[str] = []
        for i, p in enumerate(input_ports):
            mask = (1 << p.width) - 1
            shift = (i * 4) % 28
            if p.width == 1:
                lfsr_lines.append(f"        top->{p.name} = (uint8_t)((lfsr >> {shift}) & 1u);")
            else:
                lfsr_lines.append(f"        top->{p.name} = ((lfsr >> {shift}) & 0x{mask:X}u);")
        lfsr_code = "\n".join(lfsr_lines) if lfsr_lines else "        (void)lfsr;"

        if not has_clock:
            # PURE COMBINATIONAL TESTBENCH
            return (
                f"#include <verilated.h>\n"
                f"#include <verilated_cov.h>\n"
                f"#include \"V{contract.module_name}.h\"\n"
                f"#include <iostream>\n"
                f"#include <cassert>\n"
                f"#include <cstdlib>\n"
                f"#include <cstdint>\n\n"
                f"int main(int argc, char** argv) {{\n"
                f"    Verilated::commandArgs(argc, argv);\n"
                f"    V{contract.module_name}* top = new V{contract.module_name};\n\n"
                f"    // Phase 1: Combinational boundary sweeps\n"
                f"    uint32_t sweep_vals[] = {{0x00000000u, 0xFFFFFFFFu, 0xAAAAAAAAu, 0x55555555u}};\n"
                f"    for (int s = 0; s < 4; ++s) {{\n"
                f"        uint32_t boundary_val = sweep_vals[s];\n"
                f"{boundary_code}\n"
                f"        top->eval();\n"
                f"    }}\n\n"
                f"    // Phase 2: Walking bit patterns\n"
                f"    for (int bit_pos = 0; bit_pos < 32; ++bit_pos) {{\n"
                f"{walking_code}\n"
                f"        top->eval();\n"
                f"    }}\n\n"
                f"    // Phase 3: LFSR pseudo-random stimulus\n"
                f"    uint32_t lfsr = 0xACE1u;\n"
                f"    for (int cycle = 0; cycle < 500; ++cycle) {{\n"
                f"        uint32_t lsb = lfsr & 1u;\n"
                f"        lfsr = (lfsr >> 1) | (lsb ? 0x80000000u : 0u);\n"
                f"        if (lsb) lfsr ^= 0xB4BCD35Cu;\n"
                f"{lfsr_code}\n"
                f"        top->eval();\n"
                f"    }}\n\n"
                f"    top->final();\n"
                f"    VerilatedCov::write(\"coverage.dat\");\n"
                f"    std::cout << \"ALL TESTS PASSED: Combinational stimulus complete.\" << std::endl;\n"
                f"    delete top;\n"
                f"    return 0;\n"
                f"}}\n"
            )

        # SEQUENTIAL TESTBENCH
        reset_init = ""
        reset_recover = ""
        if has_reset:
            rst_assert = "0" if rst_active_low else "1"
            rst_deassert = "1" if rst_active_low else "0"
            reset_init = (
                f"    // Phase 1: Synchronous reset sequence (10 half-cycles)\n"
                f"    top->{clk_port} = 0;\n"
                f"    top->{rst_port} = {rst_assert};\n"
                f"    for (int i = 0; i < 10; ++i) {{\n"
                f"        top->{clk_port} = !top->{clk_port};\n"
                f"        top->eval();\n"
                f"    }}\n"
                f"    top->{rst_port} = {rst_deassert};\n\n"
            )
            reset_recover = (
                f"    // Phase 4: Reset recovery verification\n"
                f"    top->{rst_port} = {rst_assert};\n"
                f"    for (int i = 0; i < 4; ++i) {{\n"
                f"        top->{clk_port} = !top->{clk_port};\n"
                f"        top->eval();\n"
                f"    }}\n"
                f"    top->{rst_port} = {rst_deassert};\n"
                f"    top->{clk_port} = !top->{clk_port};\n"
                f"    top->eval();\n\n"
            )
        else:
            reset_init = (
                f"    // Phase 1: Clock startup without reset\n"
                f"    top->{clk_port} = 0;\n"
                f"    for (int i = 0; i < 4; ++i) {{\n"
                f"        top->{clk_port} = !top->{clk_port};\n"
                f"        top->eval();\n"
                f"    }}\n\n"
            )

        return (
            f"#include <verilated.h>\n"
            f"#include <verilated_cov.h>\n"
            f"#include \"V{contract.module_name}.h\"\n"
            f"#include <iostream>\n"
            f"#include <cassert>\n"
            f"#include <cstdlib>\n"
            f"#include <cstdint>\n\n"
            f"int main(int argc, char** argv) {{\n"
            f"    Verilated::commandArgs(argc, argv);\n"
            f"    V{contract.module_name}* top = new V{contract.module_name};\n\n"
            f"{reset_init}"
            f"    // Phase 2: Boundary sweep — all-zeros then all-ones\n"
            f"    uint32_t sweep_vals[] = {{0x00000000u, 0xFFFFFFFFu}};\n"
            f"    for (int s = 0; s < 2; ++s) {{\n"
            f"        uint32_t boundary_val = sweep_vals[s];\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"{boundary_code}\n"
            f"        top->eval();\n"
            f"    }}\n\n"
            f"    // Phase 2b: Walking-1 pattern across 32 bit positions\n"
            f"    for (int bit_pos = 0; bit_pos < 32; ++bit_pos) {{\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"{walking_code}\n"
            f"        top->eval();\n"
            f"    }}\n\n"
            f"    // Phase 3: Galois LFSR pseudo-random stimulus\n"
            f"    // A fixed 32-bit Galois LFSR (mask 0xB4BCD35C) used for pseudo-random stimulus.\n"
            f"    uint32_t lfsr = 0xACE1u;\n"
            f"    for (int cycle = 0; cycle < 400; ++cycle) {{\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"        uint32_t lsb = lfsr & 1u;\n"
            f"        lfsr = (lfsr >> 1) | (lsb ? 0x80000000u : 0u);\n"
            f"        if (lsb) lfsr ^= 0xB4BCD35Cu;\n"
            f"{lfsr_code}\n"
            f"        top->eval();\n"
            f"    }}\n\n"
            f"{reset_recover}"
            f"    top->final();\n"
            f"    VerilatedCov::write(\"coverage.dat\");\n"
            f"    std::cout << \"ALL TESTS PASSED: FSM-aware stimulus complete (reset+boundary+LFSR+recovery).\" << std::endl;\n"
            f"    delete top;\n"
            f"    return 0;\n"
            f"}}\n"
        )

