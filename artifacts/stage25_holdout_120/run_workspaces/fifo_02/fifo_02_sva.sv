// Deterministic formal checker for fifo_02
// Property bodies are rendered by Mind 3.0 templates, not copied from the model.
module fifo_02_sva (
  input wire clk,
  input wire rst_n,
  input wire s_valid,
  input wire s_ready,
  input wire [7:0] s_data,
  input wire m_valid,
  input wire m_ready,
  input wire [7:0] m_data
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
      if (!rst_n) assert (!m_valid && s_ready);
    end
  end

endmodule
