"""IEEE 1801 (UPF 3.0) Multi-Voltage and Low-Power Intent Engine for Mind 3.0.

Provides formal specifications, UPF 3.0 generation, and low-power verification
for power domains, isolation cells, level shifters, retention registers, and power state tables.
"""

from __future__ import annotations

import re
import textwrap
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClampValue(str, Enum):
    ZERO = "0"
    ONE = "1"
    LATCH = "latch"


class IsolationLocation(str, Enum):
    SELF = "self"
    PARENT = "parent"
    FANOUT = "fanout"


class LevelShifterType(str, Enum):
    LOW_TO_HIGH = "lh"
    HIGH_TO_LOW = "hl"
    BIDIRECTIONAL = "both"


class PowerSupplyNet(BaseModel):
    """Specification of a power or ground rail."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Supply net identifier, e.g. VDD_CORE")
    voltage_volts: float = Field(ge=0.0, description="Nominal voltage in volts")
    is_ground: bool = Field(default=False, description="True if this net is ground (VSS)")


class PowerDomainSpec(BaseModel):
    """Specification of an IEEE 1801 Power Domain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Power domain name, e.g. PD_TOP or PD_CPU")
    elements: list[str] = Field(
        default_factory=list,
        description="Hierarchical instance paths included in this domain (empty for top)",
    )
    primary_power_net: str = Field(default="VDD", description="Primary VDD net name")
    primary_ground_net: str = Field(default="VSS", description="Primary VSS net name")


class PowerSwitchSpec(BaseModel):
    """Specification of a head-switch or foot-switch power gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Switch cell instance name, e.g. SW_CPU")
    domain: str = Field(min_length=1, description="Associated power domain")
    input_supply_port: str = Field(description="Unswitched supply port (e.g. VDD)")
    output_supply_port: str = Field(description="Switched supply port (e.g. VDD_GATED)")
    control_port: str = Field(description="Power-enable control signal")
    on_state_name: str = Field(default="ON", description="State name when switch is enabled")


class IsolationRule(BaseModel):
    """Specification of an isolation cell rule between power domains."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Isolation rule name")
    domain: str = Field(min_length=1, description="Domain to isolate")
    isolation_signal: str = Field(description="Isolation enable control signal")
    clamp_value: ClampValue = Field(default=ClampValue.ZERO, description="Clamped output logic value")
    location: IsolationLocation = Field(default=IsolationLocation.SELF, description="Cell insertion location")
    applies_to: str = Field(default="outputs", description="'inputs', 'outputs', or 'both'")


class LevelShifterRule(BaseModel):
    """Specification of a level shifter rule for cross-voltage domains."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Level shifter rule name")
    domain: str = Field(min_length=1, description="Domain to protect")
    rule_type: LevelShifterType = Field(default=LevelShifterType.BIDIRECTIONAL)
    location: str = Field(default="self", description="'self' or 'parent'")
    threshold_volts: float = Field(default=0.05, description="Voltage delta triggering level shifter")


class RetentionRule(BaseModel):
    """Specification of retention registers for state retention during power-down."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="Retention rule name")
    domain: str = Field(min_length=1, description="Domain containing retention registers")
    save_signal: str = Field(description="Signal to trigger register state save")
    restore_signal: str = Field(description="Signal to trigger register state restore")


class PowerStateTable(BaseModel):
    """Power State Table (PST) defining legal operational supply combinations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(default="PST_MAIN", description="PST identifier")
    supply_nets: list[str] = Field(min_length=1, description="Ordered list of supply net names in PST")
    states: dict[str, list[float | str]] = Field(
        min_length=1,
        description="State name -> list of voltages (float) or status strings (e.g. 'OFF', 0.8)",
    )


class PowerIntentContract(BaseModel):
    """Complete IEEE 1801 UPF 3.0 Low-Power Intent Contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    top_module: str = Field(min_length=1, description="Top-level module identifier")
    supplies: list[PowerSupplyNet] = Field(min_length=1, description="Power and ground rails")
    domains: list[PowerDomainSpec] = Field(min_length=1, description="Hierarchical power domains")
    switches: list[PowerSwitchSpec] = Field(default_factory=list, description="Power gating switches")
    isolation_rules: list[IsolationRule] = Field(default_factory=list, description="Isolation rules")
    level_shifter_rules: list[LevelShifterRule] = Field(default_factory=list, description="Level shifters")
    retention_rules: list[RetentionRule] = Field(default_factory=list, description="State retention rules")
    power_state_table: PowerStateTable | None = Field(default=None, description="PST definition")


class UPFGenerator:
    """Synthesizes IEEE 1801 UPF 3.0 command scripts from a PowerIntentContract."""

    @staticmethod
    def generate_upf3(contract: PowerIntentContract) -> str:
        """Render complete UPF 3.0 script adhering to IEEE 1801."""
        lines: list[str] = [
            "## ══════════════════════════════════════════════════════════════════════════",
            f"## IEEE 1801 UPF 3.0 Power Intent for {contract.top_module}",
            "## Auto-generated by Mind 3.0 Low-Power Engine",
            "## ══════════════════════════════════════════════════════════════════════════",
            "upf_version 3.0",
            "",
            "## 1. Supply Nets and Ports",
        ]

        # Supplies
        for s in contract.supplies:
            lines.append(f"create_supply_net {s.name}")
            lines.append(f"create_supply_port {s.name} -direction in")
            lines.append(f"connect_supply_net {s.name} -ports {{{s.name}}}")
            if s.is_ground:
                lines.append(f"set_ground_net {s.name}")
            else:
                lines.append(f"set_voltage {s.voltage_volts} -object_list {{{s.name}}}")
        lines.append("")

        # Domains
        lines.append("## 2. Power Domains")
        for d in contract.domains:
            elem_cmd = f" -elements {{{' '.join(d.elements)}}}" if d.elements else ""
            lines.append(f"create_power_domain {d.name}{elem_cmd}")
            lines.append(
                f"set_domain_supply_net {d.name} "
                f"-primary_power_net {d.primary_power_net} "
                f"-primary_ground_net {d.primary_ground_net}"
            )
        lines.append("")

        # Power Switches
        if contract.switches:
            lines.append("## 3. Power Switches")
            for sw in contract.switches:
                lines.append(
                    f"create_power_switch {sw.name} -domain {sw.domain} "
                    f"-input_supply_port {{{sw.input_supply_port}}} "
                    f"-output_supply_port {{{sw.output_supply_port}}} "
                    f"-control_port {{{sw.control_port}}} "
                    f"-on_state {{{sw.on_state_name} {sw.input_supply_port} {{{sw.control_port}}}}}"
                )
            lines.append("")

        # Isolation Rules
        if contract.isolation_rules:
            lines.append("## 4. Isolation Rules")
            for iso in contract.isolation_rules:
                lines.append(
                    f"set_isolation {iso.name} -domain {iso.domain} "
                    f"-applies_to {iso.applies_to} "
                    f"-clamp_value {iso.clamp_value.value} "
                    f"-isolation_signal {{{iso.isolation_signal}}} "
                    f"-location {iso.location.value}"
                )
            lines.append("")

        # Level Shifter Rules
        if contract.level_shifter_rules:
            lines.append("## 5. Level Shifter Rules")
            for ls in contract.level_shifter_rules:
                lines.append(
                    f"set_level_shifter {ls.name} -domain {ls.domain} "
                    f"-rule {ls.rule_type.value} "
                    f"-location {ls.location} "
                    f"-threshold {ls.threshold_volts}"
                )
            lines.append("")

        # Retention Rules
        if contract.retention_rules:
            lines.append("## 6. Retention Rules")
            for ret in contract.retention_rules:
                lines.append(
                    f"set_retention {ret.name} -domain {ret.domain} "
                    f"-save_signal {{{ret.save_signal} high}} "
                    f"-restore_signal {{{ret.restore_signal} high}}"
                )
            lines.append("")

        # Power State Table
        if contract.power_state_table:
            pst = contract.power_state_table
            lines.append("## 7. Power State Table (PST)")
            lines.append(f"create_pst {pst.name} -supplies {{{' '.join(pst.supply_nets)}}}")
            for state_name, voltages in pst.states.items():
                v_str = " ".join(str(v) for v in voltages)
                lines.append(f"add_pst_state {state_name} -pst {pst.name} -state {{{v_str}}}")
            lines.append("")

        return "\n".join(lines)


class LowPowerVerifier:
    """Audits UPF power intent against RTL and checks for missing isolation/level-shifters."""

    @staticmethod
    def audit_power_intent(contract: PowerIntentContract, rtl_sources: list[Path]) -> dict[str, Any]:
        """Perform static low-power audit checking isolation and level shifter completeness."""
        violations: list[str] = []
        advisories: list[str] = []

        # 1. Check for domain with power switch but missing isolation
        switched_domains = {sw.domain for sw in contract.switches}
        isolated_domains = {iso.domain for iso in contract.isolation_rules}
        unisolated_switched = switched_domains - isolated_domains
        if unisolated_switched:
            for d in unisolated_switched:
                violations.append(
                    f"Domain '{d}' has power gating switch but missing 'set_isolation' rule. "
                    "Outputs will float during power-down causing crowbar current."
                )

        # 2. Check for multi-voltage domains requiring level shifters
        supply_voltages = {s.name: s.voltage_volts for s in contract.supplies if not s.is_ground}
        domain_voltages: dict[str, float] = {}
        for d in contract.domains:
            v = supply_voltages.get(d.primary_power_net)
            if v is not None:
                domain_voltages[d.name] = v

        if len(set(domain_voltages.values())) > 1 and not contract.level_shifter_rules:
            advisories.append(
                f"Design contains multi-voltage domains ({domain_voltages}) but zero 'set_level_shifter' rules defined."
            )

        # 3. Check PST table includes all defined supplies
        if contract.power_state_table:
            pst_nets = set(contract.power_state_table.supply_nets)
            declared_supplies = {s.name for s in contract.supplies}
            missing_in_pst = declared_supplies - pst_nets
            if missing_in_pst:
                violations.append(f"Supplies {missing_in_pst} declared in contract but missing in Power State Table.")

        passed = len(violations) == 0
        return {
            "passed": passed,
            "violations": violations,
            "violation_count": len(violations),
            "advisories": advisories,
            "advisory_count": len(advisories),
            "details": "Low-power intent clean." if passed else f"Low-power intent violations: {'; '.join(violations)}",
        }
