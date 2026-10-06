// Deterministic formal checker for arbiter_01
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module arbiter_01_sva (
  input wire clk,
  input wire rst_n,
  input wire [3:0] req,
  input wire [3:0] gnt
);

  // property-audit: contract_property_1 kind=onehot0 source=structured_template supported=True
  // property-audit: contract_property_2 kind=same_cycle_implication source=structured_template supported=True

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

  // [MIND3-TEMPLATE:same_cycle_implication] contract_property_2
  always @(posedge clk) begin
    if (!init) begin
      if (!rst_n) assert (gnt == 4'b0000);
    end
  end

endmodule
