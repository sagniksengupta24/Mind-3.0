module fifo_06 (
  input clk,
  input rst_n,
  input valid_in,
  output ready_out,
  output valid_out,
  input ready_in
);

  // FIFO control signals
  reg full;
  reg empty;
  
  // FIFO data storage
  reg valid_out_reg;
  reg ready_out_reg;
  
  // State transition logic
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      full <= 1'b0;
      empty <= 1'b1;
      valid_out_reg <= 1'b0;
      ready_out_reg <= 1'b1;
    end else begin
      // Update FIFO status
      if (valid_in && !full) begin
        full <= (full || valid_in) && !(ready_in && valid_out_reg);
        empty <= empty && !(valid_in && !ready_in);
      end else if (ready_in && valid_out_reg) begin
        full <= full && !(valid_in && !ready_in);
        empty <= (empty || !valid_out_reg) && !(valid_in && ready_in);
      end
      
      // Update valid and ready signals
      valid_out_reg <= (valid_out_reg && !ready_in) || (valid_in && !full);
      ready_out_reg <= ~empty;
    end
  end
  
  // Assign outputs
  assign valid_out = valid_out_reg;
  assign ready_out = ready_out_reg;

endmodule
