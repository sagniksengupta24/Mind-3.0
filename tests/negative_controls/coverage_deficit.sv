module coverage_deficit (
    input logic clk,
    input logic sel,
    input logic a,
    input logic b,
    output logic y
);
    always_ff @(posedge clk) begin
        if (sel)
            y <= a;
        else
            y <= b;
    end
endmodule
