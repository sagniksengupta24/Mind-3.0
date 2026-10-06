// Formal Verification Wrapper for counter_09
module counter_09_formal_top;

  logic clk;
  logic rst_n;
  logic [7:0] lfsr_out;

  counter_09 dut (
    .clk(clk),
    .rst_n(rst_n),
    .lfsr_out(lfsr_out)
  );

  counter_09_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .lfsr_out(lfsr_out)
  );

endmodule
