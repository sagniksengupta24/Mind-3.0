// Formal Verification Wrapper for counter_10
module counter_10_formal_top;

  logic clk;
  logic rst_n;
  logic strobe;
  logic [7:0] count;

  counter_10 dut (
    .clk(clk),
    .rst_n(rst_n),
    .strobe(strobe),
    .count(count)
  );

  counter_10_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .strobe(strobe),
    .count(count)
  );

endmodule
