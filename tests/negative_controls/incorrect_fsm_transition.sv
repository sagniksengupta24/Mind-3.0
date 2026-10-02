module incorrect_fsm_transition (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic fast_trigger,
    output logic [1:0] state
);
    localparam logic [1:0] S_IDLE   = 2'd0;
    localparam logic [1:0] S_SETUP  = 2'd1;
    localparam logic [1:0] S_ACTIVE = 2'd2;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
        end else begin
            case (state)
                S_IDLE: begin
                    if (fast_trigger) begin
                        // BUG: Illegally jumps directly to ACTIVE without passing through SETUP
                        state <= S_ACTIVE;
                    end else if (start) begin
                        state <= S_SETUP;
                    end
                end
                S_SETUP: begin
                    state <= S_ACTIVE;
                end
                S_ACTIVE: begin
                    state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
