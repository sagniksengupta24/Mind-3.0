# Mind 3.0 Integrity Audit (P1)

## Policy & Defect Inventory

### 1. `allow_mock_fallback` / `mock` / `fallback`
- **Location**: `src/mind3/core/driver.py:1198`
  - **Hit**: `allow_mock_fallback=True` in `PhaseDriver.run_silicon_pipeline` fallback instantiator.
  - **Classification**: **DEFECT**. Violates Rule I5 (mock/fallback must be unreachable from production and benchmark paths).
  - **Resolution**: Changed to `allow_mock_fallback=False`.
- **Location**: `benchmark_scratch/run_benchmarks.py:271` and `324`
  - **Hit**: `SiliconSignoffVerifier(..., allow_mock_fallback=True)` in `run_single_verilog_eval_task` and `run_single_rtllm_task`.
  - **Classification**: **DEFECT**. Violates Rule I5.
  - **Resolution**: Changed to `allow_mock_fallback=False`. Added active assertion rejecting `allow_mock_fallback=True` in benchmark mode.
- **Location**: `src/mind3/core/verifier.py:727`
  - **Hit**: `def __init__(..., allow_mock_fallback: bool = False)`
  - **Classification**: **JUSTIFIED**. Default is `False`. Only opt-in for unit tests.

### 2. Tautological Formal Properties & Weakening (`assert(1'b1)`)
- **Location**: `src/mind3/core/contracts.py:490` and `560`
  - **Hit**: `expr = "1'b1"` in `_generate_assertion_block` / `build_sva_bind_module`.
  - **Classification**: **CRITICAL DEFECT**. Violates Rules I2, I3, I4. Substituting `assert(1'b1)` for unsupported temporal properties creates false passes.
  - **Resolution**: Removed completely. Unsupported properties must emit an explicit `UnsupportedFormalPropertyError` and cause Gate 2 to fail with `error_category="UNSUPPORTED_FORMAL_PROPERTY"`.
- **Location**: `src/mind3/core/contracts.py:337-339`
  - **Hit**: Shift register temporal check `q == {d, q[7:1]}` rewritten to check only MSB `q[7] == d`.
  - **Classification**: **DEFECT**. Violates Rule I4 (syntactically valid but weaker assertion is not a fix).
  - **Resolution**: Rewrite to exact procedural equivalent with `$past`: `q == {$past(d), $past(q[7:1])}` or fail with `UNSUPPORTED_FORMAL_PROPERTY` if unsupported.

### 3. Silent Property Skipping & Deletion
- **Location**: `src/mind3/core/contracts.py:400` and `411`
  - **Hit**: `// Skipping this property - no equivalent procedural assertion generated`
  - **Classification**: **DEFECT**. Violates Rules I2 and I3. Silent deletion/skipping of assertions is forbidden.
  - **Resolution**: Must raise `UnsupportedFormalPropertyError` and fail Gate 2.

### 4. Empty Formal Property Set
- **Location**: `src/mind3/core/verifier.py:1236`
  - **Hit**: When `contract.sva_properties` was empty, SBY ran without assertions, trivially passing.
  - **Classification**: **DEFECT**. Violates Rule I2 (empty property set -> FAIL or explicit status).
  - **Resolution**: Added explicit check in Gate 2: if `sva_properties` is empty, return `passed=False, error_category="EMPTY_FORMAL_PROPERTY_SET"`.

### 5. Missing EDA Tooling Status
- **Location**: `src/mind3/core/verifier.py`
  - **Hit**: When binary is missing, `EDA_BINARY_MISSING` was returned, but Rule P1 requires explicit `TOOL_ERROR` mapping.
  - **Classification**: **DEFECT**.
  - **Resolution**: Standardized error category to `TOOL_ERROR` when required EDA tool is missing.

### 6. Architectural Duplication (Rule A1)
- **Location**: `benchmark_scratch/run_benchmarks.py:sanitize_extracted_verilog`
  - **Hit**: Standalone parsing duplicated regex unescaping and AST extraction.
  - **Classification**: **DEFECT**.
  - **Resolution**: Routed `sanitize_extracted_verilog` directly to authoritative `_parse_model_code_response`.
- **Location**: `src/mind3/core/contracts.py:build_sva_checker_module` vs `build_sva_bind_module`
  - **Hit**: Two duplicate implementations of SVA checker generation.
  - **Classification**: **DEFECT**.
  - **Resolution**: Consolidated to single implementation `build_sva_bind_module`; aliased `build_sva_checker_module`.
