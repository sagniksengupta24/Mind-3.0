// Safe handshake: req synced clk_a -> clk_b, ack synced clk_b -> clk_a.
// Each direction evaluated independently. Expected: CDC PASS.
module safe_handshake (
  input  logic clk_a,
  input  logic clk_b,
  input  logic rst_n,
  input  logic start_a,
  output logic done_a
);
  logic req_a;
  logic req_s1;
  logic req_s2;
  logic ack_b;
  logic ack_s1;
  logic ack_s2;

  always_ff @(posedge clk_a) begin
    if (!rst_n) begin
      req_a <= 1'b0;
      ack_s1 <= 1'b0;
      ack_s2 <= 1'b0;
      done_a <= 1'b0;
    end else begin
      req_a  <= start_a;
      ack_s1 <= ack_b;
      ack_s2 <= ack_s1;
      done_a <= ack_s2;
    end
  end

  always_ff @(posedge clk_b) begin
    if (!rst_n) begin
      ack_b <= 1'b0;
      req_s1 <= 1'b0;
      req_s2 <= 1'b0;
    end else begin
      ack_b  <= req_s2;
      req_s1 <= req_a;
      req_s2 <= req_s1;
    end
  end
endmodule
