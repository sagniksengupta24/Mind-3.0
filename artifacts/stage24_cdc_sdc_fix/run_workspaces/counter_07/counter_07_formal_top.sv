// Formal Verification Wrapper for counter_07
module counter_07_formal_top;

  logic clk;
  logic rst_n;
  logic clear;
  logic en;
  logic [7:0] count;
  logic max_pulse;

  counter_07 dut (
    .clk(clk),
    .rst_n(rst_n),
    .clear(clear),
    .en(en),
    .count(count),
    .max_pulse(max_pulse)
  );

  counter_07_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .clear(clear),
    .en(en),
    .count(count),
    .max_pulse(max_pulse)
  );

endmodule
