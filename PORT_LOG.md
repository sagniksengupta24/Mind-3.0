# PORT_LOG — port-hunk intake record (copy is canonical; port is read-only reference)

## D3 stage-key fix (applied; default ON; deliberate baseline-affecting bug fix)
- Source: `~/Desktop/Mind-3.0-port` `src/mind3/core/driver.py` (`pending_stage_key`).
- Bug on snapshot (`3e01cbc`): `run_silicon_pipeline` hardcoded `stage_key = "compile"`
  at the top of every repair iteration, so a formal/simulation failure's follow-up
  repair MODEL_CALL was labeled/budgeted as `compile`.
- Fix: keep `pending_stage_key` (init `"compile"`); each iteration uses
  `stage_key = pending_stage_key`; after every EDA failure set
  `pending_stage_key = stage_key`. Verbatim port logic; default ON (no flag).
- Baseline impact (deliberate): repair-trace `stage` labels and `_stage_repair_attempts`
  buckets change for non-compile failures (e.g. `formal` instead of `compile`).
- Regression: `tests/test_stage_preservation.py::test_formal_stage_preserved_across_repairs`
  FAILED pre-fix (`['compile', 'compile']`) and passes post-fix.

## D4 skip-unchanged (applied; flag MIND3_SKIP_UNCHANGED, default OFF)
- Source: port `_rtl_identity_hash` + skip/rollback/feedback control flow.
- Behavior: when the flag is ON and the narrow hash (line-endings/trailing
  whitespace only) of the repair candidate matches the current RTL, the verifier
  is skipped, a REPAIR_UNCHANGED_CANDIDATE VERIFY trace is recorded, bounded
  stage/parse budgets apply, and corrective feedback ("Do not return the same
  implementation again…") is returned. When OFF (default), behavior is the
  snapshot (identical candidates still consume an EDA turn).
- Kept from copy: raw+normalized C1 identity records (`_candidate_hashes`,
  `candidate_identity`, `unchanged_candidate`) are always logged; a
  normalized-only match (e.g. comment-only) must NOT skip the verifier.
- Tests: adapted port T1 (3 tests, `_with_skip_flag`, flag ON) in
  `tests/test_skip_unchanged_flag.py` plus golden flag-off test; port B1 narrow
  hash test added to `tests/test_repair_budget.py` unchanged.

## R5 evidence v2 (NOT implemented; recorded input, default unchanged)
- When MIND3_EVIDENCE_V2 is ON (future): verifier-reported
  expected/observed/reset/clock fields take precedence over contract-derived
  guesses, and the port's counterexample-procedure repair prompt is used.
- Default stays as the copy (C2 enrichment + minimal-diff/never-resubmit prompt).
- R1/R2/C1: keep the copy (no change).
