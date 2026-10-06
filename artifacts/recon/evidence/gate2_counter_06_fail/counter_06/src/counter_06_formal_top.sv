// Formal Verification Wrapper for counter_06
module counter_06_formal_top;

  logic clk;
  logic rst_n;
  logic [7:0] div_val;
  logic clk_out;

  counter_06 dut (
    .clk(clk),
    .rst_n(rst_n),
    .div_val(div_val),
    .clk_out(clk_out)
  );

  counter_06_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .div_val(div_val),
    .clk_out(clk_out)
  );

endmodule
