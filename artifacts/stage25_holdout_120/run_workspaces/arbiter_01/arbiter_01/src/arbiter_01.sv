module arbiter_01 (
  input clk,
  input rst_n,
  input [3:0] req,
  output [3:0] gnt
);

  reg [3:0] grant_reg;
  reg [1:0] priority_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      grant_reg <= 4'b0000;
      priority_reg <= 2'b00;
    end else begin
      if (req != 4'b0000) begin
        case (priority_reg)
          2'b00: begin
            if (req[0]) grant_reg <= 4'b0001;
            else if (req[1]) grant_reg <= 4'b0010;
            else if (req[2]) grant_reg <= 4'b0100;
            else if (req[3]) grant_reg <= 4'b1000;
            else grant_reg <= 4'b0000;
          end
          2'b01: begin
            if (req[1]) grant_reg <= 4'b0010;
            else if (req[2]) grant_reg <= 4'b0100;
            else if (req[3]) grant_reg <= 4'b1000;
            else if (req[0]) grant_reg <= 4'b0001;
            else grant_reg <= 4'b0000;
          end
          2'b10: begin
            if (req[2]) grant_reg <= 4'b0100;
            else if (req[3]) grant_reg <= 4'b1000;
            else if (req[0]) grant_reg <= 4'b0001;
            else if (req[1]) grant_reg <= 4'b0010;
            else grant_reg <= 4'b0000;
          end
          2'b11: begin
            if (req[3]) grant_reg <= 4'b1000;
            else if (req[0]) grant_reg <= 4'b0001;
            else if (req[1]) grant_reg <= 4'b0010;
            else if (req[2]) grant_reg <= 4'b0100;
            else grant_reg <= 4'b0000;
          end
        endcase
      end else begin
        grant_reg <= 4'b0000;
      end

      // Update priority register based on grant
      if (grant_reg != 4'b0000) begin
        case (grant_reg)
          4'b0001: priority_reg <= 2'b01;
          4'b0010: priority_reg <= 2'b10;
          4'b0100: priority_reg <= 2'b11;
          4'b1000: priority_reg <= 2'b00;
          default: priority_reg <= 2'b00;
        endcase
      end
    end
  end

  assign gnt = grant_reg;

endmodule
