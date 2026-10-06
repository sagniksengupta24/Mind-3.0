module reg_if_10 (
  input clk,
  input rst_n,
  input [7:0] in_data,
  output [7:0] out_data
);

  reg [7:0] reg_file;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      reg_file <= 8'd0;
    end else begin
      reg_file <= in_data;
    end
  end

  assign out_data = reg_file;

endmodule
