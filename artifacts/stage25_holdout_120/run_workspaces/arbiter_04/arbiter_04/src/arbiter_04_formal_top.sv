// Formal Verification Wrapper for arbiter_04
module arbiter_04_formal_top;

  logic clk;
  logic rst_n;
  logic [2:0] req;
  logic [2:0] gnt;

  arbiter_04 dut (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .gnt(gnt)
  );

  arbiter_04_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .gnt(gnt)
  );

endmodule
