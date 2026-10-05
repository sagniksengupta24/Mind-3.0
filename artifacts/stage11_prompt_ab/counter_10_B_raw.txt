module counter_10 (
  input clk,
  input rst_n,
  input strobe,
  output [7:0] count
);

  reg [7:0] count_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count_reg <= 8'd0;
    end else begin
      if (strobe) begin
        count_reg <= count_reg + 1;
      end else begin
        count_reg <= count_reg;
      end
    end
  end

  assign count = count_reg;

endmodule