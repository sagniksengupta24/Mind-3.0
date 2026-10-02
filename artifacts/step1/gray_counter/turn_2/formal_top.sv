module gray_counter_formal(
    input wire clk,
    input wire rst_n,
    input wire enable
);
    wire [3:0] gray_out;
    gray_counter dut (.clk(clk), .rst_n(rst_n), .enable(enable), .gray_out(gray_out));

    always @(posedge clk) begin
        if (!rst_n) begin
            assert(gray_out == 4'b0000);
        end else if ($past(!rst_n)) begin
            assert(gray_out == 4'b0000);
        end else if ($past(enable)) begin
            assert($onehot(gray_out ^ $past(gray_out)));
        end else begin
            assert(gray_out == $past(gray_out));
        end
    end
endmodule
