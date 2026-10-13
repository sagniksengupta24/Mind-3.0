// UNREVIEWED golden reference RTL for dev task apb_01 (apb_gpio_controller).
// MUTANT apb_01/slowreset (UNREVIEWED test input): violates specified property via: !rst_n |-> out_data == 0 (2-cycle reset). Must FAIL at some gate.
// Written from the task spec only (registered GPIO loopback with reset clear).
// Owner spot-check required.
module apb_01 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [7:0] in_data,
  output logic [7:0] out_data
);
  logic [7:0] pipe;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      pipe <= 8'h00;
      out_data <= pipe;
    end else begin
      pipe <= in_data;
      out_data <= pipe;
    end
  end
endmodule
