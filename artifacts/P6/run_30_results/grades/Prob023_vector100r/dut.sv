module TopModule (
    input        clk,
    input        rst_n,
    input [99:0] in,
    output [99:0] out
);

    // Register to hold the reversed bits
    reg [99:0] reversed_bits;

    // Sequential block to process input on clock edge
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reversed_bits <= 100'b0;
        end else begin
            // Reverse the bit ordering
            reversed_bits[99] <= in[0];
            reversed_bits[98] <= in[1];
            reversed_bits[97] <= in[2];
            reversed_bits[96] <= in[3];
            reversed_bits[95] <= in[4];
            reversed_bits[94] <= in[5];
            reversed_bits[93] <= in[6];
            reversed_bits[92] <= in[7];
            reversed_bits[91] <= in[8];
            reversed_bits[90] <= in[9];
            reversed_bits[89] <= in[10];
            reversed_bits[88] <= in[11];
            reversed_bits[87] <= in[12];
            reversed_bits[86] <= in[13];
            reversed_bits[85] <= in[14];
            reversed_bits[84] <= in[15];
            reversed_bits[83] <= in[16];
            reversed_bits[82] <= in[17];
            reversed_bits[81] <= in[18];
            reversed_bits[80] <= in[19];
            reversed_bits[79] <= in[20];
            reversed_bits[78] <= in[21];
            reversed_bits[77] <= in[22];
            reversed_bits[76] <= in[23];
            reversed_bits[75] <= in[24];
            reversed_bits[74] <= in[25];
            reversed_bits[73] <= in[26];
            reversed_bits[72] <= in[27];
            reversed_bits[71] <= in[28];
            reversed_bits[70] <= in[29];
            reversed_bits[69] <= in[30];
            reversed_bits[68] <= in[31];
            reversed_bits[67] <= in[32];
            reversed_bits[66] <= in[33];
            reversed_bits[65] <= in[34];
            reversed_bits[64] <= in[35];
            reversed_bits[63] <= in[36];
            reversed_bits[62] <= in[37];
            reversed_bits[61] <= in[38];
            reversed_bits[60] <= in[39];
            reversed_bits[59] <= in[40];
            reversed_bits[58] <= in[41];
            reversed_bits[57] <= in[42];
            reversed_bits[56] <= in[43];
            reversed_bits[55] <= in[44];
            reversed_bits[54] <= in[45];
            reversed_bits[53] <= in[46];
            reversed_bits[52] <= in[47];
            reversed_bits[51] <= in[48];
            reversed_bits[50] <= in[49];
            reversed_bits[49] <= in[50];
            reversed_bits[48] <= in[51];
            reversed_bits[47] <= in[52];
            reversed_bits[46] <= in[53];
            reversed_bits[45] <= in[54];
            reversed_bits[44] <= in[55];
            reversed_bits[43] <= in[56];
            reversed_bits[42] <= in[57];
            reversed_bits[41] <= in[58];
            reversed_bits[40] <= in[59];
            reversed_bits[39] <= in[60];
            reversed_bits[38] <= in[61];
            reversed_bits[37] <= in[62];
            reversed_bits[36] <= in[63];
            reversed_bits[35] <= in[64];
            reversed_bits[34] <= in[65];
            reversed_bits[33] <= in[66];
            reversed_bits[32] <= in[67];
            reversed_bits[31] <= in[68];
            reversed_bits[30] <= in[69];
            reversed_bits[29] <= in[70];
            reversed_bits[28] <= in[71];
            reversed_bits[27] <= in[72];
            reversed_bits[26] <= in[73];
            reversed_bits[25] <= in[74];
            reversed_bits[24] <= in[75];
            reversed_bits[23] <= in[76];
            reversed_bits[22] <= in[77];
            reversed_bits[21] <= in[78];
            reversed_bits[20] <= in[79];
            reversed_bits[19] <= in[80];
            reversed_bits[18] <= in[81];
            reversed_bits[17] <= in[82];
            reversed_bits[16] <= in[83];
            reversed_bits[15] <= in[84];
            reversed_bits[14] <= in[85];
            reversed_bits[13] <= in[86];
            reversed_bits[12] <= in[87];
            reversed_bits[11] <= in[88];
            reversed_bits[10] <= in[89];
            reversed_bits[9] <= in[90];
            reversed_bits[8] <= in[91];
            reversed_bits[7] <= in[92];
            reversed_bits[6] <= in[93];
            reversed_bits[5] <= in[94];
            reversed_bits[4] <= in[95];
            reversed_bits[3] <= in[96];
            reversed_bits[2] <= in[97];
            reversed_bits[1] <= in[98];
            reversed_bits[0] <= in[99];
        end
    end

    // Assign the reversed bits to output
    assign out = reversed_bits;

endmodule