// UNREVIEWED golden reference RTL for dev task fifo_01 (sync_fifo_8x8).
// MUTANT fifo_01/emptyhigh (UNREVIEWED test input): violates specified property via: !(full && empty). Must FAIL at some gate.
// Written from the task spec only (8-depth 8-bit synchronous FIFO with full,
// empty; active-low synchronous rst_n). Owner spot-check required.
module fifo_01 (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       wr_en,
  input  logic [7:0] wr_data,
  input  logic       rd_en,
  output logic [7:0] rd_data,
  output logic       full,
  output logic       empty
);
  logic [7:0] mem [0:7];
  logic [2:0] wr_ptr, rd_ptr;
  logic [3:0] count;

  assign full  = (count == 4'd8);
  assign empty = 1'b1;
  assign rd_data = mem[rd_ptr];

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_ptr <= 3'd0;
      rd_ptr <= 3'd0;
      count  <= 4'd0;
    end else begin
      case ({wr_en & ~full, rd_en & ~empty})
        2'b10: begin mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 3'd1; count <= count + 4'd1; end
        2'b01: begin rd_ptr <= rd_ptr + 3'd1; count <= count - 4'd1; end
        2'b11: begin mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 3'd1; rd_ptr <= rd_ptr + 3'd1; end
        default: begin end
      endcase
    end
  end
endmodule
