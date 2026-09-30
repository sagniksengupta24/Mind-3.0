module TopModule (
    input        clk,
    input        rst_n,
    input [1023:0] in,
    input [7:0]  sel,
    output [3:0] out
);

    // Register to hold the selected 4-bit value
    reg [3:0] selected_output;

    // Combinational logic to select the appropriate 4-bit input
    always @(*) begin
        // Calculate the starting bit position for the selected 4-bit input
        // Each 4-bit input is packed sequentially, so we multiply sel by 4
        int index;
        index = sel * 4;
        
        // Extract the 4-bit value at the calculated index
        selected_output = in[index +: 4];
    end

    // Synchronous reset and clocking
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out <= 4'b0;
        end else begin
            out <= selected_output;
        end
    end

endmodule