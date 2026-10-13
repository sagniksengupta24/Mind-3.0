# STOP — S3 H1 halted: P5-as-specified vs sync-reset specs vs exit criterion

## Trigger
AUTO-STOP (a) stage exit criterion not met + (c) finding needing a verifier
change beyond P3/P5/P6/P7. No fix applied for this finding. Waiting for owner.

## What ran (VERIFIED)
- S3(a) tests-first executed pre-fix: `pytest tests/soundness/test_h1_gate_fixes.py`
  → 3 failed / 5 passed in 117s. Failures shown: full-contract reset tasks
  VACUOUS, tautology-only not NO_GENUINE, flag-ON harness identical (no impl).
  All 18 script mutants (`tests/soundness/make_mutants.py` → 18 files in
  `tests/golden_mutants/`) FAIL pre-fix (caught). Results in
  `results/v4/soundness/h1_results.json`.
- P3/P5/P6/P7 implemented behind `MIND3_GATE_FIXES` (default ON) in
  `src/mind3/core/formal_templates.py` + `src/mind3/core/verifier.py` only.
  Unit checks: tautology predicate 13/13, P5 fifo_01 guard diff `!init && rst_n`
  → `!init`, flag `0` restores exact prior behavior.

## The conflict (VERIFIED commands + outputs, well-formed RTL, REAL Gate 2)
- P5 reset-antecedent `!rst_n |-> out_data == 0`, correct SYNC-reset design:
  `passed=False FORMAL_INVARIANT_BREACH at step T=2`.
- Same property, correct ASYNC-reset design:
  `passed=True`, "All 1 implication antecedent(s) reached within bound".
- P5 renders `if (!init) begin if (!rst_n) assert (out_data == 0); end`
  (guard diff VERIFIED above). Same-cycle sampling requires `out==0` at any
  edge where reset is asserted — satisfiable only by async-style reset response.
- Every dev-20 task mandates **synchronous** reset
  (`clock_reset_assumptions`, VERIFIED across all 20 records), so no
  spec-conformant golden can pass a P5 reset check: S3(d) exit ("every golden
  except counter_04 passes every available gate") is unreachable under P5's
  letter. V1 VCD tables corroborate (reset asserted row 0, solver-controlled
  timing, no wrapper reset sequencing).

## Ruled out
- Probe-malformation false alarm: one early sync probe lacked the `in_data`
  declaration (my error, disclosed); re-ran well-formed — verdict stands.
- Async redesign of goldens: contradicts specs AND fails Gate 1 structural
  check ("Synchronous reset must not appear in sensitivity list" seen on the
  async fsm golden in V1). No unilateral fix exists within P3/P5/P6/P7:
  masking the first reset cycle contradicts " |-> same cycle".

## Uncommitted work left in tree (do not lose)
- `src/mind3/core/formal_templates.py`, `src/mind3/core/verifier.py` (P-impl)
- `tests/soundness/test_h1_gate_fixes.py`, `tests/soundness/make_mutants.py`
- `tests/golden_mutants/` (18), `tests/golden/arbiter_02.sv`,
  `tests/golden/fsm_heldout_04.sv` (V1 fixes kept)
- `results/v4/soundness/h1_results.json`
- Tautology-only + flag-ON-harness-diff assertions already FAIL pre-fix as
  designed; P3/P6/P7 behavior verified at unit level, full H1 post-fix run
  NOT yet executed.

## Options for owner (ranked)
1. Amend P5: check reset behavior from the second asserted cycle
   (`!init && $past(!rst_n)`-style stability mask). Sync goldens then pass;
   noreset/wrongreset mutants still caught. Needs 1-line guard change + H1 rerun.
2. Drop `|->` reset-antecedent properties from the passable set (spec defect
   acknowledged); goldens pass without them. No code change.
3. Accept async-reset goldens + waive the Gate-1 sync-reset structural check.
   NOT recommended (contradicts all 20 specs).

## Resume
Read PORT_LOG.md, `git log`, this file; `git status -sb` shows the files above.
Then either (option 1) implement + rerun H1, or continue as directed. Replay
still ON HOLD. No push performed.
