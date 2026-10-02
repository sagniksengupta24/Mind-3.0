# Targeted Tasks Verification Breakdown (Phase 6)

| Task ID | Parser | Gate 1 (Yosys Synth) | Gate 2 (SBY BMC) | Gate 3 (Verilator Coverage) | Mind 3.0 Signoff | Failure Class | Benchmark Verdict |
|---|---|---|---|---|---|---|---|
| comparator_3bit | PASS | PASS | FAIL (UNSUPPORTED_FORMAL_PROPERTY) | SKIPPED | FAIL | MODEL_GENERATION_FAILURE | COMPILER_ERROR |
| multi_pipe_8bit | FAIL (Syntax) | SKIPPED | FAIL (UNSUPPORTED_FORMAL_PROPERTY) | SKIPPED | FAIL | MODEL_GENERATION_FAILURE | COMPILER_ERROR |
| JC_counter | FAIL (Parse) | SKIPPED | SKIPPED | SKIPPED | FAIL | MODEL_GENERATION_FAILURE | COMPILER_ERROR |
| right_shifter | FAIL (Parse) | SKIPPED | SKIPPED | SKIPPED | FAIL | MODEL_GENERATION_FAILURE | COMPILER_ERROR |
| pe | PASS | PASS | FAIL (UNSUPPORTED_FORMAL_PROPERTY) | SKIPPED | FAIL | GATE2_GENUINE_FORMAL_FAILURE | PASS |
| square_wave | FAIL (Parse) | SKIPPED | SKIPPED | SKIPPED | FAIL | MODEL_GENERATION_FAILURE | COMPILER_ERROR |
| Prob001_zero | PASS | PASS | FAIL (UNSUPPORTED_FORMAL_PROPERTY) | SKIPPED | FAIL | MODEL_GENERATION_FAILURE | PASS |

## Audit Notes
- **comparator_3bit**: SVA contains constructs unsupported by procedural BMC; failed closed emitting `UNSUPPORTED_FORMAL_PROPERTY`.
- **multi_pipe_8bit**: Contract specification contained LTL liveness temporal construct (`always ... |-> eventually ...`) unsupported by procedural bounded model checking; failed closed.
- **JC_counter, right_shifter, square_wave**: Model output failed syntax/structural extraction; failed closed emitting `RESPONSE_PARSE_FAILURE`.
- **pe**: Synthesis succeeded clean (Gate 1 PASS). SBY formal verification failed due to syntax error in generated assertion; signoff refused (FAIL).
- **Prob001_zero**: Synthesis succeeded clean (Gate 1 PASS). Contract synthesized by LLM attempted to specify clocked assertions on a clockless combinational module; failed closed emitting `UNSUPPORTED_FORMAL_PROPERTY`. Benchmark ground truth passed.
- **Integrity**: Real tool execution confirmed. Zero false PASSes observed.
