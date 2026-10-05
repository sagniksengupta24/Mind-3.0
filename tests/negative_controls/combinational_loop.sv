module combinational_loop (
    input  logic a,
    output logic y
);
    logic x;
    assign x = ~y;
    assign y = x ^ a;
endmodule
