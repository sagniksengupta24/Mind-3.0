// Formal Verification Wrapper for spi_04
module spi_04_formal_top;

  logic clk;
  logic rst_n;
  logic [7:0] in_data;
  logic [7:0] out_data;

  spi_04 dut (
    .clk(clk),
    .rst_n(rst_n),
    .in_data(in_data),
    .out_data(out_data)
  );

  spi_04_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .in_data(in_data),
    .out_data(out_data)
  );

endmodule
