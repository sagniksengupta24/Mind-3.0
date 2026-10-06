module counter_02 (
  input clk,
  input rst_n,
  input en,
  output [3:0] gray
);

  reg [3:0] gray_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      gray_reg <= 4'b0000;
    end else if (en) begin
      case (gray_reg)
        4'b0000: gray_reg <= 4'b0001;
        4'b0001: gray_reg <= 4'b0011;
        4'b0011: gray_reg <= 4'b0010;
        4'b0010: gray_reg <= 4'b0110;
        4'b0110: gray_reg <= 4'b0111;
        4'b0111: gray_reg <= 4'b0101;
        4'b0101: gray_reg <= 4'b0100;
        4'b0100: gray_reg <= 4'b1100;
        4'b1100: gray_reg <= 4'b1101;
        4'b1101: gray_reg <= 4'b1111;
        4'b1111: gray_reg <= 4'b1110;
        4'b1110: gray_reg <= 4'b1010;
        4'b1010: gray_reg <= 4'b1011;
        4'b1011: gray_reg <= 4'b1001;
        4'b1001: gray_reg <= 4'b1000;
        4'b1000: gray_reg <= 4'b0000;
        default: gray_reg <= 4'b0000;
      endcase;
    end
  end

  assign gray = gray_reg;

endmodule
