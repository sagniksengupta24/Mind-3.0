module spi_05 (
  input clk,
  input rst_n,
  input [7:0] in_data,
  output [7:0] out_data
);

  reg [7:0] out_data_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out_data_reg <= 8'd0;
    end else begin
      out_data_reg <= in_data;
    end
  end

  assign out_data = out_data_reg;

endmodule
