// Formal Verification Wrapper for fifo_01
module fifo_01_formal_top;

  logic clk;
  logic rst_n;
  logic wr_en;
  logic [7:0] wr_data;
  logic rd_en;
  logic [7:0] rd_data;
  logic full;
  logic empty;

  fifo_01 dut (
    .clk(clk),
    .rst_n(rst_n),
    .wr_en(wr_en),
    .wr_data(wr_data),
    .rd_en(rd_en),
    .rd_data(rd_data),
    .full(full),
    .empty(empty)
  );

  fifo_01_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .wr_en(wr_en),
    .wr_data(wr_data),
    .rd_en(rd_en),
    .rd_data(rd_data),
    .full(full),
    .empty(empty)
  );

endmodule
