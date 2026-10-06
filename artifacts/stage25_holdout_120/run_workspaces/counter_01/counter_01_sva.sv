// Deterministic formal checker for counter_01
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module counter_01_sva (
  input wire clk,
  input wire rst_n,
  input wire up,
  input wire down,
  input wire [7:0] count
);

  // property-audit: contract_property_1 kind=next_cycle_implication source=structured_template supported=True
  // property-audit: contract_property_2 kind=next_cycle_implication source=structured_template supported=True

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;

  // BMC starts from reset: real designs boot with reset asserted.
  // Without this, uninitialized flops take any value and every
  // stateful design fails vacuously once the init guard lifts.
  always @(posedge clk) begin
    if (init) assume (!rst_n);
  end

  // [MIND3-TEMPLATE:next_cycle_implication] contract_property_1
  always @(posedge clk) begin
    if (!init && rst_n) begin
      if ($past(count == 8'hFF && up && !down)) assert (count == 8'hFF);
    end
  end

  // [MIND3-TEMPLATE:next_cycle_implication] contract_property_2
  always @(posedge clk) begin
    if (!init && rst_n) begin
      if ($past(count == 8'h00 && !up && down)) assert (count == 8'h00);
    end
  end

endmodule
