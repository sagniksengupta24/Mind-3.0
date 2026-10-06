module fsm_heldout_04 (
  input clk,
  input rst_n,
  input din,
  output dout,
  output stuffed
);

  reg [2:0] count;
  reg state;
  
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 3'd0;
      state <= 1'b0;
    end else begin
      if (din == 1'b1) begin
        if (count < 3'd5) begin
          count <= count + 1'b1;
        end else begin
          count <= 3'd0;
          state <= 1'b1;
        end
      end else begin
        count <= 3'd0;
        state <= 1'b0;
      end
    end
  end
  
  assign dout = (state == 1'b1) ? 1'b0 : din;
  assign stuffed = state;

endmodule
