# Mind 3.0 Call Graph & Architectural Audit (P0)

## Component Callgraph & Symbol Inventory

### 1. Response Parsing & RTL Extraction
- `src/mind3/core/driver.py:_parse_model_code_response(raw_output: str) -> str`
  - Helper `_unescape(val: str) -> str`
  - Helper `_reconstruct_from_ast(data: dict) -> str | None`
  - Invocations: Called by `PhaseDriver.run_silicon_pipeline` and `PhaseDriver._repair_loop` during RTL extraction from LLM generations.
  - Duplicate/Divergence: `benchmark_scratch/run_benchmarks.py:sanitize_extracted_verilog` implemented a separate, non-authoritative extraction path with regex replacements and JSON parsing. Per Rule A1, this must be unified with the authoritative driver implementation.

### 2. Contract & Formal Specification Models
- `src/mind3/core/contracts.py:SVAProperty`
  - Pydantic model representing formal properties (`name`, `property_expr`, `description`, `clock`, `reset`, `polarity`).
- `src/mind3/core/contracts.py:InterfaceContract`
  - Encapsulates module interface: `module_name`, `ports`, `parameters`, `fsm`, `sva_properties`, `timing`.
  - Export methods: `to_verilog_header`, `to_sdc`, `to_upf`.

### 3. Verification Harness & Assertion Generation
- `src/mind3/core/contracts.py:VerificationHarnessGenerator`
  - `build_sva_bind_module(contract: InterfaceContract) -> str`: Generates Yosys-compatible formal checker module containing procedural assertions.
  - `build_formal_wrapper(contract: InterfaceContract) -> str`: Generates wrapper instantiating DUT and checker for Yosys BMC without requiring unsupported SystemVerilog `bind`.
  - `build_sby_config(contract: InterfaceContract, depth: int, ...) -> str`: Emits `.sby` configuration file specifying engines, options, and files.
  - `build_verilator_cpp_testbench(contract: InterfaceContract) -> str`: Generates C++ test driver for Verilator simulation and coverage.

### 4. Silicon Signoff Pipeline & Gates
- `src/mind3/core/verifier.py:SiliconSignoffVerifier`
  - `verify(workspace: Path, sandbox: BubblewrapSandbox) -> VerificationResult`
    - Sequentially executes Gates 1 -> 1b -> 2 -> 3 -> 4 -> 5 -> 6 -> DFT.
    - Fails closed on first non-optional gate violation.
  - Gate 1: `_run_gate1_yosys(runner, sources, ws)`: Yosys elaboration, hierarchy check, latch trap detection.
  - Gate 2: `_run_gate2_formal_sby(runner, sources, ws)`: SymbiYosys bounded model checking (BMC).
  - Gate 3: `_run_gate3_coverage(runner, sources, ws)`: Verilator compilation and coverage metrics analysis.
  - Gate 4: `_run_gate4_timing(runner, sources, ws)`: OpenSTA static timing analysis.
  - Gate 5: `_run_gate5_openroad_pnr(runner, sources, ws)`: OpenROAD physical design (opt-in).
  - Gate 6: `_run_gate6_cdc_analysis(runner, sources, ws)`: Yosys CDC static analysis.

### 5. LLM Model Invocation & Repair Loop
- `src/mind3/core/driver.py:_call_ollama(model: str, prompt: str, ...) -> str`: Direct HTTP interaction with local Ollama daemon (`http://localhost:11434/api/generate`).
- `src/mind3/core/driver.py:_repair_loop(...)`: Multi-turn iterative repair feeding categorized gate diagnostic failures back to the LLM.

### 6. Benchmark Harness
- `benchmark_scratch/run_benchmarks.py`: Adapter running VerilogEval v2 and RTLLM v1.1 tasks, invoking `PhaseDriver` and grading against external ground-truth testbenches.

---

## Path Differences & Duplication Audit (Rule A1)

1. **Response Parsing**:
   - Production path: `PhaseDriver._parse_model_code_response` in `src/mind3/core/driver.py`.
   - Benchmark path: `sanitize_extracted_verilog` in `benchmark_scratch/run_benchmarks.py`.
   - Action: Harmonize `run_benchmarks.py` to use `PhaseDriver._parse_model_code_response` directly as the single source of truth.

2. **Mock / Fallback Policy (Rule I5)**:
   - In `benchmark_scratch/run_benchmarks.py`, lines 271 and 324 initialized `SiliconSignoffVerifier(allow_mock_fallback=True)`.
   - Action: This must be strictly `allow_mock_fallback=False` in all benchmark and production executions. Mock fallback is forbidden on signoff paths.

3. **Gate 2 Formal Checker Generation**:
   - `build_sva_checker_module` and `build_sva_bind_module` were duplicating code.
   - Action: Route to single canonical implementation in `VerificationHarnessGenerator`.

4. **Tautological Assertions (`assert(1'b1)`)**:
   - In `src/mind3/core/contracts.py:490`, unsupported temporal expressions fell back to `expr = "1'b1"`.
   - Action: Prohibited by Rules I2, I3, I4. Unsupported properties must emit an explicit error / status `UNSUPPORTED_FORMAL_PROPERTY`.
