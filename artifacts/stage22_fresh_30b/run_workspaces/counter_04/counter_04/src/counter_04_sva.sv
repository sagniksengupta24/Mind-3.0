// Deterministic formal checker for counter_04
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module counter_04_sva (
  input wire clk,
  input wire rst_n,
  input wire [7:0] q
);

  // property-audit: contract_property_1 kind=same_cycle_implication source=structured_template supported=True

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;

  // BMC starts from reset: real designs boot with reset asserted.
  // Without this, uninitialized flops take any value and every
  // stateful design fails vacuously once the init guard lifts.
  always @(posedge clk) begin
    if (init) assume (!rst_n);
  end

  // [MIND3-TEMPLATE:same_cycle_implication] contract_property_1
  always @(posedge clk) begin
    if (!init) begin
      if (!rst_n) assert (q == 8'h00);
    end
  end

endmodule
