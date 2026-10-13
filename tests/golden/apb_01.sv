// UNREVIEWED golden reference RTL for dev task apb_01 (apb_gpio_controller).
// Written from the task spec only (registered GPIO loopback with reset clear).
// Owner spot-check required.
module apb_01 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [7:0] in_data,
  output logic [7:0] out_data
);
  always_ff @(posedge clk) begin
    if (!rst_n)
      out_data <= 8'h00;
    else
      out_data <= in_data;
  end
endmodule
