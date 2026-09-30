module signed_multiplier_formal(
    input wire signed [7:0] a,
    input wire signed [7:0] b
);
    wire signed [15:0] p;
    signed_multiplier dut (.a(a), .b(b), .p(p));

    always @(*) begin
        assert(p == a * b);
    end
endmodule
