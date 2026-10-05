`ifndef VERILATOR
module testbench;
  reg [4095:0] vcdfile;
  reg clock;
`else
module testbench(input clock, output reg genclock);
  initial genclock = 1;
`endif
  reg genclock = 1;
  reg [31:0] cycle = 0;
  counter_05_formal_top UUT (

  );
`ifndef VERILATOR
  initial begin
    if ($value$plusargs("vcd=%s", vcdfile)) begin
      $dumpfile(vcdfile);
      $dumpvars(0, testbench);
    end
    #5 clock = 0;
    while (genclock) begin
      #5 clock = 0;
      #5 clock = 1;
    end
  end
`endif
  initial begin
`ifndef VERILATOR
    #1;
`endif
    UUT.dut._witness_.anyinit_procdff_45 = 1'b1;
    // UUT.sva.$formal$counter_05_sva.\sv:19$2_CHECK  = 1'b0;
    // UUT.sva.$formal$counter_05_sva.\sv:19$2_EN  = 1'b0;
    // UUT.sva.$formal$counter_05_sva.\sv:26$3_CHECK  = 1'b0;
    // UUT.sva.$formal$counter_05_sva.\sv:26$3_EN  = 1'b0;
    // UUT.sva.$past$counter_05_sva.\sv:26$1$0  = 1'b1;
    UUT.sva.init = 1'b1;

    // state 0
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
    end

    // state 2
    if (cycle == 1) begin
    end

    genclock <= cycle < 2;
    cycle <= cycle + 1;
  end
endmodule
