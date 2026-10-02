module signed_unsigned_error (
    input  logic signed [7:0] val_signed,
    input  logic [7:0]        threshold_unsigned,
    output logic              is_below_threshold
);
    // Verilog pitfall: Mixing signed and unsigned operands coerces val_signed to unsigned!
    // If val_signed is negative (-1 = 8'hFF = 255), 255 < 10 is FALSE!
    always_comb begin
        is_below_threshold = (val_signed < threshold_unsigned);
    end
endmodule
