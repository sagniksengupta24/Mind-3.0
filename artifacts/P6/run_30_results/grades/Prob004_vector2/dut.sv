module TopModule (
    input        clk,
    input        rst_n,
    input  [31:0] in,
    output [31:0] out
);

    // Declare registers for the output data
    reg [31:0] out_reg;

    // Sequential block to handle byte reversal on clock edge
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_reg <= 32'h0;
        end else begin
            // Reverse byte order: 
            // in[31:24] -> out[7:0]
            // in[23:16] -> out[15:8]
            // in[15:8]  -> out[23:16]
            // in[7:0]   -> out[31:24]
            out_reg[ 7: 0] <= in[31:24];
            out_reg[15: 8] <= in[23:16];
            out_reg[23:16] <= in[15: 8];
            out_reg[31:24] <= in[ 7: 0];
        end
    end

    // Assign the output register to the output signal
    assign out = out_reg;

endmodule