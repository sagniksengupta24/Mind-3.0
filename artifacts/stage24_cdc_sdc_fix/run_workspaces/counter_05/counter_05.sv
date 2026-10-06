module counter_05 (
  input clk,
  input rst_n,
  input kick,
  output fault
);

  reg [2:0] counter;
  reg       fault_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      counter   <= 3'd0;
      fault_reg <= 1'b0;
    end else begin
      if (kick) begin
        counter <= 3'd0;
      end else begin
        counter <= counter + 3'd1;
      end
      
      if (counter == 3'd5) begin // Assuming window is 5 clock cycles
        fault_reg <= 1'b1;
      end
    end
  end

  assign fault = fault_reg;

endmodule
