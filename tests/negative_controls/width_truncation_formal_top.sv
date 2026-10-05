module width_truncation_formal_top (
    input logic clk,
    input logic [15:0] in_a,
    input logic [15:0] in_b
);
    wire [7:0] out_trunc;
    width_truncation dut (.in_a(in_a), .in_b(in_b), .out_trunc(out_trunc));

    always @(posedge clk) begin
        // Truncation causes mathematical mismatch when sum exceeds 8-bit range
        assert (out_trunc == in_a + in_b);
    end
endmodule
