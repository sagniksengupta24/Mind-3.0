module fsm_heldout_03 (
  input clk,
  input rst_n,
  input [1:0] ev,
  output [2:0] state
);

  // State definitions
  localparam ST_IDLE   = 3'b001;
  localparam ST_STEP1  = 3'b010;
  localparam ST_STEP2  = 3'b100;
  
  // Current and next state registers
  reg [2:0] current_state;
  reg [2:0] next_state;

  // Combinational logic to determine next state
  always @(*) begin
    case (current_state)
      ST_IDLE: begin
        case (ev)
          2'b00: next_state = ST_IDLE;   // Stay idle
          2'b01: next_state = ST_STEP1;  // Transition to step1
          2'b10: next_state = ST_STEP2;  // Transition to step2
          2'b11: next_state = ST_IDLE;   // Stay idle (illegal)
        endcase
      end
      
      ST_STEP1: begin
        case (ev)
          2'b00: next_state = ST_IDLE;   // Return to idle
          2'b01: next_state = ST_STEP1;  // Stay in step1
          2'b10: next_state = ST_STEP2;  // Transition to step2
          2'b11: next_state = ST_STEP1;  // Stay in step1 (illegal)
        endcase
      end
      
      ST_STEP2: begin
        case (ev)
          2'b00: next_state = ST_IDLE;   // Return to idle
          2'b01: next_state = ST_STEP1;  // Transition to step1
          2'b10: next_state = ST_STEP2;  // Stay in step2
          2'b11: next_state = ST_STEP2;  // Stay in step2 (illegal)
        endcase
      end
      
      default: next_state = ST_IDLE;
    endcase
  end

  // Sequential logic for state register
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      current_state <= ST_IDLE;
    end else begin
      current_state <= next_state;
    end
  end

  // Output assignment
  assign state = current_state;

endmodule
