"""Bare-identifier property operands must name declared ports/parameters.

The architect otherwise copies template examples (req/gnt) into unrelated
contracts, and formal fails on properties the DUT can never satisfy.
"""
from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    validate_contract_consistency,
)
from mind3.core.formal_templates import FormalPropertySpec, FormalTemplateKind


def _contract(props: list) -> InterfaceContract:
    return InterfaceContract(
        module_name="mux8",
        functional_spec="8-bit passthrough register",
        ports=[
            PortDefinition(name="clk", direction=PortDirection.INPUT),
            PortDefinition(name="rst_n", direction=PortDirection.INPUT),
            PortDefinition(name="in_data", direction=PortDirection.INPUT, width=8),
            PortDefinition(name="out_data", direction=PortDirection.OUTPUT, width=8),
        ],
        formal_properties=props,
    )


def test_template_signals_from_other_designs_rejected() -> None:
    props = [FormalPropertySpec(
        name="req_implies_gnt",
        kind=FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        clock="clk",
        antecedent="req",
        consequent="gnt",
    )]
    violations = validate_contract_consistency(_contract(props))
    assert any("req" in v["message"] for v in violations)
    assert all(v["category"] == "SPECIFICATION_ERROR" for v in violations)


def test_declared_signals_accepted() -> None:
    props = [FormalPropertySpec(
        name="data_holds",
        kind=FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        clock="clk",
        antecedent="in_data",
        consequent="out_data",
    )]
    assert validate_contract_consistency(_contract(props)) == []


def test_complex_expressions_not_flagged() -> None:
    # Literals/localparams cannot be told apart from undeclared signals, so
    # complex expressions stay unchecked (only bare identifiers are enforced).
    props = [FormalPropertySpec(
        name="reset_value",
        kind=FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        clock="clk",
        antecedent="in_data",
        consequent="out_data == 8'h00",
    )]
    assert validate_contract_consistency(_contract(props)) == []
