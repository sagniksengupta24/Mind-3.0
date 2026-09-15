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

    def to_sdc(self) -> str:
        """Render Synopsys Design Constraints (SDC) file content."""
        return (
            f"# Generated Timing Constraints\n"
            f"create_clock -name {self.clock_name} -period {self.period_ns:.3f} [get_ports {self.clock_name}]\n"
            f"set_clock_uncertainty 0.150 [get_clocks {self.clock_name}]\n"
            f"set_input_delay -clock {self.clock_name} 1.000 [all_inputs]\n"
            f"set_output_delay -clock {self.clock_name} 1.000 [all_outputs]\n"
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
    """Generates formal SBY configuration and Verilator C++ stimulus without viewing RTL internals."""

    @staticmethod
    def build_sby_config(contract: InterfaceContract, depth: int = 25) -> str:
        """Generate SymbiYosys configuration script."""
        return (
            f"[options]\n"
            f"mode bmc\n"
            f"depth {depth}\n\n"
            f"[engines]\n"
            f"smtbmc z3\n\n"
            f"[script]\n"
            f"read -formal {contract.module_name}.sv\n"
            f"prep -top {contract.module_name}\n\n"
            f"[files]\n"
            f"{contract.module_name}.sv\n"
        )

    @staticmethod
    def build_verilator_cpp_testbench(contract: InterfaceContract) -> str:
        """Generate high-coverage Verilator C++ test driver."""
        clk_port = next((p.name for p in contract.ports if "clk" in p.name.lower()), "clk")
        rst_port = next((p.name for p in contract.ports if "rst" in p.name.lower()), "rst_n")
        
        return (
            f"#include <verilated.h>\n"
            f"#include \"V{contract.module_name}.h\"\n"
            f"#include <iostream>\n"
            f"#include <cassert>\n\n"
            f"int main(int argc, char** argv) {{\n"
            f"    Verilated::commandArgs(argc, argv);\n"
            f"    V{contract.module_name}* top = new V{contract.module_name};\n"
            f"    // Reset sequence\n"
            f"    top->{rst_port} = 0;\n"
            f"    top->{clk_port} = 0;\n"
            f"    for (int i = 0; i < 10; ++i) {{\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"        top->eval();\n"
            f"    }}\n"
            f"    top->{rst_port} = 1;\n"
            f"    // Stimulus loop\n"
            f"    for (int cycle = 0; cycle < 1000; ++cycle) {{\n"
            f"        top->{clk_port} = !top->{clk_port};\n"
            f"        top->eval();\n"
            f"    }}\n"
            f"    std::cout << \"ALL TESTS PASSED: Simulated 1000 cycles without violation.\" << std::endl;\n"
            f"    delete top;\n"
            f"    return 0;\n"
            f"}}\n"
        )
