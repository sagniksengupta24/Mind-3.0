module reset_deassertion_problem_formal_top (
    input logic clk,
    input logic async_rst_n,
    input logic d
);
    wire q;
    reset_deassertion_problem dut (
        .clk(clk),
        .async_rst_n(async_rst_n),
        .d(d),
        .q(q)
    );

    // Invariant: deassertion of reset must be synchronous to clk
    always @(posedge clk) begin
        if ($rose(async_rst_n)) begin
            // Formal invariant: async reset deassertion must be synchronized
            assert (dut.sync_rst_n != async_rst_n);
        end
    end
endmodule
