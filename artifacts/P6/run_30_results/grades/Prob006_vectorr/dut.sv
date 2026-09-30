module TopModule (
    input        clk,
    input        rst_n,
    input  [7:0] in,
    output [7:0] out
);

    reg [7:0] reversed_out;
    reg [2:0] bit_index;
    reg       shift_reg_valid;
    reg [7:0] shift_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reversed_out <= 8'b0;
            bit_index    <= 3'd0;
            shift_reg_valid <= 1'b0;
            shift_reg <= 8'b0;
        end else begin
            if (bit_index < 8) begin
                shift_reg <= {in[7], shift_reg[7:1]};
                bit_index <= bit_index + 1;
                shift_reg_valid <= 1'b1;
            end else begin
                reversed_out <= shift_reg;
                shift_reg_valid <= 1'b0;
            end
        end
    end

    assign out = reversed_out;

endmodule