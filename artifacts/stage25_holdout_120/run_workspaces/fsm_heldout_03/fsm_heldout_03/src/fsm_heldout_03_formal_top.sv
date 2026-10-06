// Formal Verification Wrapper for fsm_heldout_03
module fsm_heldout_03_formal_top;

  logic clk;
  logic rst_n;
  logic [1:0] ev;
  logic [2:0] state;

  fsm_heldout_03 dut (
    .clk(clk),
    .rst_n(rst_n),
    .ev(ev),
    .state(state)
  );

  fsm_heldout_03_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .ev(ev),
    .state(state)
  );

endmodule
