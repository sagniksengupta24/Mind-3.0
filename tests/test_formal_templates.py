from mind3.core.contracts import (
    InterfaceContract,
    PortDefinition,
    PortDirection,
    SVAProperty,
    VerificationHarnessGenerator,
)
from mind3.core.formal_templates import (
    FormalPropertySpec,
    FormalTemplateKind,
    UnsupportedFormalTemplate,
    classify_legacy_property,
    compile_formal_property,
)


def test_structured_template_is_rendered_by_mind3_not_verbatim() -> None:
    prop = FormalPropertySpec(
        name="req_gnt",
        kind=FormalTemplateKind.SAME_CYCLE_IMPLICATION,
        clock="clk",
        reset="rst_n:active_low",
        antecedent="req",
        consequent="gnt",
    )
    code = compile_formal_property(prop)
    assert "[MIND3-TEMPLATE:same_cycle_implication]" in code
    assert "always @(posedge clk)" in code
    assert "if (!init && rst_n)" in code
    assert "if (req) assert (gnt);" in code


def test_clockless_legacy_property_does_not_invent_clk() -> None:
    contract = InterfaceContract(
        module_name="mux",
        functional_spec="combinational mux",
        ports=[
            PortDefinition(name="sel", direction=PortDirection.INPUT),
            PortDefinition(name="a", direction=PortDirection.INPUT),
            PortDefinition(name="b", direction=PortDirection.INPUT),
            PortDefinition(name="y", direction=PortDirection.OUTPUT),
        ],
        sva_properties=[SVAProperty(name="p", property_expr="!sel |-> (y == a)")],
    )
    code = VerificationHarnessGenerator.build_sva_bind_module(contract)
    assert "always @*" in code
    assert "posedge clk" not in code
    assert "rst_n" not in code.lower()


def test_legacy_reset_property_keeps_explicit_reset_semantics() -> None:
    prop = classify_legacy_property(
        "reset_val",
        "assert property (@(posedge clk) !rst_n |-> q == 8'h00)",
        default_clock="clk",
        default_reset="rst_n:active_low",
    )
    code = compile_formal_property(prop)
    assert "if (!init)" in code
    assert "if (!rst_n) assert (q == 8'h00);" in code


def test_legacy_past_expression_is_supported_boundedly() -> None:
    prop = classify_legacy_property(
        "history",
        "assert property (@(posedge clk) disable iff (!rst_n) match |-> $past(data_in, 1) == 1'b1)",
        default_clock="clk",
        default_reset="rst_n:active_low",
    )
    assert prop.kind == FormalTemplateKind.PAST_EXPRESSION
    assert "$past(data_in, 1)" in compile_formal_property(prop)


def test_complex_temporal_property_fails_closed() -> None:
    try:
        classify_legacy_property("complex", "req |-> ##3 gnt")
    except UnsupportedFormalTemplate:
        return
    raise AssertionError("Complex temporal property unexpectedly classified")
