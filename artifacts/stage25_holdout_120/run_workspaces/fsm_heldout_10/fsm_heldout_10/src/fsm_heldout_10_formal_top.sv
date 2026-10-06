// Formal Verification Wrapper for fsm_heldout_10
module fsm_heldout_10_formal_top;

  logic clk;
  logic rst_n;
  logic [1:0] state_out;

  fsm_heldout_10 dut (
    .clk(clk),
    .rst_n(rst_n),
    .state_out(state_out)
  );

  fsm_heldout_10_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .state_out(state_out)
  );

endmodule
