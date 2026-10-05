module TopModule (
    input        clk,
    input        rst_n,
    input  [2:0] in,
    output [1:0] out
);

    // Register to hold the population count result
    reg [1:0] count_reg;

    // Combinational logic to calculate population count
    wire [1:0] count_comb;
    
    // Calculate population count using direct bit counting
    assign count_comb = {1'b0, in[2]} + {1'b0, in[1]} + {1'b0, in[0]};
    
    // Sequential block to update the output register
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count_reg <= 2'b00;
        end else begin
            count_reg <= count_comb;
        end
    end
    
    // Assign the register value to output
    assign out = count_reg;
    
endmodule