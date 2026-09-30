module pipelined_adder (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        valid_in,
    input  wire [31:0] a,
    input  wire [31:0] b,
    output reg [31:0]  sum,
    output reg         carry_out,
    output reg         valid_out
);

reg [15:0] a_stage1, b_stage1;
reg        valid_in_d1;
reg [31:0] sum_stage2;
reg        carry_out_stage2;

always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        valid_in_d1     <= 1'b0;
        sum_stage2      <= 32'h0;
        carry_out_stage2<= 1'b0;
        valid_out       <= 1'b0;
        sum             <= 32'h0;
        carry_out       <= 1'b0;
    end else begin
        valid_in_d1     <= valid_in;
        sum_stage2      <= {a[31:16] + b[31:16] + {16{carry_out_stage2}}, a[15:0] + b[15:0]};
        carry_out_stage2<= ((a[31:16] + b[31:16]) > 16'hFFFF) || 
                          ((a[31:16] + b[31:16] == 16'hFFFF) && (carry_out_stage2 == 1'b1));
        valid_out       <= valid_in_d1;
        sum             <= sum_stage2;
        carry_out       <= carry_out_stage2;
    end
end

endmodule