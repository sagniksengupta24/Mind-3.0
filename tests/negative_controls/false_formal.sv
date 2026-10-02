module false_formal (
    input logic clk,
    input logic rst_n,
    output logic q
);
    always_ff @(posedge clk) begin
        if (!rst_n)
            q <= 1'b0;
        else
            q <= ~q;
    end
endmodule
