// Formal Verification Wrapper for counter_08
module counter_08_formal_top;

  logic clk;
  logic rst_n;
  logic [7:0] incr;
  logic [7:0] accum;
  logic overflow;

  counter_08 dut (
    .clk(clk),
    .rst_n(rst_n),
    .incr(incr),
    .accum(accum),
    .overflow(overflow)
  );

  counter_08_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .incr(incr),
    .accum(accum),
    .overflow(overflow)
  );

endmodule
