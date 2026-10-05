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

  assign gray = gray_reg;

  function [3:0] next_gray;
    input [3:0] current_gray;
    begin
      next_gray = {current_gray[2], current_gray[3], current_gray[2] ^ current_gray[3], current_gray[0] ^ current_gray[1]};
    end
  endfunction

endmodule