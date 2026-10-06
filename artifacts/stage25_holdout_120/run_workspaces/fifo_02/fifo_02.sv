module fifo_02 (
  input clk,
  input rst_n,
  input s_valid,
  output s_ready,
  input [7:0] s_data,
  output m_valid,
  input m_ready,
  output [7:0] m_data
);

  reg [7:0] stage1_data;
  reg       stage1_valid;
  reg       stage2_valid;
  reg [7:0] stage2_data;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      stage1_valid <= 1'b0;
      stage2_valid <= 1'b0;
    end else begin
      stage1_valid <= s_valid;
      stage2_valid <= stage1_valid;
    end
  end

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      stage1_data <= 8'd0;
      stage2_data <= 8'd0;
    end else if (s_valid) begin
      stage1_data <= s_data;
      stage2_data <= stage1_data;
    end
  end

  assign m_valid = stage2_valid;
  assign m_data = stage2_data;
  assign s_ready = !stage1_valid || m_ready;

endmodule
