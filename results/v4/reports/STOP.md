# STOP — RESOLVED by owner option 1 (see S3.md for completion)

Prior halts below are superseded: P5b implemented per amended decision; fifo
timeout resolved via P8 (T=240); halfreset replaced in-count by fsm__noreset
with halfreset kept as documented spec-coverage evidence. S3 exit met.
Kept as history. Original halt text follows.

---

Supersedes prior S3 STOPs (P5→P5b resolved; Gate 4 resolved; P8 done).
AUTO-STOP (a) exit not met, presenting as (b). Waiting for owner. No replay.

## What ran since (all VERIFIED)
- P8 implemented + tested (`test_p8_timeout.py` 2 passed): T=240 default
  (measured: arbiter ~0.6s, fsm/reset/apb ~1.2s, fifo direct-sby 110.9s PASS;
  no yices/boolector installed). FORMAL_TIMEOUT on exit-124 with the exact
  sentence and no counterexample fields; wall time in every Gate-2 result;
  timeout_edge on PASS >50%; flag-0 exact (timeout matrix 60/5/240/240/240 +
  real BREACH carries zero new keys). Cover job stays 60s.
- H1 rerun matrix WITH liberty (`test_h1_rerun_matrix.py`): goldens × {0,1}.
  Flag-1 pipelines: 5/5 PASS (G1, G3 incl. arbiter P7 N/A, G2 incl. fifo
  29.9s PASS, G4 0.1–0.2s PASS, G6, DFT); counter_04 fail-closed
  (FORMAL_ANALYSIS_FAILED). Flag-0 contrast fails exactly as V0/V1.
- Mutants × {0,1} full pipelines WITH liberty: **21/22 caught** by definitive
  failures; zero timeout-only catches.

## The survivor (VERIFIED, root-caused)
- `fsm_heldout_04__halfreset` (ones counter not cleared on reset): full
  pipeline passes with fixes ON.
- Direct G2 probe: `passed=True`, "All 2 implication antecedent(s) reached
  within bound" — the gate PROVED (not vacuously passed) both stated
  properties: `stuffed|->dout==0` holds (dout IS 0 whenever stuffing fires)
  and P5b `$past(!rst_n)|->!stuffed` holds (checked cycles always have
  freshly-cleared stuffed; the stale-ones effect lands only in unchecked
  cycles where reset was not recently asserted).
- The defect (wrong stuffing cadence after reset) violates the task's
  natural-language spec but NO stated formal property. Attribution:
  spec-coverage gap, gate correct. Note: under P5-same-cycle the first-
  assertion-cycle leftover WOULD have been caught; P5b's approved `$past`
  shift blinds exactly that window — inherent to the amendment, not a bug.
- My script annotation ("violates !rst_n |-> !stuffed") was written for P5
  semantics and is wrong under P5b: the mutant never met my own selection
  rule (must violate a SPECIFIED property). fsm also lacks the mandated
  "reset ignored" mutant kind.

## Uncommitted work left in tree (do not lose)
- HEAD `ad3d0e3` (P5-era WIP). Worktree-only: P5b impl (formal_templates.py,
  contracts.py), P8 (verifier.py), PORT_LOG P5b+P8 entries,
  `test_h1_gate_fixes.py`, `test_p5b_reset_rendering.py`, `test_p8_timeout.py`,
  `test_h1_rerun_matrix.py`, `make_mutants.py` (+4 kinds), `tests/golden_mutants/`
  (+4 new), `results/v4/soundness/{h1,p5b,p8_timing}.json`, `v1_fifo01_harness/`,
  this file. S3(d) flag-0/flag-1 matrix data is in h1_results.json.

## Options for owner (ranked)
1. Replace the spec-invisible mutant with `fsm__noreset` (mandate's "reset
   ignored" kind; I predict BREACH: firing stuffed across reset violates the
   P5b check), keep halfreset as documented spec-coverage evidence excluded
   from the exit count, and continue S4–S11.
2. Strengthen the fsm spec properties (task files currently off-limits).
3. Anything else; replay stays ON HOLD.

## Resume
Read PORT_LOG.md, `git log` (HEAD `ad3d0e3` + worktree per `git status -sb`),
this file. Rerun: `pytest tests/soundness/test_h1_rerun_matrix.py` (goldens
~3min, mutants ~3min) after any P5b/timeout decision.
