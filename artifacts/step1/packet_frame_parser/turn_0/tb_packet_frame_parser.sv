`timescale 1ns/1ps
module tb_packet_frame_parser;
    reg clk;
    reg rst_n;
    reg valid_in;
    reg [7:0] data_in;
    wire frame_valid;
    wire [7:0] payload_byte;
    wire payload_valid;
    wire frame_error;

    packet_frame_parser dut (
        .clk(clk),
        .rst_n(rst_n),
        .valid_in(valid_in),
        .data_in(data_in),
        .frame_valid(frame_valid),
        .payload_byte(payload_byte),
        .payload_valid(payload_valid),
        .frame_error(frame_error)
    );

    always #5 clk = ~clk;

    task send_byte(input [7:0] b);
        begin
            @(posedge clk);
            valid_in = 1;
            data_in = b;
            @(posedge clk);
            valid_in = 0;
            data_in = 0;
        end
    endtask

    integer received_payloads;
    reg [7:0] rx_buf [0:15];

    always @(posedge clk) begin
        if (payload_valid) begin
            rx_buf[received_payloads] <= payload_byte;
            received_payloads <= received_payloads + 1;
        end
    end

    initial begin
        clk = 0;
        rst_n = 0;
        valid_in = 0;
        data_in = 0;
        received_payloads = 0;
        #20;
        rst_n = 1;
        #10;

        send_byte(8'hA5);
        send_byte(8'h03);
        send_byte(8'h11);
        send_byte(8'h22);
        send_byte(8'h33);
        send_byte(8'h5A);
        #1;
        if (!frame_valid) begin
            $display("FAIL: Test 1: frame_valid not asserted on valid EOF");
            $fatal(1);
        end
        if (received_payloads !== 3 || rx_buf[0] !== 8'h11 || rx_buf[1] !== 8'h22 || rx_buf[2] !== 8'h33) begin
            $display("FAIL: Test 1: incorrect payload received");
            $fatal(1);
        end

        send_byte(8'hFF);
        #1;
        if (!frame_error) begin
            $display("FAIL: Test 2: frame_error not asserted on invalid SOF");
            $fatal(1);
        end

        send_byte(8'hA5);
        send_byte(8'h02);
        send_byte(8'hAA);
        send_byte(8'hBB);
        send_byte(8'hEE);
        #1;
        if (!frame_error) begin
            $display("FAIL: Test 3: frame_error not asserted on corrupt EOF");
            $fatal(1);
        end

        $display("ALL_TESTS_PASSED");
        $finish;
    end
endmodule
