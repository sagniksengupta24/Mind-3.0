// Formal Verification Wrapper for counter_05
module counter_05_formal_top;

  logic clk;
  logic rst_n;
  logic kick;
  logic fault;

  counter_05 dut (
    .clk(clk),
    .rst_n(rst_n),
    .kick(kick),
    .fault(fault)
  );

  counter_05_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .kick(kick),
    .fault(fault)
  );

endmodule
