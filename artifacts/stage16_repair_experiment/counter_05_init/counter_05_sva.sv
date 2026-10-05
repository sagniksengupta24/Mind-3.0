// Deterministic formal checker for counter_05
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module counter_05_sva (
  input wire clk,
  input wire rst_n,
  input wire kick,
  input wire fault
);

  // property-audit: contract_property_1 kind=same_cycle_implication source=structured_template supported=True
  // property-audit: contract_property_2 kind=next_cycle_implication source=structured_template supported=True

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;

  // [MIND3-TEMPLATE:same_cycle_implication] contract_property_1
  always @(posedge clk) begin
    if (!init) begin
      if (!rst_n) assert (fault == 0);
    end
  end

  // [MIND3-TEMPLATE:next_cycle_implication] contract_property_2
  always @(posedge clk) begin
    if (!init && rst_n) begin
      if ($past(fault)) assert (fault);
    end
  end

endmodule
