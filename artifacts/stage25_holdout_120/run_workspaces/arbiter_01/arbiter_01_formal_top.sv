// Formal Verification Wrapper for arbiter_01
module arbiter_01_formal_top;

  logic clk;
  logic rst_n;
  logic [3:0] req;
  logic [3:0] gnt;

  arbiter_01 dut (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .gnt(gnt)
  );

  arbiter_01_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .req(req),
    .gnt(gnt)
  );

endmodule
