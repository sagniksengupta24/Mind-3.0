module priority_encoder_formal(
    input wire [7:0] in
);
    wire [2:0] out;
    wire valid;
    priority_encoder dut (.in(in), .out(out), .valid(valid));

    always @(*) begin
        if (in == 8'b0) begin
            assert(!valid);
            assert(out == 3'b000);
        end else begin
            assert(valid);
        end
        if (in[7]) assert(out == 3'd7);
        else if (in[6]) assert(out == 3'd6);
        else if (in[5]) assert(out == 3'd5);
        else if (in[4]) assert(out == 3'd4);
        else if (in[3]) assert(out == 3'd3);
        else if (in[2]) assert(out == 3'd2);
        else if (in[1]) assert(out == 3'd1);
        else if (in[0]) assert(out == 3'd0);
    end
endmodule
