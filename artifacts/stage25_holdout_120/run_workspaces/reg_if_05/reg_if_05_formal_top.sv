// Formal Verification Wrapper for reg_if_05
module reg_if_05_formal_top;

  logic clk;
  logic rst_n;
  logic [7:0] in_data;
  logic [7:0] out_data;

  reg_if_05 dut (
    .clk(clk),
    .rst_n(rst_n),
    .in_data(in_data),
    .out_data(out_data)
  );

  reg_if_05_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .in_data(in_data),
    .out_data(out_data)
  );

endmodule
