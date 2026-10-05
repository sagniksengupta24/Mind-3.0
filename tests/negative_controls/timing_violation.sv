module timing_violation (
    input wire clk,
    input wire [7:0] a,
    output wire [7:0] y
);
    // Structural 3-stage flop pipeline for OpenSTA read_verilog, which
    // accepts gate-level netlists (sky130 cells) rather than behavioral RTL.
    // A 0.001ns clock against real cell delays yields negative setup slack.
    wire [7:0] r0, r1, r2;
    sky130_fd_sc_hd__dfxtp_1 f_s0_b0 (.CLK(clk), .D(a[0]), .Q(r0[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b1 (.CLK(clk), .D(a[1]), .Q(r0[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b2 (.CLK(clk), .D(a[2]), .Q(r0[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b3 (.CLK(clk), .D(a[3]), .Q(r0[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b4 (.CLK(clk), .D(a[4]), .Q(r0[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b5 (.CLK(clk), .D(a[5]), .Q(r0[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b6 (.CLK(clk), .D(a[6]), .Q(r0[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b7 (.CLK(clk), .D(a[7]), .Q(r0[7]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b0 (.CLK(clk), .D(r0[0]), .Q(r1[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b1 (.CLK(clk), .D(r0[1]), .Q(r1[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b2 (.CLK(clk), .D(r0[2]), .Q(r1[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b3 (.CLK(clk), .D(r0[3]), .Q(r1[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b4 (.CLK(clk), .D(r0[4]), .Q(r1[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b5 (.CLK(clk), .D(r0[5]), .Q(r1[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b6 (.CLK(clk), .D(r0[6]), .Q(r1[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b7 (.CLK(clk), .D(r0[7]), .Q(r1[7]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b0 (.CLK(clk), .D(r1[0]), .Q(r2[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b1 (.CLK(clk), .D(r1[1]), .Q(r2[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b2 (.CLK(clk), .D(r1[2]), .Q(r2[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b3 (.CLK(clk), .D(r1[3]), .Q(r2[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b4 (.CLK(clk), .D(r1[4]), .Q(r2[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b5 (.CLK(clk), .D(r1[5]), .Q(r2[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b6 (.CLK(clk), .D(r1[6]), .Q(r2[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b7 (.CLK(clk), .D(r1[7]), .Q(r2[7]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b0 (.CLK(clk), .D(r2[0]), .Q(y[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b1 (.CLK(clk), .D(r2[1]), .Q(y[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b2 (.CLK(clk), .D(r2[2]), .Q(y[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b3 (.CLK(clk), .D(r2[3]), .Q(y[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b4 (.CLK(clk), .D(r2[4]), .Q(y[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b5 (.CLK(clk), .D(r2[5]), .Q(y[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b6 (.CLK(clk), .D(r2[6]), .Q(y[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b7 (.CLK(clk), .D(r2[7]), .Q(y[7]));
endmodule
