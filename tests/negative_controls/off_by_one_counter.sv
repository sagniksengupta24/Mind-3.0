module off_by_one_counter (
    input  logic clk,
    input  logic rst_n,
    output logic [3:0] val
);
    // Specified to count 0..9 and roll over to 0.
    // BUG: Checks val == 10 instead of val == 9, so it reaches 10!
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            val <= 4'd0;
        end else begin
            if (val == 4'd10) begin
                val <= 4'd0;
            end else begin
                val <= val + 1'b1;
            end
        end
    end
endmodule
