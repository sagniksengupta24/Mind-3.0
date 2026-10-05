module reset_deassertion_problem (
    input  logic clk,
    input  logic async_rst_n,
    input  logic d,
    output logic q
);
    // Asynchronous reset deassertion directly sampled synchronously without a 2-flop reset synchronizer
    logic sync_rst_n;
    assign sync_rst_n = async_rst_n; // BUG: un-synchronized async reset deassertion

    always_ff @(posedge clk or negedge async_rst_n) begin
        if (!async_rst_n) begin
            q <= 1'b0;
        end else begin
            q <= d;
        end
    end
endmodule
