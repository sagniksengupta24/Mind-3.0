// Formal Verification Wrapper for counter_04
module counter_04_formal_top;

  logic clk;
  logic rst_n;
  logic [7:0] q;

  counter_04 dut (
    .clk(clk),
    .rst_n(rst_n),
    .q(q)
  );

  counter_04_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .q(q)
  );

endmodule
