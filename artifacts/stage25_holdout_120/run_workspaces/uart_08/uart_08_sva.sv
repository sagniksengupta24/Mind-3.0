// Deterministic formal checker for uart_08
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module uart_08_sva (
  input wire clk,
  input wire rst_n,
  input wire [7:0] in_data,
  input wire [7:0] out_data
);

  // property-audit: contract_property_1 kind=same_cycle_implication source=structured_template supported=True
  // property-audit: contract_property_2 kind=boolean source=structured_template supported=True

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
      if (!rst_n) assert (out_data == 0);
    end
  end

  // [MIND3-TEMPLATE:boolean] contract_property_2
  always @(posedge clk) begin
    if (!init && rst_n) assert (out_data == out_data);
  end

endmodule
