module incorrect_fsm_transition_formal_top (
    input logic clk,
    input logic rst_n,
    input logic start,
    input logic fast_trigger
);
    wire [1:0] state;
    incorrect_fsm_transition dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .fast_trigger(fast_trigger),
        .state(state)
    );

    always @(posedge clk) begin
        if (rst_n && $past(rst_n)) begin
            // Protocol requirement: from IDLE, state must NEVER transition directly to ACTIVE in 1 cycle
            if ($past(state) == 2'd0) begin
                assert (state != 2'd2);
            end
        end
    end
endmodule
