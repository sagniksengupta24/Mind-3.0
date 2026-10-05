module false_formal_formal_top;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic q;

    false_formal dut(.clk(clk), .rst_n(rst_n), .q(q));

    always #1 clk = ~clk;
    initial begin
        #2 rst_n = 1'b1;
        #2 assert (q == 1'b0);
        #2 $finish;
    end
endmodule
