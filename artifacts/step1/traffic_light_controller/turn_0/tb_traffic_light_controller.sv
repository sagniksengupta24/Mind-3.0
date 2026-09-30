`timescale 1ns/1ps
module tb_traffic_light_controller;
    reg clk;
    reg rst_n;
    reg car_side;
    wire [1:0] light_main;
    wire [1:0] light_side;

    traffic_light_controller dut (
        .clk(clk),
        .rst_n(rst_n),
        .car_side(car_side),
        .light_main(light_main),
        .light_side(light_side)
    );

    always #5 clk = ~clk;

    initial begin
        #10000;
        $display("FAIL: Simulation watchdog timeout (DUT hung in FSM state)");
        $fatal(1);
    end

    integer cycle;

    always @(posedge clk) begin
        if (rst_n) begin
            if (light_main != 2'b00 && light_side != 2'b00) begin
                $display("FAIL: Mutual exclusion breached: main=%b, side=%b at cycle %0d",
                         light_main, light_side, cycle);
                $fatal(1);
            end
        end
    end

    initial begin
        clk = 0;
        rst_n = 0;
        car_side = 0;
        cycle = 0;
        #20;
        rst_n = 1;

        for (cycle = 0; cycle < 10; cycle = cycle + 1) begin
            @(posedge clk);
            #1;
            if (light_main !== 2'b10 || light_side !== 2'b00) begin
                $display("FAIL: Expected Main GREEN, Side RED with no car, got main=%b, side=%b",
                         light_main, light_side);
                $fatal(1);
            end
        end

        car_side = 1;
        while (light_main == 2'b10) @(posedge clk);
        #1;
        if (light_main !== 2'b01 || light_side !== 2'b00) begin
            $display("FAIL: Expected Main YELLOW, Side RED, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        while (light_main == 2'b01) @(posedge clk);
        #1;
        if (light_main !== 2'b00 || light_side !== 2'b10) begin
            $display("FAIL: Expected Main RED, Side GREEN, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        while (light_side == 2'b10) @(posedge clk);
        #1;
        if (light_main !== 2'b00 || light_side !== 2'b01) begin
            $display("FAIL: Expected Main RED, Side YELLOW, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        while (light_side == 2'b01) @(posedge clk);
        #1;
        if (light_main !== 2'b10 || light_side !== 2'b00) begin
            $display("FAIL: Expected return to Main GREEN, got main=%b, side=%b", light_main, light_side);
            $fatal(1);
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
