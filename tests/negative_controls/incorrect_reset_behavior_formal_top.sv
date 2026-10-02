module incorrect_reset_behavior_formal_top (
    input logic clk,
    input logic rst_n,
    input logic [7:0] d
);
    wire [7:0] q;
    incorrect_reset_behavior dut (
        .clk(clk),
        .rst_n(rst_n),
        .d(d),
        .q(q)
    );

    always @(posedge clk) begin
        if (!rst_n) begin
            // Formal invariant: reset must drive q to 0
            assert (q == 8'h00);
        end
    end
endmodule
