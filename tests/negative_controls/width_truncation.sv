module width_truncation (
    input  logic [15:0] in_a,
    input  logic [15:0] in_b,
    output logic [7:0]  out_trunc
);
    // Explicit width mismatch: assigning 16-bit sum directly to 8-bit output
    // Verilator -Wall catches this as WIDTHEXPAND / WIDTHTRUNC violation
    assign out_trunc = in_a + in_b;
endmodule
