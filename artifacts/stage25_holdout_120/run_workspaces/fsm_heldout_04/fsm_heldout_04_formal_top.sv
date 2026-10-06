// Formal Verification Wrapper for fsm_heldout_04
module fsm_heldout_04_formal_top;

  logic clk;
  logic rst_n;
  logic din;
  logic dout;
  logic stuffed;

  fsm_heldout_04 dut (
    .clk(clk),
    .rst_n(rst_n),
    .din(din),
    .dout(dout),
    .stuffed(stuffed)
  );

  fsm_heldout_04_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .din(din),
    .dout(dout),
    .stuffed(stuffed)
  );

endmodule
