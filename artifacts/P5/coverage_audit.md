# Phase 5 Gate 3 Verilator Coverage Audit

## 1. Root Cause Analysis of Baseline COVERAGE_BUILD_FAILURE
- **Observed Defect**: Gate 3 consistently produced `0/10` pass rate with `COVERAGE_BUILD_FAILURE`.
- **Investigated Causes**:
  - EOF newline hypothesis: Disproved. Adding newlines did not resolve the build failure.
  - Warnings-as-errors hypothesis: Disproved.
  - Linker symbol collision: **CONFIRMED ROOT CAUSE**. Verilator invoked with `--binary` generates an internal `main()` function in C++, colliding with the user-supplied C++ testbench (`multiple definition of 'main'`).
- **Fix**: Switched from `--binary` to canonical compilation flags:
  `verilator --cc --exe --build -Wall --coverage-line --coverage-toggle -top-module {top_module} {sources} {cpp_tb} -o {bin_target}`
  This correctly links the user-supplied C++ testbench containing the Galois LFSR stimulus.

## 2. Testbench Architecture & Coverage Instrumentation
- Added `#include <verilated_cov.h>` and `VerilatedCov::write("coverage.dat");` at simulation conclusion.
- Combinational module support: testbench generator automatically detects clockless modules and drives boundary sweeps and randomized inputs without clock/reset toggling.
- Sequential module support: multi-phase testbench executing reset, boundary conditions (all zeros/all ones, walking-1), and 400-cycle Galois LFSR pseudo-random stimulus.

## 3. Real Coverage Extraction & Evaluation
- Gate 3 parses `coverage.dat` using `parse_coverage_dat_file()` to extract exact line and toggle hits.
- Evaluates metrics against existing repository thresholds:
  - Minimum branch/line coverage: **95.0%**
  - Minimum toggle coverage: **90.0%**
- Fail-closed invariant: If coverage instrumentation fails or no metrics are recorded, coverage defaults to `0.0%` (not `100.0%`), failing closed with `COVERAGE_DEFICIT`.

## 4. Test Verification Results (3/3 Passed)
- `test_p5_valid_fixture_pass`: Simple counter compiles, simulates, collects coverage, and satisfies thresholds.
- `test_p5_broken_fixture_fail`: Broken syntax correctly triggers `COVERAGE_BUILD_FAILURE`.
- `test_p5_below_threshold_fail`: Partial-toggle design generates toggle=36.4%, accurately failing closed with `COVERAGE_DEFICIT` against the 90.0% threshold.
