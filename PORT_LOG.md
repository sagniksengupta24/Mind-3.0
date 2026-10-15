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

## Hygiene: eda marks + tracked-write gating (committed)
- Tagged every real-tool test with the existing `@pytest.mark.eda`
  (module-level for the 5 uniform soundness files; function-level for the 2
  render-only p5b tests left unmarked, the smoke probe, the 9-param live
  negative-control test, gate2 test_7, and the 3 PDK canaries): eda 27 -> 57,
  non-eda 441 -> 411, collected total unchanged at 468. Deliberately NOT
  marked (verified pure/fast): assurance receipts, r2/benchmark evaluator
  logic, commercial simulated receipts, parser fixtures, `--version` canary,
  `git`-based claim hygiene, CDC presence checks, sandbox probes, all mocked
  suites. Fast suite wall: 21m40s -> ~7s.
- `_writable_results_path()` in all 6 soundness files: tracked result JSONs
  (and the v1 reference harness) are written only with
  `MIND3_WRITE_RESULTS=1`; default goes to untracked `results/v4/runs/`
  (added to .gitignore). Reads prefer mirror-if-exists else tracked, so
  multi-test merge semantics are preserved. Verified: sha256 of tracked
  JSONs byte-identical pre/post fast run.

## P3-COMPLETE: classifier-level tautology rejection (committed)
- `FormalTemplateKind.TAUTOLOGY` + `is_tautological_property_text()` in
  `formal_templates.py`, gated on `gate_fixes_enabled()` (flag-0 kinds
  byte-identical: boolean/same_cycle as before). Decides: constant-true,
  structural P3 forms, identical-normalized `X |-> X`, constant-false
  antecedent / constant-true consequent, and a truth table over <= 8 vars
  (identifiers/`!`/`&&`/`||` only; `==`/`!=` atomized with commutative
  canonicalization; slices/arithmetic/calls/`|=>`/temporals abstain).
- Drops wired into the audit + both `compile_contract_properties` branches;
  all-tautology contracts fail closed (`NO_GENUINE_PROPERTY`, live-proven).
  `compile_cover_point` needs no change (TAUTOLOGY has no antecedent).
- Comparison vs skipped patches 0008/0009: every disclosed catch-form is
  caught except slice-bearing `en |-> (gnt[0] || !gnt[0])` (spec-mandated
  exclusion; verifies normally, harmless). `~a || a` / `x[0]==x[0]` were
  already structural-P3 catches.
- Tests: 4 R3-B reproducers converted to conditional-xfail (pass flag-1,
  xfail flag-0); +14 table positives (flag-1, xfail flag-0) incl. the F2
  disclosed forms; +9 negatives incl. `a |=> a` and slice abstains; one
  mocked gate-2 test updated to the fail-closed expectation (flag-split).
  Fast suite: 434 passed flag-1; flag-0   green except pre-existing
  P5b-render assertion (render-only, untouched by this change).

## Gate-1 INCOMPLETE_RESET partial-reset trap (committed)
- Structural trap in `_run_gate1_yosys` (MIND3_GATE_FIXES, sync contracts
  only): per clocked block with a reset branch, `LHS_non_reset -
  LHS_reset` non-empty fails closed with the missing names (e.g. `ones`)
  in the diagnostic. No-reset-branch blocks neutral (noreset-class keeps
  downstream verdicts); loop iterators/genvars/block-local temporaries and
  unpacked-array memories excluded. Balanced-paren/call-stripped scanning;
  flag-0 path untouched.
- S3 `fsm__halfreset` exclusion removed from both soundness files: the
  matrix natively requires 23/23 (halfreset caught at Gate 1).
- Rejected alternative (documented): +2-cycle reset-release temporal
  assertion caught halfreset but false-failed 4/5 goldens (fifo_01 step-2
  legitimate-write trace) — output-level checks past 1 cycle race
  legitimate post-release operation; reverted.
- Tests: `tests/test_gate1_reset_trap.py` (5 pure incl. repo golden/mutant
  agreement, 2 live flag-split incl. broken-RTL negative control).
  Live matrix: 5/5 goldens, 23/23 mutants, halfreset@Gate-1/INCOMPLETE_RESET,
  noreset verdicts unchanged. Fast suite 439 green.

## R5 evidence decoder + repair guard (UNCOMMITTED: src/mind3/core/vcd_evidence.py,
## contracts.py/build_prompt evidence_v2 flag, driver.py decode + multidriven pre-check,
## tests/test_r5_evidence_v2.py + tests/fixtures/vcd/arbiter_02_formal_breach.vcd)
- `MIND3_EVIDENCE_V2` (default OFF; flag-0 prompts byte-identical, proven by
  golden test). Flag ON: formal-breach VCDs decode to a cycle table (contract
  ports + failing-property signals, steps 0..t_fail capped at 10, reset
  asserted/released marking) replacing raw trace ASCII in evidence; cycle +
  relevant_signals filled; repair system prompt gains the single-driver
  guard (in-place always-block edits, never a second `assign` driver).
- Multidriven pre-check mirrors REPAIR_PATCH_TOO_LARGE (feedback + continue,
  no EDA turn): `detect_multidriven_nets` (assign vs always LHS, locals and
  comparisons excluded), mocked-driver integration test proves a duplicate
  `assign gnt` is rejected pre-EDA with REPAIR_MULTIDRIVEN.
- Mocked tests (10, fast): flag default/off/on prompts, real-VCD decode
  shape, deep-trace capping, malformed-input safety, multidriven
  positive/negative/edge cases, pre-EDA rejection. Fast suite 449 green.
- Controlled arbiter_02 runs (flag ON, seed 43, text format, 2 attempts):
  model deterministically emits async `or negedge rst_n` RTL -> Gate-1
  CLOCK_RESET_ERROR both turns (known R3 async gap); formal never reached,
  so live decode/guard legs were proven instead by a deterministic
  single-repair-turn probe on registered-grant RTL: live BREACH step 2 ->
  decoded table (reset asserted@0 SOLID) -> guard-bearing prompt -> live
  Ollama repair (clean, no multidriven) -> re-verify still BREACH
  (mechanics proven; model repair quality unchanged: 0/1).

## Sync-reset sensitivity guard + failure-report reselection (UNCOMMITTED:
## vcd_evidence.py sensitivity helpers, contracts.py/build_prompt sensitivity_guard,
## driver.py pre-check + NOT_RUN reselection, tests/test_repair_sensitivity_guard.py)
- Models reflexively emit `always_ff @(posedge clk or negedge rst_n)` on
  seeing `rst_n`. Flag ON (MIND3_EVIDENCE_V2): generation + repair prompts
  carry the exact required header (`always_ff @(posedge clk)` / async form);
  `sensitivity_mismatch` (mirrors Gate-1 regexes exactly, comments
  stripped, neutral without reset) rejects mismatches pre-EDA as
  REPAIR_SENSITIVITY_MISMATCH with the header in feedback. Flag-0 prompts
  byte-identical (proven). Real bug fixed en route: `required_*` defaulted
  like Gate 1 (clk/posedge) instead of None for clockless contracts.
- Failure-report reselection (flag ON only): the driver used
  `gate_reports[-1]`, which after a Gate-2 failure is a DFT `NOT_RUN` stub
  (verify keeps running advisory Gate 6/DFT). Now reselects the last failed
  non-NOT_RUN report, so repair evidence carries real
  property/step/trace/cycle. Legacy flag-off path untouched; dead
  `lower_category` removed. Live-proven: seed-43 rerun emits sync RTL,
  reaches Gate 2, repair guidance carries the decoded table + cycle 2.
- Tests (10, fast): header sync/async/no-clock, both mismatch directions,
  comment/neutral cases, prompt off/on identity, mocked-driver pre-EDA
  rejection. Fast suite 459 green.

## Phase 2B dataset miner (committed: scripts/distill_mind3_dataset.py,
## tests/test_distill_dataset.py; dataset untracked at results/v4/runs/distilled/)
- `MIND3_EVIDENCE_V2` forced ON in-process; every prompt uses the flag-ON
  pipeline (sensitivity header + NOT_RUN reselection + R5 decoded table).
- `--from-soundness`: all 23 mutants verified live -> 23 SFT (ChatML
  system/user/assistant) + 23 DPO (prompt/chosen/rejected/error_category/
  failing_gate). `--from-transcripts`: 5 workspaces -> 8 DPO + 0 SFT.
- Guards (fail fast): sealed-suite path components, holdout-ONLY task IDs
  (dev-20 IDs are a subset of holdout IDs with identical specs — a bare
  ID block would refuse every dev run), mock/unknown providers, sha256
  triple dedup shared across modes (single merged write + manifest).
- Substring guard corrected to path components after it false-positived on
  the dev family `fsm_heldout_04`. Transcript guidance aligned to
  repair_attempts[i] <-> VERIFY#(i+1). Transcript failing gates labeled by
  deterministic category->gate map.
- `build_miner_evidence` mirrors the driver (stage map, tool default,
  decode); cross-check test runs the real driver loop and asserts evidence
  equality on all fields but repair_history.
- Miner tests (11, fast): guards, overlap documentation, decode against the
  real VCD fixture, parity, harvest/dedup/blocking on synthetic workspaces.
  Mined output verified: 23 SFT + 31 DPO, exact schemas, all chosen golden,
  gates Gate2x20/Gate3x8/Gate1x3, decoded table in 15/31.

## R5.1 witness->contract property mapper + same-cycle latency hint (committed)
- `formal_templates.py`: `resolve_witness_property` maps a SymbiYosys witness
  name (`check_assert_<stem>_sva_sv_<line>_<col>`) to the rendered contract
  property name via the nearest `// [MIND3-TEMPLATE:<kind>] <name>` marker
  above the assert line (None on non-witness/out-of-range/no-marker; caller
  keeps the legacy uncertain path). `contract_property_source` restates a
  named contract property deterministically from the typed spec
  (`|->` / `|=>` / expression / `$onehot`, etc.; legacy SVA verbatim) —
  never invented.
- `verifier.py` attaches `mapped_property`; `driver.py` repair loop and
  `distill_mind3_dataset.py` miner prefer it over the raw witness name and
  restate `failing_assertion` as `<name>: <source>` (miner prompts stay
  byte-identical to loop prompts, incl. the latency hint).
- `vcd_evidence.py`: sensitivity-guard text clarifies the sequential hint is
  conditional — same-cycle outputs stay combinational (`assign`/`always_comb`);
  `latency_hint_for_repair` helper gates the hint on contract+RTL.
- Tests (fast, no EDA/Ollama): `test_r5_evidence_v2.py` mapper/source-table
  cases, `test_repair_sensitivity_guard.py` hint cases, `test_distill_dataset.py`
  miner parity. `pytest` on the three files: 40 green.
