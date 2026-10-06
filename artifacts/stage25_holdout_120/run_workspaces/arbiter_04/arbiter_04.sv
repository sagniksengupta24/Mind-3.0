module arbiter_04 (
  input clk,
  input rst_n,
  input [2:0] req,
  output [2:0] gnt
);

  reg [2:0] gnt_reg;
  reg [1:0] count;
  reg [2:0] weight;
  reg [2:0] grant_mask;
  reg [2:0] req_delayed;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      gnt_reg <= 3'b000;
      count <= 2'd0;
      weight <= 3'b011; // 3:2:1 ratio
      grant_mask <= 3'b111;
      req_delayed <= 3'b000;
    end else begin
      req_delayed <= req;
      
      if (count == 0) begin
        grant_mask <= req_delayed;
      end
      
      if (grant_mask != 0) begin
        if (req_delayed[2] && weight[2]) begin
          gnt_reg <= 3'b100;
          count <= 2'd2; // Next cycle will be 1, then 0
          weight <= 3'b011;
        end else if (req_delayed[1] && weight[1]) begin
          gnt_reg <= 3'b010;
          count <= 2'd1;
          weight <= 3'b011;
        end else if (req_delayed[0] && weight[0]) begin
          gnt_reg <= 3'b001;
          count <= 2'd0;
          weight <= 3'b011;
        end else begin
          gnt_reg <= 3'b000;
          count <= 2'd0;
          weight <= 3'b011;
        end
      end else begin
        gnt_reg <= 3'b000;
        count <= 2'd0;
        weight <= 3'b011;
      end
      
      if (count > 0) begin
        count <= count - 1;
      end
      
      // Update weights for next cycle based on current grant
      if (gnt_reg[2]) begin
        weight <= 3'b010; // Next grant should be 2:1:1 ratio
      end else if (gnt_reg[1]) begin
        weight <= 3'b001; // Next grant should be 1:1:1 ratio
      end else if (gnt_reg[0]) begin
        weight <= 3'b110; // Next grant should be 3:2:1 ratio
      end
    end
  end

  assign gnt = gnt_reg;

endmodule
