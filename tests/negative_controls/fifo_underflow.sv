module fifo_underflow (
    input  logic clk,
    input  logic rst_n,
    input  logic wr_en,
    input  logic [7:0] wr_data,
    input  logic rd_en,
    output logic [7:0] rd_data,
    output logic full,
    output logic empty,
    output logic [2:0] count
);
    logic [7:0] mem [0:3];
    logic [1:0] wr_ptr;
    logic [1:0] rd_ptr;

    assign full  = (count == 3'd4);
    assign empty = (count == 3'd0);
    assign rd_data = mem[rd_ptr];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= 2'd0;
            rd_ptr <= 2'd0;
            count  <= 3'd0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
                count <= count + 1'b1;
            end
            // BUG: read when empty is not guarded, decrementing count below 0 to 3'b111!
            if (rd_en) begin
                rd_ptr <= rd_ptr + 1'b1;
                count <= count - 1'b1; // underflows!
            end
        end
    end
endmodule
