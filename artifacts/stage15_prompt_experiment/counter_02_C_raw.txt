module counter_02 (
  input clk,
  input rst_n,
  input en,
  output [3:0] gray
);

  reg [3:0] gray_reg;
  reg [3:0] next_gray;

  // Next-state logic for Gray code counter
  always @(*) begin
    if (!rst_n) begin
      next_gray = 4'b0000;
    end else if (en) begin
      // Convert binary to Gray code
      next_gray = {gray_reg[3], gray_reg[3] ^ gray_reg[2], gray_reg[2] ^ gray_reg[1], gray_reg[1] ^ gray_reg[0]};
    end
  end

  // Always block for output
  assign gray = gray_reg;

  // Synchronous reset block
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      gray_reg <= 4'b0000;
    end else begin
      gray_reg <= next_gray;
    end
  end

endmodule