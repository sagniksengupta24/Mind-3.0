module signed_unsigned_error_formal_top (
    input logic clk,
    input logic signed [7:0] val_signed,
    input logic [7:0] threshold_unsigned
);
    wire is_below_threshold;
    signed_unsigned_error dut (
        .val_signed(val_signed),
        .threshold_unsigned(threshold_unsigned),
        .is_below_threshold(is_below_threshold)
    );

    always @(posedge clk) begin
        // If val_signed is negative and threshold is positive (e.g. 10), it MUST be below threshold!
        if (val_signed < 0 && threshold_unsigned == 8'd10) begin
            assert (is_below_threshold == 1'b1);
        end
    end
endmodule
