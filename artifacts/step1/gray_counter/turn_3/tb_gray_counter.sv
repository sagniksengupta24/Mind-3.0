`timescale 1ns/1ps
module tb_gray_counter;
    reg clk;
    reg rst_n;
    reg enable;
    wire [3:0] gray_out;

    gray_counter dut (
        .clk(clk),
        .rst_n(rst_n),
        .enable(enable),
        .gray_out(gray_out)
    );

    always #5 clk = ~clk;

    reg [3:0] seq [0:15];
    integer i, step;

    initial begin
        seq[0]=4'b0000; seq[1]=4'b0001; seq[2]=4'b0011; seq[3]=4'b0010;
        seq[4]=4'b0110; seq[5]=4'b0111; seq[6]=4'b0101; seq[7]=4'b0100;
        seq[8]=4'b1100; seq[9]=4'b1101; seq[10]=4'b1111; seq[11]=4'b1110;
        seq[12]=4'b1010; seq[13]=4'b1011; seq[14]=4'b1001; seq[15]=4'b1000;

        clk = 0;
        rst_n = 0;
        enable = 0;
        #20;
        rst_n = 1;
        #10;
        if (gray_out !== 4'b0000) begin
            $display("FAIL: Reset did not clear gray_out, got %b", gray_out);
            $fatal(1);
        end

        // Check hold when enable=0
        #20;
        if (gray_out !== 4'b0000) begin
            $display("FAIL: Counter changed while enable=0, got %b", gray_out);
            $fatal(1);
        end

        // Count through 32 cycles (2 full sequences)
        enable = 1;
        for (step = 0; step < 32; step = step + 1) begin
            @(posedge clk);
            #1;
            if (gray_out !== seq[(step + 1) % 16]) begin
                $display("FAIL: At step %0d, expected %b, got %b",
                         step, seq[(step + 1) % 16], gray_out);
                $fatal(1);
            end
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
