module counter_03 (
  input clk,
  input rst_n,
  input en,
  output [3:0] bcd_ones,
  output [3:0] bcd_tens,
  output carry_out
);

  reg [3:0] bcd_ones_reg;
  reg [3:0] bcd_tens_reg;
  reg carry_out_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      bcd_ones_reg <= 4'd0;
      bcd_tens_reg <= 4'd0;
      carry_out_reg <= 1'b0;
    end else if (en) begin
      if (bcd_ones_reg == 4'd9) begin
        bcd_ones_reg <= 4'd0;
        if (bcd_tens_reg == 4'd9) begin
          bcd_tens_reg <= 4'd0;
          carry_out_reg <= 1'b1;
        end else begin
          bcd_tens_reg <= bcd_tens_reg + 4'd1;
          carry_out_reg <= 1'b0;
        end
      end else begin
        bcd_ones_reg <= bcd_ones_reg + 4'd1;
        carry_out_reg <= 1'b0;
      end
    end else begin
      carry_out_reg <= 1'b0;
    end
  end

  assign bcd_ones = bcd_ones_reg;
  assign bcd_tens = bcd_tens_reg;
  assign carry_out = carry_out_reg;

endmodule
