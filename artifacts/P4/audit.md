# Phase 4 Formal Verification (Gate 2) Audit

## Strategy & Toolchain Alignment
Gate 2 executes SymbiYosys (SBY) Bounded Model Checking (BMC) with Yosys.
To avoid syntax errors with SystemVerilog property and bind constructs that open-source toolchains reject (`syntax error, unexpected TOK_PROPERTY`), all SVA properties are compiled into a dedicated checker module (`*_sva.sv`) and instantiated alongside the DUT in a formal verification wrapper (`*_formal_top.sv`).

## Mandatory Invariant Verification (7/7 Passed)
- **Test 1 (Combinational Clean PASS)**: 4-bit adder with immediate assertion `sum == (a + b)`. Verified cleanly at BMC depth 25.
- **Test 2 (Combinational Buggy FAIL)**: Buggy adder with XOR operation. Caught by SBY BMC; counterexample generated and parsed.
- **Test 3 (Sequential Clean PASS)**: D-register with active-low reset. Proves `!rst_n |-> (q == 8'h00)`. Verified clean.
- **Test 4 (Sequential Buggy FAIL)**: D-register resetting to 0xFF instead of 0x00. Caught by SBY at cycle step T=1 with counterexample trace.
- **Test 5 (Sequential Without Reset)**: Free-running counter. Generated checker and wrapper contain zero reset signals or references.
- **Test 6 (Combinational Without Clock)**: Pure combinational multiplexer. Generated checker and wrapper contain zero clock or edge references.
- **Test 7 (Unsupported Temporal Construct)**: Complex multi-cycle sequence `req ##3 gnt` fails closed emitting `UNSUPPORTED_FORMAL_PROPERTY`.

## Evidence of Non-Weakening & Zero Tautology
- `properties_weakened: no`: No property was rewritten into a weakened form.
- `tautological_fallback_remaining: no`: All `expr = "1'b1"` fallbacks have been removed. Any construct outside supported BMC semantics fails closed.
- Empty property set: Rejection verified; empty property sets emit `EMPTY_FORMAL_PROPERTY_SET`.
