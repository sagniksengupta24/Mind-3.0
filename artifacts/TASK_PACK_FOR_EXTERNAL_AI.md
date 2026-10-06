# Held-out Counter Tasks — External Evaluation Pack

Rules for the solving AI: for each task, return ONLY one complete synthesizable
SystemVerilog module. Module name MUST equal the task id. Reproduce the interface
exactly (names, directions, widths; 1-bit ports are scalars with no range).
No testbenches, no assertions, no explanations.

## counter_01 — up_down_saturating_8b
Specification: 8-bit saturating up/down counter with load enable and overflow/underflow clamp
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input scalar (no range) up
- input scalar (no range) down
- output [7:0] count
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) count == 8'hFF && up && !down |=> count == 8'hFF);`
- `assert property (@(posedge clk) disable iff (!rst_n) count == 8'h00 && !up && down |=> count == 8'h00);`

## counter_02 — gray_counter_4b
Specification: 4-bit synchronous Gray code counter incrementing by 1 Gray step each active cycle
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input scalar (no range) en
- output [3:0] gray
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> gray == 4'b0000);`
- `assert property (@(posedge clk) disable iff (!rst_n) en |=> $onehot(gray ^ $past(gray)));`

## counter_03 — bcd_counter_2digit
Specification: 2-digit 0-99 BCD decimal counter with carry out on wrap
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input scalar (no range) en
- output [3:0] bcd_ones
- output [3:0] bcd_tens
- output scalar (no range) carry_out
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) bcd_ones <= 4'd9);`
- `assert property (@(posedge clk) disable iff (!rst_n) bcd_tens <= 4'd9);`

## counter_04 — johnson_counter_8b
Specification: 8-bit twisted-ring Johnson counter producing 16-phase sequences
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- output [7:0] q
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> q == 8'h00);`
- `assert property (@(posedge clk) disable iff (!rst_n) q[7:1] == $past(q[6:0]));`

## counter_05 — window_watchdog_counter
Specification: Window watchdog counter requiring kick pulses only within an allowed time window
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input scalar (no range) kick
- output scalar (no range) fault
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> fault == 0);`
- `assert property (@(posedge clk) disable iff (!rst_n) fault |=> fault);`

## counter_06 — ring_oscillator_divider
Specification: Programmable integer frequency divider with 50 percent duty cycle output
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input [7:0] div_val
- output scalar (no range) clk_out
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> clk_out == 0);`
- `assert property (@(posedge clk) disable iff (!rst_n) div_val == 0 |-> clk_out == 0);`

## counter_07 — adv_counter_boundary
Specification: Adversarial boundary counter: rollover exactly at MAX-1 with simultaneous clear
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input scalar (no range) clear
- input scalar (no range) en
- output [7:0] count
- output scalar (no range) max_pulse
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) clear |=> count == 8'd0);`
- `assert property (@(posedge clk) disable iff (!rst_n) count == 8'd255 |-> max_pulse == 1);`

## counter_08 — adv_counter_signed_wrap
Specification: Adversarial signed accumulator detecting overflow and saturation bounds
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input [7:0] incr
- output [7:0] accum
- output scalar (no range) overflow
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> accum == 0);`
- `assert property (@(posedge clk) disable iff (!rst_n) overflow |-> $past(accum[7]) == $past(incr[7]));`

## counter_09 — linear_feedback_shift_reg
Specification: 8-bit Galois LFSR with maximal-length pseudo-random polynomial x^8 + x^6 + x^5 + x^4 + 1
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- output [7:0] lfsr_out
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> lfsr_out == 8'h01);`
- `assert property (@(posedge clk) disable iff (!rst_n) lfsr_out != 8'h00);`

## counter_10 — dual_edge_toggle_counter
Specification: Dual-edge event counter capturing transitions on asynchronous strobe lines
Ports:
- input scalar (no range) clk
- input scalar (no range) rst_n
- input scalar (no range) strobe
- output [7:0] count
Must satisfy:
- `assert property (@(posedge clk) disable iff (!rst_n) !rst_n |-> count == 0);`
- `assert property (@(posedge clk) disable iff (!rst_n) $changed(strobe) |=> count == $past(count) + 1);`
