# Mind 3.0 Negative Controls Suite

These 16 fixtures are intentionally broken designs used to prove that Mind 3.0 verification gates reject known-bad RTL at the precise expected gate.

They are **never** benchmark tasks and must never be included in model performance metrics. A negative-control run is successful only when every applicable live gate produces the **expected failure category**. Missing tooling, skipped gates, mock output, or an unexpected PASS are explicit failures of the negative-control run.

| Control Fixture | Source RTL | Expected Compile | Expected Gate | Expected Category | Why It Must Fail |
|---|---|---|---|---|---|
| `latch_inference` | `latch_inference.sv` | FAIL | Gate 1 | `LATCH_INFERRED` | Incomplete combinational case infers a transparent latch |
| `combinational_loop` | `combinational_loop.sv` | FAIL | Gate 1 | `COMBINATIONAL_LOOP` | Cross-coupled combinational logic creates a zero-delay feedback loop |
| `incorrect_reset_behavior` | `incorrect_reset_behavior.sv` | PASS | Gate 2 | `FORMAL_INVARIANT_BREACH` | Flop retains state during reset rather than clearing to 0 |
| `reset_deassertion_problem` | `reset_deassertion_problem.sv` | PASS | Gate 2 | `FORMAL_INVARIANT_BREACH` | Asynchronous reset deassertion without synchronizer violates recovery timing |
| `cdc_violation` | `cdc_violation.sv` | PASS | Gate 6 | `CDC_VIOLATION` | Unsynchronized signal crosses between independent clock domains |
| `fifo_overflow` | `fifo_overflow.sv` | PASS | Gate 3 | `SIMULATION_FAILURE` | Unguarded write into full FIFO corrupts unread queue entries |
| `fifo_underflow` | `fifo_underflow.sv` | PASS | Gate 3 | `SIMULATION_FAILURE` | Unguarded read from empty FIFO underflows counter and returns invalid data |
| `off_by_one_counter` | `off_by_one_counter.sv` | PASS | Gate 2 / 3 | `FORMAL_INVARIANT_BREACH` | Modulo-10 counter checks value==10 instead of 9, reaching out-of-range state |
| `incorrect_handshake` | `incorrect_handshake.sv` | PASS | Gate 2 | `FORMAL_INVARIANT_BREACH` | Ready/valid transmitter mutates data payload while valid is asserted and stalled |
| `incorrect_fsm_transition` | `incorrect_fsm_transition.sv` | PASS | Gate 2 | `FORMAL_INVARIANT_BREACH` | State machine executes illegal transition directly from IDLE to ACTIVE |
| `width_truncation` | `width_truncation.sv` | FAIL | Gate 1 | `SYNTHESIS_ELABORATION_ERROR` | 16-bit operation assigned directly to 8-bit output causing bit-width mismatch |
| `signed_unsigned_error` | `signed_unsigned_error.sv` | PASS | Gate 2 | `FORMAL_INVARIANT_BREACH` | Mixing signed and unsigned operands coerces negative value to high positive value |
| `timing_violation` | `timing_violation.sv` | PASS | Gate 4 | `TIMING_SLACK_VIOLATION` | Combinational delay exceeds clock period causing negative setup slack |
| `false_formal` | `false_formal.sv` | PASS | Gate 2 | `FORMAL_INVARIANT_BREACH` | Deliberately false formal property asserted on alternating toggle register |
| `sim_behavioral_failure` | `sim_behavioral_failure.sv` | PASS | Gate 3 | `SIMULATION_FAILURE` | Elaborates clean but subtracts instead of adds, detected by simulation assert |
| `coverage_deficit` | `coverage_deficit.sv` | PASS | Gate 3 | `COVERAGE_DEFICIT` | Testbench exercises only a fraction of module branches and toggles |

The timing control is intentionally environment-dependent: set `MIND3_NEGATIVE_CONTROL_LIBERTY` before a live Gate 4 run.
