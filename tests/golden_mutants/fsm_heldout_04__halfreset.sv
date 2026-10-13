// UNREVIEWED golden reference RTL for dev task fsm_heldout_04 (sdlc_bit_stuffer_fsm).
// MUTANT fsm_heldout_04/halfreset (UNREVIEWED test input): violates specified property via: !rst_n |-> !stuffed (ones not cleared). Must FAIL at some gate.
// Written from the task spec only (insert 0 after 5 consecutive 1s).
// Owner spot-check required.
module fsm_heldout_04 (
  input  logic clk,
  input  logic rst_n,
  input  logic din,
  output logic dout,
  output logic stuffed
);
  logic [2:0] ones;

  // Synchronous active-low reset per task clock_reset_assumptions.
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      dout    <= 1'b0;
      stuffed <= 1'b0;
    end else if (ones == 3'd5) begin
      dout    <= 1'b0;
      stuffed <= 1'b1;
      ones    <= 3'd0;
    end else begin
      dout    <= din;
      stuffed <= 1'b0;
      ones    <= din ? ones + 3'd1 : 3'd0;
    end
  end
endmodule
