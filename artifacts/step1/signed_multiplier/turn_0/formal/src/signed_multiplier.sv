module signed_multiplier (
    input  wire signed [7:0] a,
    input  wire signed [7:0] b,
    output wire signed [15:0] p
);

    // Use standard signed multiplication - synthesizer will handle two's complement correctly
    assign p = a * b;

endmodule