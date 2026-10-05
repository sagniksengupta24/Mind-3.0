module counter_02 (
  input clk,
  input rst_n,
  input en,
  output [3:0] gray
);

  // Internal 4-bit register to store the Gray code
  reg [3:0] gray_reg;

  // Combinational logic to generate the next Gray code value
  always @(*) begin
    if (rst_n == 0) begin
      gray_reg = 4'b0000;
    end else if (en) begin
      gray_reg = gray_reg ^ (gray_reg >> 1);
    end
  end

  // Assign the Gray code register to the output
  assign gray = gray_reg;

endmodule