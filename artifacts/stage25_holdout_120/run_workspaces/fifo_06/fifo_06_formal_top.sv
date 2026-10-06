// Formal Verification Wrapper for fifo_06
module fifo_06_formal_top;

  logic clk;
  logic rst_n;
  logic valid_in;
  logic ready_out;
  logic valid_out;
  logic ready_in;

  fifo_06 dut (
    .clk(clk),
    .rst_n(rst_n),
    .valid_in(valid_in),
    .ready_out(ready_out),
    .valid_out(valid_out),
    .ready_in(ready_in)
  );

  fifo_06_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .valid_in(valid_in),
    .ready_out(ready_out),
    .valid_out(valid_out),
    .ready_in(ready_in)
  );

endmodule
