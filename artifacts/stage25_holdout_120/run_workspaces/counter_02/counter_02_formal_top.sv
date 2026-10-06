// Formal Verification Wrapper for counter_02
module counter_02_formal_top;

  logic clk;
  logic rst_n;
  logic en;
  logic [3:0] gray;

  counter_02 dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .gray(gray)
  );

  counter_02_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .gray(gray)
  );

endmodule
