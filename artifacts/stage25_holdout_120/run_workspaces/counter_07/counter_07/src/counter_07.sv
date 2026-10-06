module counter_07 (
  input clk,
  input rst_n,
  input clear,
  input en,
  output [7:0] count,
  output max_pulse
);

  reg [7:0] count_reg;
  reg max_pulse_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count_reg <= 8'd0;
      max_pulse_reg <= 1'b0;
    end else begin
      if (clear) begin
        count_reg <= 8'd0;
        max_pulse_reg <= 1'b0;
      end else if (en) begin
        if (count_reg == 8'd255) begin
          count_reg <= 8'd0;
          max_pulse_reg <= 1'b1;
        end else begin
          count_reg <= count_reg + 8'd1;
          max_pulse_reg <= 1'b0;
        end
      end else begin
        max_pulse_reg <= 1'b0;
      end
    end
  end

  assign count = count_reg;
  assign max_pulse = max_pulse_reg;

endmodule
