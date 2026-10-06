// Formal Verification Wrapper for arbiter_05
module arbiter_05_formal_top;

  logic clk;
  logic rst_n;
  logic [3:0] req;
  logic [3:0] gnt;

  arbiter_05 dut (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .gnt(gnt)
  );

  arbiter_05_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .gnt(gnt)
  );

endmodule
