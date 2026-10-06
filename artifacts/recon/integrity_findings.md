# Integrity grep (read-only; verdicts are static-code review, not fixes)
Scope: src/mind3/core, src/mind3/benchmarks (tests excluded).

## allow_mock_fallback (default False at verifier.py:977,1023; forced False at driver.py:1720, baselines.py:184/453, runner.py:373)
- verifier.py:1376/1476/1613/1656/1924/2149/2279/2370/2639/2853/2901/2962 — every branch either returns simulated=True with "[SIMULATED - NOT REAL TOOL OUTPUT]" text or fails closed. Verdict: SAFE (labelled simulation, never presented as signoff).
- No live benchmark path sets allow_mock_fallback=True (all observed call sites pass False). Verdict: SAFE.

## mock / fallback strings in src
- "mock" hits in src are: mock-provider schema-fixture labels (baselines.py/runner.py, counted as non-evidence) and the SIMULATED markers above. No live-verdict mock path observed. Verdict: SAFE.

## "return True" hits
- verifier.py:859 (`_is_binary_missing` helper), :2720-2728 (`_cdc_requirement` returns CDC-required decision + reason string, not a gate pass), release.py:89 (bundle integrity message). Verdict: SAFE.
- driver.py:1411/1838 — both execute only after `v_result.passed` is true (genuine pass-through of verifier verdict). Verdict: SAFE.
- contracts.py:859 — temporal-pattern predicate (unsupported-construct classifier). Verdict: SAFE.

## skip_gate
- No `skip_gate` symbol observed in src. Gate skipping exists only as contract-declared/opt-out SKIPPED reports (verifier.py Gate 6 paths), never as silent bypass. Verdict: SAFE.

## bare except / except-continue
- verifier.py:473 (coverage.dat unreadable -> all-None), :920 (tool version -> "missing"), :1414 (source context -> ""), :1538 (AST parse -> ast_available=False, falls to fail-closed path).
- driver.py:224/477/492/513 (parser fallbacks -> None -> ModelResponseParseError, fail-closed).
- cache.py:71 (cache miss -> None), reproducibility.py:56 (-> "UNKNOWN_COMMIT").
- Verdict: SAFE in all cases (fail-closed or unknown-label defaults).

## assert(1'b1) / trivially-true assertions
- None observed in src. Verdict: SAFE (nothing to report).

## Empty-property handling
- verifier.py:1857-1858: empty formal property set -> explicit FAIL ("cannot sign off"). Verdict: SAFE (fail-closed, opposite of a bypass).

## Tool error / timeout / exception -> PASS paths
- None observed. Every tool-error branch observed returns passed=False with a named error_category (EDA_BINARY_MISSING, TIMING_ANALYSIS_FAILED, CDC_ANALYSIS_FAILED, ENVIRONMENT_FAILURE, etc.). Verdict: SAFE.

## Overall
No DEFECT verdicts. No SUSPECT verdicts requiring confirmation beyond normal review. One standing watch-item (from prior sessions, not re-proven here): `$dffsr`/`$sr` membership in the Gate 1 latch cell list — marked INFERRED, needs a dedicated probe with a set/reset-flop design.
