module reg_if_04 (
  input clk,
  input rst_n,
  input [7:0] in_data,
  output [7:0] out_data
);

  reg [7:0] ram_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ram_reg <= 8'd0;
    end else begin
      ram_reg <= in_data;
    end
  end

  assign out_data = ram_reg;

endmodule
