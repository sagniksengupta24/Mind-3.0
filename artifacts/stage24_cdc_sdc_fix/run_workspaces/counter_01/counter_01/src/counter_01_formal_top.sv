// Formal Verification Wrapper for counter_01
module counter_01_formal_top;

  logic clk;
  logic rst_n;
  logic up;
  logic down;
  logic [7:0] count;

  counter_01 dut (
    .clk(clk),
    .rst_n(rst_n),
    .up(up),
    .down(down),
    .count(count)
  );

  counter_01_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .up(up),
    .down(down),
    .count(count)
  );

endmodule
