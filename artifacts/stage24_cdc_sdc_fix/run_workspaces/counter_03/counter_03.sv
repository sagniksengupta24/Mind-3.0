module counter_03 (
  input clk,
  input rst_n,
  input en,
  output [3:0] bcd_ones,
  output [3:0] bcd_tens,
  output carry_out
);

  reg [3:0] ones_reg;
  reg [3:0] tens_reg;
  reg carry_out_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ones_reg <= 4'd0;
      tens_reg <= 4'd0;
      carry_out_reg <= 1'b0;
    end else if (en) begin
      if (ones_reg == 4'd9) begin
        ones_reg <= 4'd0;
        if (tens_reg == 4'd9) begin
          tens_reg <= 4'd0;
          carry_out_reg <= 1'b1;
        end else begin
          tens_reg <= tens_reg + 4'd1;
          carry_out_reg <= 1'b0;
        end
      end else begin
        ones_reg <= ones_reg + 4'd1;
        carry_out_reg <= 1'b0;
      end
    end
  end

  assign bcd_ones = ones_reg;
  assign bcd_tens = tens_reg;
  assign carry_out = carry_out_reg;

endmodule
