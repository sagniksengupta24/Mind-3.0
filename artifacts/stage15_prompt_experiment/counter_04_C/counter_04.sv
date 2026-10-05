module counter_04 (
  input clk,
  input rst_n,
  output [7:0] q
);

  reg [7:0] q_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      q_reg <= 8'h00;
    end else begin
      q_reg <= {q_reg[6:0], q_reg[7]};
    end
  end

  assign q = q_reg;

endmodule