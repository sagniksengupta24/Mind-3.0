module counter_08 (
  input clk,
  input rst_n,
  input [7:0] incr,
  output [7:0] accum,
  output overflow
);

  reg [7:0] accum_reg;
  reg overflow_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      accum_reg <= 8'd0;
      overflow_reg <= 1'b0;
    end else begin
      // Check for overflow before updating accumulator
      // Overflow occurs when adding positive incr to positive accum
      // or adding negative incr to negative accum
      if ((accum_reg[7] == 1'b0 && incr[7] == 1'b0 && accum_reg > (8'd255 - incr)) ||
          (accum_reg[7] == 1'b1 && incr[7] == 1'b1 && accum_reg < (8'd128 + incr))) begin
        accum_reg <= {1'b1, 7'd127}; // Saturate to maximum positive value
        overflow_reg <= 1'b1;
      end else begin
        accum_reg <= accum_reg + incr;
        overflow_reg <= 1'b0;
      end
    end
  end

  assign accum = accum_reg;
  assign overflow = overflow_reg;

endmodule
