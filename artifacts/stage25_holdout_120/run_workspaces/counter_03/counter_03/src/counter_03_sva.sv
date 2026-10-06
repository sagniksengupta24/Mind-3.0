// Deterministic formal checker for counter_03
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module counter_03_sva (
  input wire clk,
  input wire rst_n,
  input wire en,
  input wire [3:0] bcd_ones,
  input wire [3:0] bcd_tens,
  input wire carry_out
);

  // property-audit: contract_property_1 kind=boolean source=structured_template supported=True
  // property-audit: contract_property_2 kind=boolean source=structured_template supported=True

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;

  // BMC starts from reset: real designs boot with reset asserted.
  // Without this, uninitialized flops take any value and every
  // stateful design fails vacuously once the init guard lifts.
  always @(posedge clk) begin
    if (init) assume (!rst_n);
  end

  // [MIND3-TEMPLATE:boolean] contract_property_1
  always @(posedge clk) begin
    if (!init && rst_n) assert (bcd_ones <= 4'd9);
  end

  // [MIND3-TEMPLATE:boolean] contract_property_2
  always @(posedge clk) begin
    if (!init && rst_n) assert (bcd_tens <= 4'd9);
  end

endmodule
