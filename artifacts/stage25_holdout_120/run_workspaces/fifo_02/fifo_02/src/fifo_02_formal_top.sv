// Formal Verification Wrapper for fifo_02
module fifo_02_formal_top;

  logic clk;
  logic rst_n;
  logic s_valid;
  logic s_ready;
  logic [7:0] s_data;
  logic m_valid;
  logic m_ready;
  logic [7:0] m_data;

  fifo_02 dut (
    .clk(clk),
    .rst_n(rst_n),
    .s_valid(s_valid),
    .s_ready(s_ready),
    .s_data(s_data),
    .m_valid(m_valid),
    .m_ready(m_ready),
    .m_data(m_data)
  );

  fifo_02_sva sva (
    .clk(clk),
    .rst_n(rst_n),
    .s_valid(s_valid),
    .s_ready(s_ready),
    .s_data(s_data),
    .m_valid(m_valid),
    .m_ready(m_ready),
    .m_data(m_data)
  );

endmodule
