module TopModule (
    input        clk,
    input        rst_n,
    input  [3:0] x,
    input  [3:0] y,
    output [4:0] sum
);

    // Declare internal signals for carry propagation
    wire [3:0] carry_in;
    wire [3:0] carry_out;
    wire [4:0] full_sum;
    
    // Full adder for each bit position
    // Bit 0
    assign carry_in[0] = 1'b0;
    assign full_sum[0] = x[0] ^ y[0] ^ carry_in[0];
    assign carry_out[0] = (x[0] & y[0]) | (carry_in[0] & (x[0] ^ y[0]));
    
    // Bit 1
    assign carry_in[1] = carry_out[0];
    assign full_sum[1] = x[1] ^ y[1] ^ carry_in[1];
    assign carry_out[1] = (x[1] & y[1]) | (carry_in[1] & (x[1] ^ y[1]));
    
    // Bit 2
    assign carry_in[2] = carry_out[1];
    assign full_sum[2] = x[2] ^ y[2] ^ carry_in[2];
    assign carry_out[2] = (x[2] & y[2]) | (carry_in[2] & (x[2] ^ y[2]));
    
    // Bit 3
    assign carry_in[3] = carry_out[2];
    assign full_sum[3] = x[3] ^ y[3] ^ carry_in[3];
    assign carry_out[3] = (x[3] & y[3]) | (carry_in[3] & (x[3] ^ y[3]));
    
    // Overflow bit is the final carry out
    assign full_sum[4] = carry_out[3];
    
    // Combine all bits into sum output
    assign sum = {full_sum[4], full_sum[3], full_sum[2], full_sum[1], full_sum[0]};
    
endmodule