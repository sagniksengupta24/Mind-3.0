module counter_01 (
  input clk,
  input rst_n,
  input up,
  input down,
  output [7:0] count
);

  reg [7:0] count_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count_reg <= 8'h00;
    end else begin
      if (up && !down) begin
        if (count_reg == 8'hFF) begin
          count_reg <= 8'hFF;
        end else begin
          count_reg <= count_reg + 8'd1;
        end
      end else if (!up && down) begin
        if (count_reg == 8'h00) begin
          count_reg <= 8'h00;
        end else begin
          count_reg <= count_reg - 8'd1;
        end
      end else begin
        // No change when both or neither up/down are asserted
        count_reg <= count_reg;
      end
    end
  end

  assign count = count_reg;

endmodule
