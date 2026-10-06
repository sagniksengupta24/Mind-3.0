module counter_10 (
  input clk,
  input rst_n,
  input strobe,
  output [7:0] count
);

  reg [7:0] count_reg;
  reg strobe_prev;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count_reg <= 8'd0;
      strobe_prev <= 1'b0;
    end else begin
      if (strobe != strobe_prev) begin
        count_reg <= count_reg + 8'd1;
      end
      strobe_prev <= strobe;
    end
  end

  assign count = count_reg;

endmodule
