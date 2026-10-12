"""Multi-clock dodge: single-clock RTL must fail against dual-clock contracts.

Found in exp_c9_cdc_s43 (cdc_04): the model emitted single-clock RTL for a
dual-clock gray-pointer task, and Gate 6 reported "0 crossings" PASS.
"""
from mind3.core.contracts import (
    ClockContract,
    InterfaceContract,
    PortDefinition,
    PortDirection,
    SVAProperty,
    validate_rtl_against_contract,
)


def _contract() -> InterfaceContract:
    return InterfaceContract(
        module_name="cdc_x",
        functional_spec="Dual-clock gray-pointer synchronizer",
        ports=[
            PortDefinition(name="wr_clk", direction=PortDirection.INPUT),
            PortDefinition(name="rd_clk", direction=PortDirection.INPUT),
            PortDefinition(name="wr_rst_n", direction=PortDirection.INPUT),
            PortDefinition(name="din", direction=PortDirection.INPUT, width=8),
            PortDefinition(name="dout", direction=PortDirection.OUTPUT, width=8),
        ],
        sva_properties=[
            SVAProperty(name="p_wr", property_expr="dout == dout", clock="wr_clk", reset="wr_rst_n"),
            SVAProperty(name="p_rd", property_expr="dout == dout", clock="rd_clk", reset="wr_rst_n"),
        ],
    )


def test_single_clock_rtl_fails_dual_clock_contract() -> None:
    rtl = (
        "module cdc_x(input logic clk, input logic wr_clk, input logic rd_clk, "
        "input logic wr_rst_n, input logic [7:0] din, output logic [7:0] dout);\n"
        "  always_ff @(posedge clk) dout <= din;\n"
        "endmodule\n"
    )
    # Header declares ports the contract does not, so filter to the clock rule.
    violations = validate_rtl_against_contract(_contract(), rtl)
    clock_viols = [v for v in violations if "edge-sensitive block" in v["message"]]
    assert len(clock_viols) == 2
    assert any("wr_clk" in v["message"] for v in clock_viols)
    assert any("rd_clk" in v["message"] for v in clock_viols)


def test_dual_clock_rtl_clears_clock_rule() -> None:
    rtl = (
        "module cdc_x(input logic wr_clk, input logic rd_clk, input logic wr_rst_n, "
        "input logic [7:0] din, output logic [7:0] dout);\n"
        "  logic [7:0] mid;\n"
        "  always_ff @(posedge wr_clk) mid <= din;\n"
        "  always_ff @(posedge rd_clk) dout <= mid;\n"
        "endmodule\n"
    )
    violations = validate_rtl_against_contract(_contract(), rtl)
    assert [v for v in violations if "edge-sensitive block" in v["message"]] == []


def test_second_property_clock_required_even_when_contract_clock_set() -> None:
    contract = _contract()
    contract = contract.model_copy(update={"clock": ClockContract(name="wr_clk")})
    rtl = (
        "module cdc_x(input logic wr_clk, input logic rd_clk, input logic wr_rst_n, "
        "input logic [7:0] din, output logic [7:0] dout);\n"
        "  always_ff @(posedge wr_clk) dout <= din;\n"
        "endmodule\n"
    )
    violations = validate_rtl_against_contract(contract, rtl)
    clock_viols = [v for v in violations if "edge-sensitive block" in v["message"]]
    assert len(clock_viols) == 1 and "rd_clk" in clock_viols[0]["message"]


def test_single_clock_contract_unaffected() -> None:
    contract = InterfaceContract(
        module_name="mux",
        functional_spec="Combinational mux",
        ports=[
            PortDefinition(name="a", direction=PortDirection.INPUT),
            PortDefinition(name="b", direction=PortDirection.INPUT),
            PortDefinition(name="y", direction=PortDirection.OUTPUT),
        ],
        sva_properties=[SVAProperty(name="p", property_expr="y == y", clock="clk", reset="rst_n")],
    )
    rtl = "module mux(input logic a, input logic b, output logic y);\n  assign y = a;\nendmodule\n"
    violations = validate_rtl_against_contract(contract, rtl)
    assert [v for v in violations if "edge-sensitive block" in v["message"]] == []
