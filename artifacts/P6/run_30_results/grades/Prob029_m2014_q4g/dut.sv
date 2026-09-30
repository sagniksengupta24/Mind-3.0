module TopModule (
    input  wire in1,
    input  wire in2,
    input  wire in3,
    output wire out
);

    wire xnor_out;

    // XNOR gate: outputs 1 when both inputs are equal
    assign xnor_out = (in1 == in2);
    
    // XOR gate: outputs 1 when inputs are different
    assign out = (xnor_out != in3);

endmodule