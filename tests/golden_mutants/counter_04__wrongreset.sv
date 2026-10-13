// UNREVIEWED golden reference RTL for dev task counter_04 (johnson_counter_8b).
// MUTANT counter_04/wrongreset (UNREVIEWED test input): violates specified property via: !rst_n |-> q == 8'h00. Must FAIL at some gate.
// Written from the task spec only (8-bit twisted-ring Johnson counter,
// 16-phase sequences; active-low synchronous rst_n). Never from model outputs.
// Owner spot-check required before any use as ground truth.
module counter_04 (
  input  logic       clk,
  input  logic       rst_n,
  output logic [7:0] q
);
  always_ff @(posedge clk) begin
    if (!rst_n)
      q <= 8'hFF;
    else
      q <= {~q[0], q[7:1]};
  end
endmodule
