// Synchronous (single-clock) FIFO: no cross-domain sampling exists.
// A dual-clock variant is UNPROVEN_FIFO/INCONCLUSIVE until a Gray-pointer
// proof is implemented. Expected: CDC PASS (zero crossings).
module safe_async_fifo (
  input  logic clk,
  input  logic rst_n,
  input  logic wr_en,
  input  logic [7:0] wr_data,
  input  logic rd_en,
  output logic [7:0] rd_data,
  output logic full,
  output logic empty
);
  logic [7:0] mem [0:7];
  logic [3:0] wr_ptr;
  logic [3:0] rd_ptr;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_ptr <= 4'd0;
      rd_ptr <= 4'd0;
      rd_data <= 8'h00;
    end else begin
      if (wr_en) begin
        mem[wr_ptr[2:0]] <= wr_data;
        wr_ptr <= wr_ptr + 4'd1;
      end
      if (rd_en) begin
        rd_data <= mem[rd_ptr[2:0]];
        rd_ptr <= rd_ptr + 4'd1;
      end
    end
  end

  assign full = (wr_ptr == rd_ptr + 4'd8);
  assign empty = (wr_ptr == rd_ptr);
endmodule
