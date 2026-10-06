module uart_08 (
  input clk,
  input rst_n,
  input [7:0] in_data,
  output [7:0] out_data
);

  reg [7:0] out_data_reg;
  reg [1:0] glitch_filter_counter;
  reg sample_valid;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out_data_reg <= 8'd0;
      glitch_filter_counter <= 2'd0;
      sample_valid <= 1'b0;
    end else begin
      // Update glitch filter counter
      if (glitch_filter_counter > 0) begin
        glitch_filter_counter <= glitch_filter_counter - 1;
      end

      // When a new sample is valid and no active filtering
      if (sample_valid && glitch_filter_counter == 0) begin
        out_data_reg <= in_data;
      end

      // Detect start of new data sample (assuming in_data transitions from 1 to 0)
      // This assumes that the start bit is low for one sample period
      if (!in_data[0] && sample_valid) begin
        // Start glitch filtering - reset counter to 3 (for 4 clock samples)
        glitch_filter_counter <= 2'd3;
      end

      // Sample valid flag - assume we sample at every clock cycle
      // and that the first bit is a start bit, so we consider valid after
      // one full sample period (i.e., after 10 bits of data including start/stop)
      // This is a simplified model; actual UART uses baud rate divider.
      // We will treat each incoming bit as a valid sample assuming it's not a glitch.
      if (!sample_valid) begin
        sample_valid <= 1'b1;
      end else begin
        sample_valid <= 1'b0;
      end

    end
  end

  assign out_data = out_data_reg;

endmodule
