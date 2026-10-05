module cdc_violation (
    input logic clk_a,
    input logic clk_b,
    input logic rst_n,
    input logic data_a,
    output logic data_b
);
    logic async_signal;

    always_ff @(posedge clk_a) begin
        if (!rst_n)
            async_signal <= 1'b0;
        else
            async_signal <= data_a;
    end

    // Intentional CDC defect: async_signal is sampled directly by clk_b.
    always_ff @(posedge clk_b) begin
        if (!rst_n)
            data_b <= 1'b0;
        else
            data_b <= async_signal;
    end
endmodule
