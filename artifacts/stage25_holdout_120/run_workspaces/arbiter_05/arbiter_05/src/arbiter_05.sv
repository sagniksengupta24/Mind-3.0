module arbiter_05 (
  input clk,
  input rst_n,
  input [3:0] req,
  output [3:0] gnt
);

  reg [3:0] gnt_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      gnt_reg <= 4'd0;
    end else begin
      // Priority arbiter logic for upper-triangular matrix
      // Client 0 has highest priority, then 1, 2, 3
      if (req[0]) begin
        gnt_reg <= 4'b0001;
      end else if (req[1]) begin
        gnt_reg <= 4'b0010;
      end else if (req[2]) begin
        gnt_reg <= 4'b0100;
      end else if (req[3]) begin
        gnt_reg <= 4'b1000;
      end else begin
        gnt_reg <= 4'd0;
      end
    end
  end

  assign gnt = gnt_reg;

endmodule
