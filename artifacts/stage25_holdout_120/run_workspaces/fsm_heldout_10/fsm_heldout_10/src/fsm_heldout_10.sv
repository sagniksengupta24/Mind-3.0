module fsm_heldout_10 (
  input clk,
  input rst_n,
  output [1:0] state_out
);

  reg [1:0] state_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state_reg <= 2'd0;
    end else begin
      case (state_reg)
        2'd0: state_reg <= 2'd1;
        2'd1: state_reg <= 2'd2;
        2'd2: state_reg <= 2'd0;  // Fixed: transition to reset state instead of undefined state
        2'd3: state_reg <= 2'd0;
        default: state_reg <= 2'd0; // Self-healing: undefined states recover to reset
      endcase
    end
  end

  assign state_out = state_reg;

endmodule
