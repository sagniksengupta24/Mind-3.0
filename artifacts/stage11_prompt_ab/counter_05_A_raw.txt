module counter_05 (
  input clk,
  input rst_n,
  input kick,
  output fault
);

  // Registers
  logic [3:0] counter;
  logic kick_received;
  logic fault_reg;

  // Combinational logic to detect kick pulses within the window
  assign fault_reg = (counter == 4'd15) ? 1'b1 : 1'b0;

  // Sequential logic for the counter and kick detection
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      counter <= 4'd0;
      kick_received <= 1'b0;
      fault <= 1'b0;
    end else begin
      if (kick && !kick_received) begin
        counter <= counter + 1;
        kick_received <= 1'b1;
      end
      if (counter == 4'd15) begin
        kick_received <= 1'b0;
      end
      fault <= fault_reg;
    end
  end

endmodule