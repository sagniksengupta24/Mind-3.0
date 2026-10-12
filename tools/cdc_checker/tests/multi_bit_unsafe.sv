// Multi-bit bus crossing without handshake/FIFO: per-bit staging would
// still not transfer a coherent value. Expected: CDC INCONCLUSIVE.
module multi_bit_unsafe (
  input  logic clk_a,
  input  logic clk_b,
  input  logic rst_n,
  input  logic [7:0] in_a,
  output logic [7:0] data_b
);
  logic [7:0] data_a;

  always_ff @(posedge clk_a) begin
    if (!rst_n)
      data_a <= 8'h00;
    else
      data_a <= in_a;
  end

  always_ff @(posedge clk_b) begin
    if (!rst_n)
      data_b <= 8'h00;
    else
      data_b <= data_a;
  end
endmodule
