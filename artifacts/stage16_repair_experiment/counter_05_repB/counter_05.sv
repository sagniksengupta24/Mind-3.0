module counter_05 (
  input clk,
  input rst_n,
  input kick,
  output fault
);

  reg fault_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fault_reg <= 1'b0;
    end else begin
      if (kick) begin
        fault_reg <= 1'b0;
      end else begin
        fault_reg <= 1'b0; // Change from 1'b1 to 1'b0
      end
    end
  end

  assign fault = fault_reg;

endmodule
