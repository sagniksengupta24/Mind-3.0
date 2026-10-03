module timing_violation (
    input wire clk,
    input wire [7:0] a,
    output wire [7:0] y
);
    // Structural 3-stage flop pipeline for OpenSTA read_verilog, which
    // accepts gate-level netlists (sky130 cells) rather than behavioral RTL.
    // A 0.001ns clock against real cell delays yields negative setup slack.
    wire [7:0] r0, r1, r2;
    sky130_fd_sc_hd__dfxtp_1 f_s0_b0 (.clk(clk), .d(a[0]), .q(r0[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b1 (.clk(clk), .d(a[1]), .q(r0[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b2 (.clk(clk), .d(a[2]), .q(r0[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b3 (.clk(clk), .d(a[3]), .q(r0[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b4 (.clk(clk), .d(a[4]), .q(r0[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b5 (.clk(clk), .d(a[5]), .q(r0[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b6 (.clk(clk), .d(a[6]), .q(r0[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s0_b7 (.clk(clk), .d(a[7]), .q(r0[7]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b0 (.clk(clk), .d(r0[0]), .q(r1[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b1 (.clk(clk), .d(r0[1]), .q(r1[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b2 (.clk(clk), .d(r0[2]), .q(r1[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b3 (.clk(clk), .d(r0[3]), .q(r1[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b4 (.clk(clk), .d(r0[4]), .q(r1[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b5 (.clk(clk), .d(r0[5]), .q(r1[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b6 (.clk(clk), .d(r0[6]), .q(r1[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s1_b7 (.clk(clk), .d(r0[7]), .q(r1[7]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b0 (.clk(clk), .d(r1[0]), .q(r2[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b1 (.clk(clk), .d(r1[1]), .q(r2[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b2 (.clk(clk), .d(r1[2]), .q(r2[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b3 (.clk(clk), .d(r1[3]), .q(r2[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b4 (.clk(clk), .d(r1[4]), .q(r2[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b5 (.clk(clk), .d(r1[5]), .q(r2[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b6 (.clk(clk), .d(r1[6]), .q(r2[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s2_b7 (.clk(clk), .d(r1[7]), .q(r2[7]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b0 (.clk(clk), .d(r2[0]), .q(y[0]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b1 (.clk(clk), .d(r2[1]), .q(y[1]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b2 (.clk(clk), .d(r2[2]), .q(y[2]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b3 (.clk(clk), .d(r2[3]), .q(y[3]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b4 (.clk(clk), .d(r2[4]), .q(y[4]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b5 (.clk(clk), .d(r2[5]), .q(y[5]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b6 (.clk(clk), .d(r2[6]), .q(y[6]));
    sky130_fd_sc_hd__dfxtp_1 f_s3_b7 (.clk(clk), .d(r2[7]), .q(y[7]));
endmodule
