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

## V0 follow-up (NOT fixed): brace-concat $onehot0 crashes the formal gate
- Repro: `assert property (@(posedge clk) $onehot0({gnt1, gnt0}));` as an
  `sva_properties` entry makes `classify_legacy_property` build a
  `FormalPropertySpec` with `signal='{gnt1, gnt0}'`, which fails the identifier
  validator; the resulting pydantic `ValidationError` is NOT an
  `UnsupportedFormalTemplate`, so `_run_gate2_formal_sby` does not fail closed —
  the exception escapes the gate (evidence:
  `results/v4/soundness/v0_results.json`, `onehot0_brace_concat` → ERROR).
- Not in the dev-20 corpus (arbiter_02 uses single-signal `$onehot0(gnt)`).
- Fix deferred by owner decision; candidates: catch `ValueError` alongside
  `UnsupportedFormalTemplate` in the gate, or reject brace operands in the
  classifier with `UnsupportedFormalTemplate`.

## S1 (V1 commit + vacuity history)
- Committed V1 audit files as `9640388` ("V1 gate completeness audit, test-only"):
  `tests/soundness/test_v1_completeness.py`, `tests/golden/` (6 UNREVIEWED),
  `results/v4/soundness/v1_results.json`, `results/v4/soundness/v1_fifo01_harness/`.
- Vacuity check (`VACUOUS_PROPERTY`, `_run_gate2_vacuity_check`) entered the tree
  in `5c7e7ec` (2026-10-02), in HEAD's ancestry. The only recorded historical runs
  (`results/`, heldout mock suite, 2026-09-30, sha `9201daf` from 2026-09-22)
  predate it and recorded 0 passes; dev-20 has no recorded passes at all. So no
  historical pass postdates (or is invalidated by) the vacuity check.
- Standing nuisance (not fixed): every full-suite run re-executes the V0/V1
  soundness tests, which rewrite `v0/v1_results.json` SBY timestamp tails and
  dirty the tree. Follow-up: write result JSONs only on verdict change.

## S2 (golden review package)
- Wrote `results/v4/reports/goldens_for_review.md`: six goldens reprinted
  verbatim (machine-checked against `tests/golden/`) with the spec fields each
  was written from. Goldens unaltered.
