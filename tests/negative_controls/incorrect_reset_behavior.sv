module incorrect_reset_behavior (
    input  logic clk,
    input  logic rst_n,
    input  logic [7:0] d,
    output logic [7:0] q
);
    // Intentionally fails to reset 'q' to 0 on !rst_n (leaves it uninitialized / retains d)
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            // BUG: resetting leaves q unchanged instead of clearing to 8'h00
            q <= q;
        end else begin
            q <= d;
        end
    end
endmodule
