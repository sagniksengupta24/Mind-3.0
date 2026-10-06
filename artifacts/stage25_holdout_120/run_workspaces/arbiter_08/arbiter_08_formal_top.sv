// Formal Verification Wrapper for arbiter_08
module arbiter_08_formal_top;

  logic clk;
  logic rst_n;
  logic [3:0] cluster_req;
  logic [3:0] gnt;

  arbiter_08 dut (
    .clk(clk),
    .rst_n(rst_n),
    .cluster_req(cluster_req),
    .gnt(gnt)
  );

  arbiter_08_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .cluster_req(cluster_req),
    .gnt(gnt)
  );

endmodule
