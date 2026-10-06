module counter_09 (
  input clk,
  input rst_n,
  output [7:0] lfsr_out
);

  reg [7:0] lfsr_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      lfsr_reg <= 8'h01;
    end else begin
      lfsr_reg <= {lfsr_reg[6:0], lfsr_reg[7] ^ lfsr_reg[5] ^ lfsr_reg[4] ^ lfsr_reg[3]};
    end
  end

  assign lfsr_out = lfsr_reg;

endmodule
