// Formal Verification Wrapper for counter_03
module counter_03_formal_top;

  logic clk;
  logic rst_n;
  logic en;
  logic [3:0] bcd_ones;
  logic [3:0] bcd_tens;
  logic carry_out;

  counter_03 dut (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .bcd_ones(bcd_ones),
    .bcd_tens(bcd_tens),
    .carry_out(carry_out)
  );

  counter_03_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .en(en),
    .bcd_ones(bcd_ones),
    .bcd_tens(bcd_tens),
    .carry_out(carry_out)
  );

endmodule
