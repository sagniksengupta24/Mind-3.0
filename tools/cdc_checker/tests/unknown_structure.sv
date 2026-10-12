// Unknown structure: the crossing passes through an unanalyzed module
// instance boundary. Expected: CDC INCONCLUSIVE (never PASS).
module unknown_structure (
  input  logic clk_a,
  input  logic clk_b,
  input  logic rst_n,
  input  logic in_a,
  output logic request_b
);
  logic reg_a;
  logic w;

  always_ff @(posedge clk_a) begin
    if (!rst_n)
      reg_a <= 1'b0;
    else
      reg_a <= in_a;
  end

  black_box u (.x(reg_a), .y(w));

  always_ff @(posedge clk_b) begin
    if (!rst_n)
      request_b <= 1'b0;
    else
      request_b <= w;
  end
endmodule
