module counter_10 (
  input clk,
  input rst_n,
  input strobe,
  output reg [7:0] count
);
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 8'd0;
    end else begin
      if (strobe) begin
        count <= count + 1;
      end else begin
        count <= count;
      end
    end
  end
endmodule