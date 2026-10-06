module reg_if_06 (
  input clk,
  input rst_n,
  input [7:0] in_data,
  output [7:0] out_data
);

  reg [7:0] interrupt_status;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      interrupt_status <= 8'd0;
    end else begin
      interrupt_status <= interrupt_status | in_data;
    end
  end

  assign out_data = interrupt_status;

endmodule
