// Unsafe direct crossing: reg_a (clk_a) sampled straight into clk_b.
// Expected: CDC FAIL (UNSAFE_DIRECT).
module unsafe_direct (
  input  logic clk_a,
  input  logic clk_b,
  input  logic rst_n,
  input  logic in_a,
  output logic request_b
);
  logic reg_a;

  always_ff @(posedge clk_a) begin
    if (!rst_n)
      reg_a <= 1'b0;
    else
      reg_a <= in_a;
  end

  always_ff @(posedge clk_b) begin
    if (!rst_n)
      request_b <= 1'b0;
    else
      request_b <= reg_a;
  end
endmodule
