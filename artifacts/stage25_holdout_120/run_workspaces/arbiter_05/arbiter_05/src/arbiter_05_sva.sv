// Deterministic formal checker for arbiter_05
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module arbiter_05_sva (
  input wire clk,
  input wire rst_n,
  input wire [3:0] req,
  input wire [3:0] gnt
);

  // property-audit: contract_property_1 kind=onehot0 source=structured_template supported=True

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;

  // BMC starts from reset: real designs boot with reset asserted.
  // Without this, uninitialized flops take any value and every
  // stateful design fails vacuously once the init guard lifts.
  always @(posedge clk) begin
    if (init) assume (!rst_n);
  end

  // [MIND3-TEMPLATE:onehot0] contract_property_1
  always @(posedge clk) begin
    if (!init && rst_n) assert ($onehot0(gnt));
  end

endmodule
