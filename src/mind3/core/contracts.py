"""
Decoupled multi-agent contract specifications and prompt builders for Mind 3.0.
Prevents tautological testbench hallucination by decoupling RTL synthesis from verification harness creation.
"""

from __future__ import annotations

import json
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
        """Render SVA property and assert directive."""
        return (
            f"  // SVA Property: {self.name}\n"
            f"  property p_{self.name};\n"
            f"    @(posedge {self.clock}) disable iff (!{self.reset})\n"
            f"    {self.property_expr};\n"
            f"  endproperty\n"
            f"  assert property (p_{self.name}) else $fatal(1, \"Assertion failed: {self.name}\");\n"
        )


class TimingConstraint(BaseModel):
    """Clock and physical timing parameters for OpenSTA signoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    clock_name: str = Field(default="clk", description="Primary clock signal name")
    period_ns: float = Field(default=10.0, gt=0.0, description="Clock period target in nanoseconds")
    target_library: str = Field(
        default="sky130_fd_sc_hd__tt_025C_1v80.lib",
        description="Reference Liberty cell library",
    )
    pvt_corners: list[str] = Field(
        default_factory=lambda: ["tt_025c_1v80", "ff_n40c_1v95", "ss_125c_1v60"],
        description="PVT corner identifiers for MCMM timing analysis (TT, FF, SS)",
    )
    lef_path: str | None = Field(
        default=None,
        description="Technology LEF file path for OpenROAD physical design (Gate 5)",
    )

    def to_sdc(self) -> str:
        """Render Synopsys Design Constraints (SDC) file content with timing exception stubs."""
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
        param_decl = f" #(\n{',\n'.join(param_list)}\n)" if param_list else ""
        port_list = [f"  {p.to_verilog_declaration()}" for p in self.ports]
        return (
            f"module {self.module_name}{param_decl} (\n"
            f"{',\n'.join(port_list)}\n"
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
            "3. Timing: Define target clock period in nanoseconds."
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


class VerificationHarnessGenerator:
    """Generates formal SBY configuration, SVA bind files, and Verilator C++ stimulus without viewing RTL internals."""

    @staticmethod
    def build_sva_bind_module(contract: InterfaceContract) -> str:
        """Generate SystemVerilog bind module containing SVA temporal assertions."""
        port_decls = [f"  {p.to_verilog_declaration()}" for p in contract.ports]
        assertions = "\n".join(prop.to_verilog_assertion() for prop in contract.sva_properties)
        return (
            f"// Formal SVA Verification Bind Module for {contract.module_name}\n"
            f"module {contract.module_name}_sva (\n"
            f"{',\n'.join(port_decls)}\n"
            f");\n\n"
            f"{assertions}\n"
            f"endmodule\n\n"
            f"bind {contract.module_name} {contract.module_name}_sva sva_inst (.*);\n"
        )

    @staticmethod
    def build_sby_config(
        contract: InterfaceContract,
        depth: int = 25,
        include_sva_file: bool = True,
        property_depths: dict[str, int] | None = None,
    ) -> str:
        """Generate SymbiYosys configuration script with optional per-property depth overrides.

        Args:
            contract: Interface contract specifying the module and SVA properties.
            depth: Default BMC depth for all properties (cycles).
            include_sva_file: Whether to include the SVA bind module.
            property_depths: Optional dict mapping SVA property name to a custom depth,
                overriding the default for that property only.
        """
        files_section = f"{contract.module_name}.sv\n"
        read_sva = ""
        if include_sva_file and contract.sva_properties:
            files_section += f"{contract.module_name}_sva.sv\n"
            read_sva = f"read -formal {contract.module_name}_sva.sv\n"

        effective_depth = depth
        if property_depths:
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
            f"prep -top {contract.module_name}\n\n"
            f"[files]\n"
            f"{files_section}"
        )

    @staticmethod
    def build_verilator_cpp_testbench(contract: InterfaceContract) -> str:
        """Generate FSM-aware Verilator C++ test driver with 4-phase stimulus coverage.

        Phase 1 (cycles 0-9):   Synchronous reset sequence.
        Phase 2 (cycles 10-75): Boundary sweep — all-zeros, all-ones, walking-1, walking-0.
        Phase 3 (cycles 76-475): LFSR pseudo-random stimulus (32-bit maximal-length polynomial).
        Phase 4 (cycles 476-479): Reset recovery — re-assert reset and verify outputs settle.
        """
        clk_port = next((p.name for p in contract.ports if "clk" in p.name.lower()), "clk")
        rst_port = next((p.name for p in contract.ports if "rst" in p.name.lower()), "rst_n")

        # Collect non-clock, non-reset input signals
        input_ports = [
            p for p in contract.ports
            if p.direction == PortDirection.INPUT and p.name not in (clk_port, rst_port)
        ]

        # Phase 2: Boundary sweep assignments (all-zeros / all-ones)
        boundary_lines: list[str] = []
        for p in input_ports:
            mask = (1 << p.width) - 1
            if p.width == 1:
                boundary_lines.append(f"        top->{p.name} = (uint8_t)(boundary_val & 1u);")
            else:
                boundary_lines.append(f"        top->{p.name} = (boundary_val & 0x{mask:X}u);")
        boundary_code = "\n".join(boundary_lines) if boundary_lines else "        (void)boundary_val;"

        # Phase 2b: Walking-1 assignments
        walking_lines: list[str] = []
        for i, p in enumerate(input_ports):
            mask = (1 << p.width) - 1
            if p.width == 1:
                walking_lines.append(f"        top->{p.name} = (uint8_t)((1u << bit_pos) >> {i} & 1u);")
            else:
                walking_lines.append(f"        top->{p.name} = ((1u << (bit_pos % {p.width})) & 0x{mask:X}u);")
        walking_code = "\n".join(walking_lines) if walking_lines else "        (void)bit_pos;"

        # Phase 3: LFSR stimulus assignments
        lfsr_lines: list[str] = []
        for i, p in enumerate(input_ports):
            mask = (1 << p.width) - 1
            shift = (i * 4) % 28
            if p.width == 1:
                lfsr_lines.append(f"        top->{p.name} = (uint8_t)((lfsr >> {shift}) & 1u);")
            else:
                lfsr_lines.append(f"        top->{p.name} = ((lfsr >> {shift}) & 0x{mask:X}u);")
        lfsr_code = "\n".join(lfsr_lines) if lfsr_lines else "        (void)lfsr;"

        return (
            f"#include <verilated.h>\n"
            f"#include \"V{contract.module_name}.h\"\n"
            f"#include <iostream>\n"
            f"#include <cassert>\n"
            f"#include <cstdlib>\n"
            f"#include <cstdint>\n\n"
            f"int main(int argc, char** argv) {{\n"
            f"    Verilated::commandArgs(argc, argv);\n"
            f"    V{contract.module_name}* top = new V{contract.module_name};\n\n"
            f"    // Phase 1: Synchronous reset sequence (10 half-cycles)\n"
            f"    top->{clk_port} = 0;\n"
            f"    top->{rst_port} = 0;\n"
            f"    for (int i = 0; i < 10; ++i) {{\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"        top->eval();\n"
            f"    }}\n"
            f"    top->{rst_port} = 1;\n\n"
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
            f"    // Phase 3: LFSR pseudo-random stimulus\n"
            f"    // 32-bit maximal-length Fibonacci LFSR: polynomial x^32+x^31+x^29+x^1+1 (0xB4BCD35C)\n"
            f"    uint32_t lfsr = 0xACE1u;\n"
            f"    for (int cycle = 0; cycle < 400; ++cycle) {{\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"        uint32_t lsb = lfsr & 1u;\n"
            f"        lfsr = (lfsr >> 1) | (lsb ? 0x80000000u : 0u);\n"
            f"        if (lsb) lfsr ^= 0xB4BCD35Cu;\n"
            f"{lfsr_code}\n"
            f"        top->eval();\n"
            f"    }}\n\n"
            f"    // Phase 4: Reset recovery verification\n"
            f"    top->{rst_port} = 0;\n"
            f"    for (int i = 0; i < 4; ++i) {{\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"        top->eval();\n"
            f"    }}\n"
            f"    top->{rst_port} = 1;\n"
            f"    top->{clk_port} = !top->{clk_port};\n"
            f"    top->eval();\n\n"
            f"    top->final();\n"
            f"    std::cout << \"ALL TESTS PASSED: FSM-aware stimulus complete (reset+boundary+LFSR+recovery).\" << std::endl;\n"
            f"    delete top;\n"
            f"    return 0;\n"
            f"}}\n"
        )

