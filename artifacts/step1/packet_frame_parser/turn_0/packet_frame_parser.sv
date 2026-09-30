module packet_frame_parser (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       valid_in,
    input  wire [7:0] data_in,
    output reg        frame_valid,
    output reg  [7:0] payload_byte,
    output reg        payload_valid,
    output reg        frame_error
);

    typedef enum reg [2:0] {
        IDLE,
        SOF_WAIT,
        LEN_WAIT,
        PAYLOAD_WAIT,
        EOF_WAIT
    } state_t;

    state_t current_state, next_state;
    reg [2:0] len_counter;
    reg [2:0] len_value;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            current_state <= IDLE;
            len_counter   <= 3'b000;
            len_value     <= 3'b000;
        end else begin
            current_state <= next_state;
            len_counter   <= len_counter;
            len_value     <= len_value;
        end
    end

    always @(*) begin
        case (current_state)
            IDLE: begin
                if (valid_in && (data_in == 8'hA5))
                    next_state = SOF_WAIT;
                else
                    next_state = IDLE;
            end

            SOF_WAIT: begin
                if (valid_in) begin
                    if (data_in >= 1 && data_in <= 8)
                        next_state = LEN_WAIT;
                    else
                        next_state = IDLE;
                end else
                    next_state = SOF_WAIT;
            end

            LEN_WAIT: begin
                if (valid_in) begin
                    len_value = data_in;
                    len_counter = 3'b000;
                    next_state = PAYLOAD_WAIT;
                end else
                    next_state = LEN_WAIT;
            end

            PAYLOAD_WAIT: begin
                if (valid_in) begin
                    if (len_counter < (len_value - 1))
                        next_state = PAYLOAD_WAIT;
                    else
                        next_state = EOF_WAIT;
                end else
                    next_state = PAYLOAD_WAIT;
            end

            EOF_WAIT: begin
                if (valid_in && (data_in == 8'h5A))
                    next_state = IDLE;
                else
                    next_state = IDLE;
            end

            default: next_state = IDLE;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            frame_valid   <= 1'b0;
            payload_byte  <= 8'h00;
            payload_valid <= 1'b0;
            frame_error   <= 1'b0;
        end else begin
            frame_valid   <= 1'b0;
            payload_valid <= 1'b0;
            frame_error   <= 1'b0;

            case (current_state)
                IDLE: begin
                    if (valid_in && (data_in == 8'hA5))
                        len_counter <= 3'b000;
                end

                SOF_WAIT: begin
                    if (valid_in && (data_in >= 1 && data_in <= 8)) begin
                        len_value = data_in;
                        len_counter = 3'b000;
                    end
                end

                LEN_WAIT: begin
                    if (valid_in) begin
                        len_value = data_in;
                        len_counter = 3'b000;
                    end
                end

                PAYLOAD_WAIT: begin
                    if (valid_in) begin
                        payload_byte  <= data_in;
                        payload_valid <= 1'b1;
                        len_counter   <= len_counter + 1;
                    end
                end

                EOF_WAIT: begin
                    if (valid_in && (data_in == 8'h5A)) begin
                        frame_valid <= 1'b1;
                    end
                end
            endcase

            // Error handling
            if (valid_in) begin
                case (current_state)
                    SOF_WAIT: begin
                        if (data_in < 1 || data_in > 8)
                            frame_error <= 1'b1;
                    end
                    PAYLOAD_WAIT: begin
                        if (len_counter >= len_value)
                            frame_error <= 1'b1;
                    end
                    EOF_WAIT: begin
                        if (data_in != 8'h5A)
                            frame_error <= 1'b1;
                    end
                endcase
            end
        end
    end

endmodule