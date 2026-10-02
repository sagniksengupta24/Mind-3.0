`timescale 1ns/1ps
module tb_priority_encoder;
    reg [7:0] in;
    wire [2:0] out;
    wire valid;
    priority_encoder dut (.in(in), .out(out), .valid(valid));

    integer i;
    reg exp_valid;
    reg [2:0] exp_out;

    initial begin
        for (i = 0; i < 256; i = i + 1) begin
            in = i[7:0];
            #5;
            exp_valid = (in != 0);
            exp_out = 3'd0;
            if (in[7]) exp_out = 3'd7;
            else if (in[6]) exp_out = 3'd6;
            else if (in[5]) exp_out = 3'd5;
            else if (in[4]) exp_out = 3'd4;
            else if (in[3]) exp_out = 3'd3;
            else if (in[2]) exp_out = 3'd2;
            else if (in[1]) exp_out = 3'd1;
            else if (in[0]) exp_out = 3'd0;

            if (valid !== exp_valid || out !== exp_out) begin
                $display("FAIL: in=%b got valid=%b out=%b expected valid=%b out=%b",
                         in, valid, out, exp_valid, exp_out);
                $fatal(1);
            end
        end
        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
