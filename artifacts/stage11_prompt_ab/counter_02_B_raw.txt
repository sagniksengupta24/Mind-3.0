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
      gray_reg <= next_gray(gray_reg);
    end
  end

  function [3:0] next_gray;
    input [3:0] gray;
    begin
      next_gray = gray ^ (gray >> 1);
    end
  endfunction

  assign gray = gray_reg;

endmodule