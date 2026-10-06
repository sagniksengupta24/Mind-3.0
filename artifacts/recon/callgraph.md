# Single-implementation map (observed via grep, no execution)

## Model-response parsing
- `_parse_model_code_response` — src/mind3/core/driver.py:178. Call sites:
  driver.py:1669 (initial generation), driver.py:1759 (repair),
  benchmarks/baselines.py:224 (baseline A), benchmarks/baselines.py:385 (baseline B repair).
  NO duplicate implementation observed.
- `_reconstruct_from_ast` — nested closure driver.py:228, called driver.py:517 (lenient JSON branch only).
- `_unescape` — nested closure driver.py:217, used by AST/known-key recovery.

## Contracts
- `InterfaceContract` — src/mind3/core/contracts.py:133.
- `SVAProperty` — src/mind3/core/contracts.py:55.
- `VerificationHarnessGenerator` — src/mind3/core/contracts.py:795.
- `build_sva_bind_module` — contracts.py:1011. Callers: driver.py (harness staging), verifier.py Gate 2 formal flow.
- `build_formal_wrapper` — contracts.py:1120. Callers: driver.py staging, verifier.py Gate 2.
- `build_sby_config` — contracts.py:1084. Callers: driver.py staging, verifier.py Gate 2.

## Signoff pipeline
- `SiliconSignoffVerifier` — src/mind3/core/verifier.py:949; `verify` at verifier.py:1082.
- Gate 1 entry `_run_gate1_yosys` — verifier.py:1298; called verifier.py:1107.
- Gate 3 entry `_run_gate3_coverage` — verifier.py:2089; called verifier.py:1145.
- Gate 2 entry `_run_gate2_formal_sby` — verifier.py:1836; called verifier.py:1162.
- Verilator coverage runner: inline in `_run_gate3_coverage` (verilator `--cc --exe --build`, coverage.dat parse).

## Drivers / clients / runner
- `PhaseDriver` — src/mind3/core/driver.py:683 (owns `_query_model` dispatch).
- `BenchmarkRunner` — src/mind3/benchmarks/runner.py:181.
- Ollama client: `PhaseDriver._query_ollama` — driver.py:953 (no separate OllamaClient class observed).
- OpenRouter client: `PhaseDriver._query_openrouter` — driver.py:980.

## Mock / fallback paths (all gated on allow_mock_fallback; default False)
- verifier.py:1376/1381 compile, :1476 latch-check sim, :1613/:1671 LEC, :1943 formal,
  :2168 coverage, :2392 STA, :2644 PnR, :2858/:2906 CDC. Each emits "[SIMULATED - NOT REAL TOOL OUTPUT]".
- driver.py/benchmarks baselines/runner contain "mock" only for mock-provider schema fixtures (NOT OBSERVED as live-verdict paths).
- `get_gate_presentation_label` (verifier.py:3061) derives [REAL EDA]/[SIMULATED]/[SKIPPED]/[NOT_RUN] from report fields.

## Duplicates
- No duplicate parser, contract, harness-generator, or signoff-verifier implementations observed.
- Sibling `*Verifier` classes (RTL/Software/IndustryReport, verifier.py:56/172/226) are separate product surfaces, not duplicates of the signoff path.
- `verify()` overrides exist per subclass (expected polymorphism), single signoff implementation at verifier.py:1082.
