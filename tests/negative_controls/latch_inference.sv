module latch_inference (
    input  logic a,
    input  logic en,
    output logic y
);
    always_comb begin
        if (en)
            y = a;
        // Intentional bug: no else/default assignment => latch.
    end
endmodule
