// UNREVIEWED golden reference RTL for dev task reset_02 (glitch_free_reset_mux).
// MUTANT reset_02/noreset (UNREVIEWED test input): violates specified property via: !rst_n |-> out_data == 0. Must FAIL at some gate.
// Written from the task spec only (registered data path cleared while reset
// is asserted; active-low synchronous rst_n). Owner spot-check required.
module reset_02 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [7:0] in_data,
  output logic [7:0] out_data
);
  always_ff @(posedge clk) begin
    out_data <= in_data;
  end
endmodule
