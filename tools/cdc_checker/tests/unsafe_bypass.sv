// Unsafe bypass: a synchronizer exists, but bypass_out samples the raw
// crossing signal directly. Expected: CDC FAIL (UNSAFE_BYPASS).
module unsafe_bypass (
  input  logic clk_a,
  input  logic clk_b,
  input  logic rst_n,
  input  logic in_a,
  output logic request_b,
  output logic bypass_out
);
  logic reg_a;
  logic sync1;
  logic sync2;

  always_ff @(posedge clk_a) begin
    if (!rst_n)
      reg_a <= 1'b0;
    else
      reg_a <= in_a;
  end

  always_ff @(posedge clk_b) begin
    if (!rst_n) begin
      sync1      <= 1'b0;
      sync2      <= 1'b0;
      request_b  <= 1'b0;
      bypass_out <= 1'b0;
    end else begin
      sync1      <= reg_a;
      sync2      <= sync1;
      request_b  <= sync2;
      bypass_out <= reg_a;
    end
  end
endmodule
