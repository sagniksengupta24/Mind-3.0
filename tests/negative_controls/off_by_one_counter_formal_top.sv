module off_by_one_counter_formal_top (
    input logic clk,
    input logic rst_n
);
    wire [3:0] val;
    off_by_one_counter dut (.clk(clk), .rst_n(rst_n), .val(val));

    always @(posedge clk) begin
        if (rst_n) begin
            // Invariant: modulo-10 counter must NEVER exceed 9
            assert (val <= 4'd9);
        end
    end
endmodule
