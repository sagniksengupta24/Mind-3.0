module counter_06 (
  input clk,
  input rst_n,
  input [7:0] div_val,
  output clk_out
);

  reg [7:0] counter;
  reg clk_out_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      counter <= 8'd0;
      clk_out_reg <= 1'b0;
    end else begin
      if (counter == 0) begin
        counter <= div_val;
        clk_out_reg <= ~clk_out_reg;
      end else begin
        counter <= counter - 1'd1;
      end
    end
  end

  assign clk_out = clk_out_reg;

endmodule
