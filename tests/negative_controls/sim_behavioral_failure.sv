module sim_behavioral_failure (
    input  logic clk,
    input  logic rst_n,
    input  logic [7:0] a,
    input  logic [7:0] b,
    output logic [7:0] sum
);
    // Compiles and elaborates completely clean.
    // BUG: Subtracts instead of adds (behavioral semantic bug only caught by simulation)
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sum <= 8'd0;
        end else begin
            sum <= a - b; // BUG: Should be a + b
        end
    end
endmodule
