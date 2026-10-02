`timescale 1ns/1ps
module tb_signed_multiplier;
    reg signed [7:0] a;
    reg signed [7:0] b;
    wire signed [15:0] p;

    signed_multiplier dut (.a(a), .b(b), .p(p));

    integer i, j;
    reg signed [15:0] exp_p;

    initial begin
        // Corner cases
        reg signed [7:0] test_vals [0:7];
        test_vals[0] = -128; test_vals[1] = -127; test_vals[2] = -1;
        test_vals[3] = 0;    test_vals[4] = 1;    test_vals[5] = 2;
        test_vals[6] = 126;  test_vals[7] = 127;

        for (i = 0; i < 8; i = i + 1) begin
            for (j = 0; j < 8; j = j + 1) begin
                a = test_vals[i];
                b = test_vals[j];
                #5;
                exp_p = a * b;
                if (p !== exp_p) begin
                    $display("FAIL: %0d * %0d: got %0d, expected %0d", a, b, p, exp_p);
                    $fatal(1);
                end
            end
        end

        // Random tests
        for (i = 0; i < 500; i = i + 1) begin
            a = $random;
            b = $random;
            #5;
            exp_p = a * b;
            if (p !== exp_p) begin
                $display("FAIL: Random test %0d: %0d * %0d got %0d, exp %0d", i, a, b, p, exp_p);
                $fatal(1);
            end
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
