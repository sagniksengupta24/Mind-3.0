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

## S3 (H1 gate completeness: P3/P5b/P6/P7/P8; exit met with 1 exclusion + counter_04)
- P3 (tautology drop + NO_GENUINE_PROPERTY), P5b (sync `$past(reset)` rewrite,
  async same-cycle, contract-style-only), P6 (`$past(rst)` boundary, never on
  P5b props), P7 (branch N/A, toggle unchanged), P8 (T=240 measured: others
  ~1s, fifo direct-sby 110.9s PASS; FORMAL_TIMEOUT on exit-124; wall time +
  timeout_edge, all flag-gated; cover stays 60s). One flag:
  MIND3_GATE_FIXES (ON/0-exact, incl. strict report-shape exactness).
- H1 rerun matrix WITH liberty: flag-1 pipelines 5/5 PASS (G4 0.1-0.2s with
  liberty in pipeline order); 22/23 mutants caught, zero timeout-only.
  Documented exclusion (owner option 1): `fsm__halfreset` is provably
  spec-invisible under approved P5b semantics (gate PROVED both implications
  with antecedents reached); replaced in-count by `fsm__noreset` (caught).
- S3(c): sta 3.1.0 + 12.8MB liberty exist; Gate 4 passes via Gate-1 netlist in
  pipeline order (standalone `-sv` feed fails on `logic` keyword — harness
  artifact, not a gate defect). reset_02 full pipeline: all gates PASS in 8s.
- `scripts/run_negative_controls.py --require-live`: SUCCESS (1 env SKIP).
- Regression caught by suite: bare `pass` in `_gate2_timeout_sec` tripped
  `test_zero_stubs_integrity`; fixed (behavior-identical) and green.
- Standing nuisance: V0/V1/H1 tests rewrite result JSONs (timestamp churn) and
  V1 regenerates its own reference harness (restored post-run); write-on-change
  follow-up recorded.

## S4 (passable ceiling: 19/20)
- Static classification under the NEW rendering (`results/v4/dev_passable.json`):
  21 same-cycle (P5b-checkable), 15 boolean (13 tautologies dropped, 2 genuine),
  2 next-cycle, 1 onehot0, 1 unsupported (counter_04 `$past`-slice).
- All 20 dev contracts declare synchronous reset (VERIFIED) → P5b-sync uniform.
- PASSABLE 19/20 (all but counter_04: unsupported poisons vacuity cover).
  Caveats: antecedent reachability is runtime-proven (cover), not static;
  fifo_04 multi-clock unprobed at runtime; ceiling assumes spec-faithful RTL.

## P5b (UNCOMMITTED WIP on feat/det-assist; supersedes P5)
- Deliberate verifier change, reason: dev-20 specs mandate synchronous reset
  yet state reset checks in same-cycle `!rst_n |-> X` form, which no
  spec-conformant design can satisfy under P5 (benchmark authoring defect;
  dev task files NOT edited). P5b: sync contracts render
  `$past(reset asserted) |-> X` under init-only guard; async contracts keep
  same-cycle + init-only; choice ONLY from `contract.reset.synchronous`;
  no P6 on rewritten props; cover checks the rewritten antecedent.
- Files: `formal_templates.py` (`reset_synchronous` threading, render sites),
  `contracts.py` (thread contract flag into 3 compile calls), no verifier.py
  behavior change for P5b. Behind MIND3_GATE_FIXES (default ON; 0 = V0/V1).
- S3 HALTED (second STOP.md): see `results/v4/reports/STOP.md`. Summary:
  P5b passes 3/4 sync goldens + full reset_02 pipeline WITH liberty passes ALL
  gates; fifo_01 P5b-BMC exceeds the fixed 60s gate timeout (Z3 order luck at
  the budget edge) and timeouts misreport as BREACH (exit 124).

## P8 Gate-2 timeout (UNCOMMITTED WIP; deliberate verifier change)
- Reason: S3(d) halt — fifo_01 P5b-BMC needs ~111s (measured direct-sby,
  solver z3, depth 25) against the fixed 60s limit, and timeouts misreported
  as FORMAL_INVARIANT_BREACH (exit 124).
- Measurement (serial, VERIFIED): arbiter_02 ~0.6s, fsm/reset/apb ~1.2s,
  fifo_01 capped 60s ×3 + direct 110.9s PASS. No yices/boolector installed
  (no solver comparison possible; engine stays smtbmc z3).
- Selection: smallest T in {120,180,240} with every golden < T/2 → **240**
  (111 < 120). Saved in `results/v4/soundness/p8_timing.json`.
- Implementation (`verifier.py` only): `_gate2_timeout_sec()` (flag off → 60
  exactly; otherwise MIND3_SBY_TIMEOUT_S clamped to (0,240], default 240);
  exit-124 → FORMAL_TIMEOUT fail-closed with "formal check did not finish;
  no counterexample" and NO counterexample fields; `gate2_wall_s` in every
  Gate-2 result + `timeout_edge` on PASS beyond 50% (both fixes-gated, so
  flag-0 reports are byte-shape-identical to V0/V1). Cover job keeps 60s
  (observed <2s). No solver/SBY config change.
