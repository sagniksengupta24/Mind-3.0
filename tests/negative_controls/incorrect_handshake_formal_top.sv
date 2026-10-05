module incorrect_handshake_formal_top (
    input logic clk,
    input logic rst_n,
    input logic [7:0] next_data,
    input logic ready
);
    wire valid;
    wire [7:0] data;

    incorrect_handshake dut (
        .clk(clk),
        .rst_n(rst_n),
        .next_data(next_data),
        .ready(ready),
        .valid(valid),
        .data(data)
    );

    always @(posedge clk) begin
        if (rst_n && $past(rst_n)) begin
            // Handshake forward progress rule: if valid was high and ready was low, data must stay unchanged!
            if ($past(valid) && !$past(ready)) begin
                assert (valid == 1'b1);
                assert (data == $past(data));
            end
        end
    end
endmodule
