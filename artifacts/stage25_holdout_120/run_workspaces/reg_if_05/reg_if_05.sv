module reg_if_05 (
  input clk,
  input rst_n,
  input [7:0] in_data,
  output [7:0] out_data
);

  reg [7:0] shadow_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      shadow_reg <= 8'd0;
    end else begin
      shadow_reg <= in_data;
    end
  end

  assign out_data = shadow_reg;

endmodule
