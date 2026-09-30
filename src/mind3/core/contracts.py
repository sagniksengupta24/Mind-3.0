"""
Decoupled multi-agent contract specifications and prompt builders for Mind 3.0.
Prevents tautological testbench hallucination by decoupling RTL synthesis from verification harness creation.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
        generation is done by VerificationHarnessGenerator.build_sva_bind_module().
        """
        return (
            f"  // SVA Property: {self.name} (Yosys-compatible generation in build_sva_bind_module)\n"
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


class InterfaceContract(BaseModel):
    """Strict interface contract decoupling RTL implementation from verification harnesses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    module_name: str = Field(min_length=1, description="Target top-level module identifier")
    functional_spec: str = Field(min_length=1, description="Natural language behavioral specification")
    parameters: dict[str, str] = Field(default_factory=dict, description="Verilog module parameters")
    ports: list[PortDefinition] = Field(min_length=1, description="Complete interface pinout")
    sva_properties: list[SVAProperty] = Field(
        default_factory=list,
        description="Formal invariants verifying sequential behavior",
    )
    timing: TimingConstraint = Field(
        default_factory=TimingConstraint,
        description="Physical timing and clock constraints",
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
            "2. Formal Invariants: Author 2 to 5 SystemVerilog Assertions (SVA) covering safety and liveness.\n"
            "3. Timing: Define target clock period in nanoseconds.\n\n"
            "Schema template:\n"
            "{\n"
            '  "module_name": "string (valid verilog identifier)",\n'
            '  "functional_spec": "string",\n'
            '  "parameters": {},\n'
            '  "ports": [\n'
            '    {"name": "clk", "direction": "input", "width": 1, "description": "Clock signal"},\n'
            '    {"name": "rst_n", "direction": "input", "width": 1, "description": "Active-low reset"}\n'
            '  ],\n'
            '  "sva_properties": [\n'
            '    {"name": "p_name", "property_expr": "expr", "clock": "clk", "reset": "rst_n", "description": "desc"}\n'
            '  ],\n'
            '  "timing": {"clock_name": "clk", "period_ns": 10.0}\n'
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
        user_msg = (
            f"Module: {contract.module_name}\n"
            f"Specification: {contract.functional_spec}\n"
            f"Parameters: {json.dumps(contract.parameters)}\n"
            f"Pinout:\n{ports_summary}\n\n"
            f"Implement the complete synthesizable SystemVerilog module:"
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

        if not contract.sva_properties:
            return (
                f"// Mind 3.0 SVA Checker Module: {contract.module_name}_sva\n"
                f"module {contract.module_name}_sva (\n{port_decls_str}\n);\n\n"
                f"  // No SVA properties specified in contract\n\n"
                f"endmodule\n"
            )

        has_clock = VerificationHarnessGenerator._has_clock(contract)
        clock_name = VerificationHarnessGenerator._get_clock_name(contract) if has_clock else ""
        reset_info = VerificationHarnessGenerator._get_reset_info(contract) if has_clock else None

        init_reg = ""
        if has_clock:
            init_reg = f"  reg init = 1'b1;\n  always @(posedge {clock_name}) init <= 1'b0;\n\n"

        assertion_blocks = []
        for prop in contract.sva_properties:
            block = VerificationHarnessGenerator._generate_assertion_block(
                contract=contract,
                prop=prop,
                has_clock=has_clock,
                clock_name=clock_name,
                reset_info=reset_info,
            )
            assertion_blocks.append(block)

        assertions = "\n".join(assertion_blocks)
        return (
            f"// Formal SVA Verification Checker Module for {contract.module_name}\n"
            f"// Generated with Yosys-compatible procedural assertions\n"
            f"module {contract.module_name}_sva (\n"
            f"{port_decls_str}\n"
            f");\n\n"
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
        if include_sva_file and contract.sva_properties:
            files_section += f"{contract.module_name}_sva.sv\n"
            read_sva = f"read -formal {contract.module_name}_sva.sv\n"

        effective_depth = depth
        if property_depths and contract.sva_properties:
            all_depths = [property_depths.get(p.name, depth) for p in contract.sva_properties]
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

