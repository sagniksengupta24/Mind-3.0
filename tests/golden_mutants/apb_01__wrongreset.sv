// UNREVIEWED golden reference RTL for dev task apb_01 (apb_gpio_controller).
// MUTANT apb_01/wrongreset (UNREVIEWED test input): violates specified property via: !rst_n |-> out_data == 0. Must FAIL at some gate.
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
      out_data <= 8'hFF;
    else
      out_data <= in_data;
  end
endmodule
