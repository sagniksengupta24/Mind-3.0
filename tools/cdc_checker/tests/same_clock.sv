// Single-clock pipe: no crossing can exist. Expected: CDC PASS.
module same_clock (
  input  logic clk,
  input  logic rst_n,
  input  logic [7:0] in_data,
  output logic [7:0] out_data
);
  always_ff @(posedge clk) begin
    if (!rst_n)
      out_data <= 8'h00;
    else
      out_data <= in_data;
  end
endmodule
