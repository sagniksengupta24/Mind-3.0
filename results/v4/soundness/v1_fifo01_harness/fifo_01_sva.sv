// Deterministic formal checker for fifo_01
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module fifo_01_sva (
  input wire clk,
  input wire rst_n,
  input wire wr_en,
  input wire [7:0] wr_data,
  input wire rd_en,
  input wire [7:0] rd_data,
  input wire full,
  input wire empty
);

  // property-audit: contract_property_1 kind=boolean source=structured_template supported=True
  // property-audit: contract_property_2 kind=same_cycle_implication source=structured_template supported=True

  reg init = 1'b1;
  always @(posedge clk) init <= 1'b0;

  // [MIND3-TEMPLATE:boolean] contract_property_1
  always @(posedge clk) begin
    if (!init && rst_n) assert (!(full && empty));
  end

  // [MIND3-TEMPLATE:same_cycle_implication] contract_property_2
  always @(posedge clk) begin
    if (!init && rst_n) begin
      if (!rst_n) assert (empty == 1 && full == 0);
    end
  end

endmodule
