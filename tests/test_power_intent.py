"""Tests for IEEE 1801 UPF 3.0 Power Intent Engine and Low-Power Verifier."""

from pathlib import Path

from mind3.core.power import (
    ClampValue,
    IsolationLocation,
    IsolationRule,
    LevelShifterRule,
    LevelShifterType,
    LowPowerVerifier,
    PowerDomainSpec,
    PowerIntentContract,
    PowerStateTable,
    PowerSupplyNet,
    PowerSwitchSpec,
    RetentionRule,
    UPFGenerator,
)


def test_upf3_script_generation() -> None:
    """Validate that UPFGenerator outputs compliant IEEE 1801 UPF 3.0 TCL commands."""
    contract = PowerIntentContract(
        top_module="soc_top",
        supplies=[
            PowerSupplyNet(name="VDD_TOP", voltage_volts=0.8),
            PowerSupplyNet(name="VDD_CPU", voltage_volts=0.75),
            PowerSupplyNet(name="VSS", voltage_volts=0.0, is_ground=True),
        ],
        domains=[
            PowerDomainSpec(name="PD_TOP", elements=[], primary_power_net="VDD_TOP", primary_ground_net="VSS"),
            PowerDomainSpec(name="PD_CPU", elements=["u_cpu"], primary_power_net="VDD_CPU", primary_ground_net="VSS"),
        ],
        switches=[
            PowerSwitchSpec(
                name="SW_CPU",
                domain="PD_CPU",
                input_supply_port="VDD_TOP",
                output_supply_port="VDD_CPU",
                control_port="pwr_en_cpu",
            )
        ],
        isolation_rules=[
            IsolationRule(
                name="ISO_CPU",
                domain="PD_CPU",
                isolation_signal="iso_en_cpu",
                clamp_value=ClampValue.ZERO,
                location=IsolationLocation.SELF,
            )
        ],
        level_shifter_rules=[
            LevelShifterRule(
                name="LS_CPU_TO_TOP",
                domain="PD_CPU",
                rule_type=LevelShifterType.BIDIRECTIONAL,
            )
        ],
        retention_rules=[
            RetentionRule(
                name="RET_CPU",
                domain="PD_CPU",
                save_signal="save_cpu",
                restore_signal="restore_cpu",
            )
        ],
        power_state_table=PowerStateTable(
            name="PST_SOC",
            supply_nets=["VDD_TOP", "VDD_CPU", "VSS"],
            states={
                "STATE_ACTIVE": [0.8, 0.75, 0.0],
                "STATE_SLEEP": [0.8, "OFF", 0.0],
            },
        ),
    )

    upf_text = UPFGenerator.generate_upf3(contract)
    assert "upf_version 3.0" in upf_text
    assert "create_power_domain PD_TOP" in upf_text
    assert "create_power_domain PD_CPU -elements {u_cpu}" in upf_text
    assert "create_power_switch SW_CPU" in upf_text
    assert "set_isolation ISO_CPU" in upf_text
    assert "set_level_shifter LS_CPU_TO_TOP" in upf_text
    assert "set_retention RET_CPU" in upf_text
    assert "create_pst PST_SOC" in upf_text
    assert "add_pst_state STATE_ACTIVE" in upf_text
    assert "add_pst_state STATE_SLEEP" in upf_text


def test_low_power_verifier_detects_unisolated_domain() -> None:
    """LowPowerVerifier must flag domains with power gating switches but no isolation rules."""
    bad_contract = PowerIntentContract(
        top_module="chip",
        supplies=[
            PowerSupplyNet(name="VDD", voltage_volts=0.8),
            PowerSupplyNet(name="VSS", voltage_volts=0.0, is_ground=True),
        ],
        domains=[
            PowerDomainSpec(name="PD_CORE", elements=["u_core"], primary_power_net="VDD", primary_ground_net="VSS"),
        ],
        switches=[
            PowerSwitchSpec(
                name="SW_CORE",
                domain="PD_CORE",
                input_supply_port="VDD",
                output_supply_port="VDD_GATED",
                control_port="en",
            )
        ],
        isolation_rules=[],  # Missing isolation!
    )
    res = LowPowerVerifier.audit_power_intent(bad_contract, [])
    assert res["passed"] is False
    assert any("missing 'set_isolation'" in v for v in res["violations"])


def test_low_power_verifier_clean_contract() -> None:
    """LowPowerVerifier passes when all switched domains are properly isolated."""
    clean_contract = PowerIntentContract(
        top_module="chip",
        supplies=[
            PowerSupplyNet(name="VDD", voltage_volts=0.8),
            PowerSupplyNet(name="VSS", voltage_volts=0.0, is_ground=True),
        ],
        domains=[
            PowerDomainSpec(name="PD_CORE", elements=["u_core"], primary_power_net="VDD", primary_ground_net="VSS"),
        ],
        switches=[
            PowerSwitchSpec(
                name="SW_CORE",
                domain="PD_CORE",
                input_supply_port="VDD",
                output_supply_port="VDD_GATED",
                control_port="en",
            )
        ],
        isolation_rules=[
            IsolationRule(
                name="ISO_CORE",
                domain="PD_CORE",
                isolation_signal="iso_en",
            )
        ],
    )
    res = LowPowerVerifier.audit_power_intent(clean_contract, [])
    assert res["passed"] is True
    assert res["violation_count"] == 0
