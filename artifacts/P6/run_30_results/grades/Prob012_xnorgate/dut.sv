module TopModule (
    input  wire a,
    input  wire b,
    output wire out
);

    // XNOR implementation: out = (a && b) || (!a && !b)
    // or equivalently: out = !(a ^ b)
    assign out = ~(a ^ b);

endmodule