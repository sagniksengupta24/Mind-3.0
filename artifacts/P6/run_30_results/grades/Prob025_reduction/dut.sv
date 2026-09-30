module TopModule (
    input        clk,
    input        rst_n,
    input [7:0]  in,
    output       parity
);

    // Register to store the computed parity
    reg parity_reg;

    // Compute even parity using XOR of all 8 bits
    // Even parity = XOR of all input bits
    always @(*) begin
        parity_reg = in[0] ^ in[1] ^ in[2] ^ in[3] ^ in[4] ^ in[5] ^ in[6] ^ in[7];
    end

    // Synchronous reset and clocking
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            parity <= 1'b0;
        end else begin
            parity <= parity_reg;
        end
    end

endmodule