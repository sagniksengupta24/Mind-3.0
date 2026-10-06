module arbiter_08 (
  input clk,
  input rst_n,
  input [3:0] cluster_req,
  output [3:0] gnt
);

  reg [3:0] gnt_reg;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      gnt_reg <= 4'b0000;
    end else begin
      // Cluster 0 (bits 1:0) has clients 0 and 1
      // Cluster 1 (bits 3:2) has clients 2 and 3
      if (cluster_req[3]) begin
        gnt_reg <= 4'b0001; // Grant to client 3
      end else if (cluster_req[2]) begin
        gnt_reg <= 4'b0010; // Grant to client 2
      end else if (cluster_req[1]) begin
        gnt_reg <= 4'b0100; // Grant to client 1
      end else if (cluster_req[0]) begin
        gnt_reg <= 4'b1000; // Grant to client 0
      end else begin
        gnt_reg <= 4'b0000; // No grant
      end
    end
  end

  assign gnt = gnt_reg;

endmodule
