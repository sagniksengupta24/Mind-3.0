module timing_violation (
    input logic clk,
    input logic [7:0] a,
    output logic [7:0] y
);
    (* keep = 1 *) logic [7:0] r0, r1, r2;
    always_ff @(posedge clk) begin
        r0 <= a;
        r1 <= r0;
        r2 <= r1;
    end
    assign y = r2;
endmodule
