module signed_multiplier (
    input  wire signed [7:0] a,
    input  wire signed [7:0] b,
    output wire signed [15:0] p
);

    // Perform signed multiplication using explicit signed types
    assign p = a * b;

endmodule