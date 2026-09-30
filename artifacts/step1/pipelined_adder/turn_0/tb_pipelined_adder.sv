`timescale 1ns/1ps
module tb_pipelined_adder;
    reg clk;
    reg rst_n;
    reg valid_in;
    reg [31:0] a;
    reg [31:0] b;
    wire [31:0] sum;
    wire carry_out;
    wire valid_out;

    pipelined_adder dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .a(a),
        .b(b),
        .sum(sum),
        .carry_out(carry_out),
        .valid_out(valid_out)
    );

    always #5 clk = ~clk;

    reg [31:0] exp_a [0:99];
    reg [31:0] exp_b [0:99];
    reg [32:0] exp_res [0:99];
    integer i;

    initial begin
        clk = 0;
        rst_n = 0;
        valid_in = 0;
        a = 0;
        b = 0;
        #20;
        rst_n = 1;
        #10;

        for (i = 0; i < 50; i = i + 1) begin
            @(posedge clk);
            valid_in = 1;
            if (i == 0) begin
                a = 32'h0000_FFFF; b = 32'h0000_0001;
            end else if (i == 1) begin
                a = 32'hFFFF_FFFF; b = 32'h0000_0001;
            end else begin
                a = $random; b = $random;
            end
            exp_a[i] = a;
            exp_b[i] = b;
            exp_res[i] = {1'b0, a} + {1'b0, b};
        end

        @(posedge clk);
        valid_in = 0;

        for (i = 0; i < 50; i = i + 1) begin
            @(posedge clk);
            #1;
            if (i >= 1) begin
                integer chk;
                chk = i - 1;
                if (valid_out !== 1'b1) begin
                    $display("FAIL: valid_out not asserted for item %0d", chk);
                    $fatal(1);
                end
                if ({carry_out, sum} !== exp_res[chk]) begin
                    $display("FAIL: %0h + %0h: got {c,s}=%0h, expected %0h",
                             exp_a[chk], exp_b[chk], {carry_out, sum}, exp_res[chk]);
                    $fatal(1);
                end
            end
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
