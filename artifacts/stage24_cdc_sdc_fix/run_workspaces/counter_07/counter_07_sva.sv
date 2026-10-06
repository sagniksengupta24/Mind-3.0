// Deterministic formal checker for counter_07
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module counter_07_sva (
  input wire clk,
  input wire rst_n,
  input wire clear,
  input wire en,
  input wire [7:0] count,
  input wire max_pulse
);

  // property-audit: contract_property_1 kind=next_cycle_implication source=structured_template supported=True
  // property-audit: contract_property_2 kind=same_cycle_implication source=structured_template supported=True

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
      if ($past(clear)) assert (count == 8'd0);
    end
  end

  // [MIND3-TEMPLATE:same_cycle_implication] contract_property_2
  always @(posedge clk) begin
    if (!init && rst_n) begin
      if (count == 8'd255) assert (max_pulse == 1);
    end
  end

endmodule
