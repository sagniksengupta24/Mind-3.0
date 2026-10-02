module incorrect_handshake (
    input  logic clk,
    input  logic rst_n,
    input  logic [7:0] next_data,
    input  logic ready,
    output logic valid,
    output logic [7:0] data
);
    // Protocol specification: Once valid is asserted, data MUST remain stable until ready == 1.
    // BUG: RTL updates data unconditionally on clk even when stalled (valid && !ready)!
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid <= 1'b0;
            data  <= 8'h00;
        end else begin
            valid <= 1'b1;
            // BUG: updates data while stalled, corrupting current in-flight word
            data <= next_data;
        end
    end
endmodule
