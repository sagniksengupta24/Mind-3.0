# Gate 1 Failure and Synthesis Classification Report

## Overview
Gate 1 executes Yosys AST elaboration and latch trap detection.
Every source file in the synthesis workspace is traced and filtered to ensure formal harnesses (`*_sva.sv`, `*_formal_top.sv`, `*_checker.sv`, `*_tb.sv`, `*_tb.v`) are strictly excluded, while legitimate SystemVerilog files (`.sv`) are retained.

## Classification Taxonomy
- **MODEL_GENERATION_FAILURE**: Model output was malformed, truncated, or could not be reconstructed into valid SystemVerilog (e.g., missing endmodule, empty JSON body).
- **GATE1_INFRASTRUCTURE_FAILURE**: Pipeline harness or toolchain defect (e.g., SVA file accidentally included in synthesis source list, missing top module renaming, Yosys command syntax error).
- **GATE1_GENUINE_RTL_FAILURE**: Model synthesized valid Verilog that contains genuine hardware bugs (e.g. unintended storage latches inferred from incomplete `if` branches in combinational always blocks, combinational loops).

## Historic & Baseline Failures Analyzed

### 1. Inferred Latches in Combinational Blocks
- **Task Category**: Combinational multiplexers / decoders without explicit `else` or default assignment.
- **Example**: `latch_unit.v` where `if (sel) y = a;` lacks an `else` branch.
- **Classification**: **GATE1_GENUINE_RTL_FAILURE**
- **Action**: Correctly caught by Yosys AST inspection and flagged as `LATCH_INFERRED`. The pipeline halts signoff and prompts targeted RTL repair.

### 2. SVA File Inclusion in Yosys Elaboration
- **Symptom**: `syntax error, unexpected TOK_PROPERTY` or `module ..._sva already declared`.
- **Root Cause**: `*.sv` glob previously captured `top_sva.sv` during Yosys synthesis.
- **Classification**: **GATE1_INFRASTRUCTURE_FAILURE**
- **Fix**: Updated `verifier.py` source filter to explicitly exclude `*_sva.sv`, `*_formal_top.sv`, `*_checker.sv`, `*_tb.sv`, `*_tb.v` by role and naming pattern, while preserving user `.sv` implementation files.
- **Verification**: Verified by `tests/test_p3_gate1.py` (passes).

### 3. Model Response JSON AST / Escape Sequence Parse Failures
- **Symptom**: `Failed to extract valid synthesizable SystemVerilog module from model response`.
- **Root Cause**: Model emitted AST-style dictionary or escaped newlines (`\n`) that the legacy parser failed to unpack.
- **Classification**: **GATE1_INFRASTRUCTURE_FAILURE**
- **Fix**: Implemented robust AST JSON reconstruction (`_reconstruct_from_ast`) and structural unescaping in `driver.py:_parse_model_code_response`.
- **Verification**: Verified by `tests/test_p2_parser.py` (passes).

### 4. Non-Synthesizable Constructs
- **Symptom**: Verilog code containing initial blocks or delay elements `#10` in synthesizable logic.
- **Classification**: **MODEL_GENERATION_FAILURE**
- **Action**: Yosys synthesis fails with `SYNTHESIS_ELABORATION_ERROR`, accurately failing closed.
