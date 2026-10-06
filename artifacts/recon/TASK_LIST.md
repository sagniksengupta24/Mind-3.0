# TASK LIST (read-only recon pass, 2026-10-06; nothing modified outside artifacts/recon/, nothing fixed)
Source of truth for verdicts below: files I read this pass. Prior-session claims were re-checked;
corrections are marked CORRECTION. Order: false-PASS risks first, then Gate 2 infra, Gate 3 infra,
parser, Gate 1, data-quality/provenance, cleanup.
Most recent benchmark results directory: artifacts/stage22_fresh_30b/ (10 real transcripts,
qwen2.5-coder:30b, strict parser, 2026-10-05T18:59:08Z) + per-turn gate evidence in
artifacts/stage22_fresh_30b/run_workspaces/<task>/.mind/transcript.jsonl.
Observed gate order: Gate 1 -> Gate 3 -> Gate 2 -> Gate 4 -> Gate 5(opt-out) -> Gate 6.

## R1 | phase P1 | subsystem Gate 4 timing parser | file src/mind3/core/verifier.py:2409 (wns None->FAIL), :2505-2524 (unconditional PASS), parse_opensta_timing :294-348, parse_opensta_mcmm :390-460
- Observed evidence: code read this pass. `parse_opensta_timing` regex `\bwns\s*[:=]?\s*<num>` matches a bare `wns 0.00` line, so IF OpenSTA emits `No paths found.` + `wns 0.00`, setup_wns=0.0 (not None) and the gate returns `passed=True`, details `Timing closure confirmed: setup WNS = 0.000 ns` (artifacts/recon/toolchain.txt, artifacts/recon/repo_state.txt for code context).
- Failure class: FULL_SIGNOFF (vacuous timing PASS on zero timed paths) - INFERRED impact.
- Proposed minimal fix: treat `No paths found` / zero reported paths as a distinct vacuous verdict (fail or explicit VACUOUS flag), never `Timing closure confirmed`.
- Regression test to add: feed a `No paths found / wns 0.00` log to `_run_gate4_timing` with a stub runner; assert `passed is False` (or vacuous flag set).
- Severity: CRITICAL-candidate (can cause a false PASS). Confidence: INFERRED - CORRECTION: the firing artifact cited by a prior draft (`No paths found` in an executed run) was NOT OBSERVED by me; grep over artifacts/, results/, tests/ finds that string only in the prior draft itself. Mechanism is OBSERVED, impact is not. Confirming evidence: a fixture with no timed paths run through Gate 4.
- Related live watch: counter_01 Gate 4 passed all 4 turns with exactly `setup WNS = 0.000 ns` (artifacts/recon/results_snapshot.csv, run_workspaces/counter_01/.mind/transcript.jsonl) - MET, but exact-zero; see R10.

## R2 | phase P1 | subsystem Gate 3 coverage parser | file src/mind3/core/verifier.py:505-513 (parse_coverage_dat_file)
- Observed evidence: code read this pass: `elif cat == "branch" and "line" in counts: result["branch"] = line%` - line coverage substituted for branch coverage when branch data is absent.
- Failure class: GATE3_GENUINE_COVERAGE_FAILURE masked as pass (INFERRED impact).
- Proposed minimal fix: report branch as None/unmeasurable instead of substituting line values (fail closed per Rule I2 path already used for missing coverage).
- Regression test to add: coverage.dat with line-only hits through Gate 3 must yield branch=None, never a pass-driving number.
- Severity: CRITICAL-candidate (can inflate a pass metric). Confidence: OBSERVED code, INFERRED impact - confirming evidence: crafted line-only coverage.dat through Gate 3 (not executed; beyond read-only scope).

## R3 | phase P1 | subsystem Gate 2 vacuity | file src/mind3/core/verifier.py:1736 (_run_gate2_vacuity_check)
- Observed evidence: passing Gate 2 reports quote `details: Bounded BMC to depth 25: zero invariant counterexamples. Vacuity assessment: user-supplied harness; antecedent exercise not assessed.` with `passed: True` - seen live in run_workspaces/counter_01/.mind/transcript.jsonl (4 turns) and the stage22 counter_04/counter_09 transcripts.
- Failure class: GATE2_GENUINE_FORMAL_FAILURE possibly masked (unreachable antecedents unassessed).
- Proposed minimal fix: when vacuity is NOT_APPLICABLE, either assess antecedents on the generated harness or mark the pass explicitly vacuity-unassessed (never silently equivalent to a fully-vacuous-checked pass).
- Regression test to add: property with unreachable antecedent through Gate 2 must not yield a clean PASS.
- Severity: CRITICAL-candidate. Confidence: OBSERVED gate text, INFERRED impact - confirming evidence: false-antecedent probe design through Gate 2.

## R4 | phase P4 | subsystem Gate 1 latch list | file src/mind3/core/verifier.py (structured AST latch check; `$dffsr`/`$sr` membership)
- Observed evidence: code observed; no firing case in any artifact (all recorded LATCH_INFERRED cases match `$dlatch` chatter or true latches).
- Failure class: GATE1_INFRASTRUCTURE_FAILURE (false-FAIL direction, not false PASS).
- Proposed minimal fix: none until a probe with async set/reset flops demonstrates misclassification.
- Regression test to add: `$dffsr`-only netlist through Gate 1, expecting PASS.
- Severity: major (false FAIL). Confidence: INFERRED - confirming evidence: set/reset-flop probe design through Gate 1.

## R5 | phase P4 | subsystem RTLVerifier source scan | file src/mind3/core/verifier.py:96-103 (rglob) vs :925-948 (discover_rtl_sources, top-level only)
- Observed evidence: code read this pass. Sibling RTLVerifier collects `sorted(resolved_ws.rglob("*.v"))` / `rglob("*.sv")` while the signoff path uses top-level-only `discover_rtl_sources()` (fix for SBY `<top>/src/` copies poisoning recompiles). Same nested-copy hazard exists in RTLVerifier.
- Failure class: GATE1_INFRASTRUCTURE_FAILURE (false-FAIL direction via duplicate modules).
- Proposed minimal fix: reuse `discover_rtl_sources()` in RTLVerifier.
- Regression test to add: workspace with nested tool-copy + root file; assert file list excludes the copy.
- Severity: major. Confidence: INFERRED impact (same mechanism, different entry point; no firing case observed).

## R6 | phase P7 | subsystem docs | files docs/cdc_gate6.md:66-69 vs README.md:30,109
- Observed evidence: grep this pass. docs/cdc_gate6.md documents the rtl-buddy-cdc fallback engine; README Gate 6 lines still describe Yosys-only behavior / fail-closed-on-missing-CDC.
- Failure class: cleanup (no verdict impact).
- Proposed minimal fix: one-paragraph fallback note in README (or pointer to docs/cdc_gate6.md).
- Severity: low. Confidence: OBSERVED.

## R7 | phase P0 | subsystem recon data quality (no code impact) | file artifacts/recon/results_snapshot.csv (REGENERATED this pass)
- Observed evidence: CORRECTION - the snapshot written by the concurrent 00:44 pass contradicts primary records: (a) counter_10 row said CDC_VIOLATION, but transcript JSON (`gate_failure_category: COVERAGE_DEFICIT`), stage23 record (`COVERAGE_DEFICIT branch=75.0%/toggle=20.0%`), and .mind transcript (4 turns, all Gate 3 COVERAGE_DEFICIT, downstream NOT_RUN) all agree on COVERAGE_DEFICIT; (b) counter_01 `repair_cats` claimed FORMAL_INVARIANT_BREACH turns + `T=4 formal breach` error text, but .mind transcript shows all turns CDC_VIOLATION with Gate 2 PASS every turn. I regenerated the CSV from .mind/transcript.jsonl per-turn gate reports (final turn per task).
- Failure class: none (recon artifact, not product). Regenerated file: artifacts/recon/results_snapshot.csv (columns task,final_status,Gate1,Gate3,Gate2,Gate4,Gate6,signoff,first_failing_gate,error_text,evidence_path).
- Regression test to add: n/a (process fix: cross-check snapshots against .mind transcripts before publishing).
- Severity: medium (wrong triage input). Confidence: OBSERVED.

## R8 | phase P1 | subsystem Gate 2 evidence provenance | dir artifacts/recon/evidence/gate2_counter_08_pass/
- Observed evidence: sha256 of staged `counter_08.sv` (b476dc9d...) != sha256 of the benchmark graded RTL in artifacts/stage22_fresh_30b/transcripts/counter_08.json `generated_rtl` (fe3ed01c...), both hashed this pass. The staged sby run (00:45, `DONE (PASS, rc=0)`) therefore does NOT disposition the graded RTL that failed formal (T=3 breach) in the benchmark. Same SHA check not yet done for the other evidence dirs.
- Failure class: none (evidence hygiene). Counter_08 benchmark verdict stays GATE2_GENUINE_FORMAL_FAILURE (INFERRED - counterexample trace not inspected this pass).
- Proposed minimal fix: restage evidence from graded RTL (or label exactly which repair-turn RTL is staged); add SHA-equality check between staged DUT and graded/transcript RTL.
- Regression test to add: evidence-packing script asserts staged DUT SHA == transcript RTL SHA.
- Severity: major (a PASS on ungraded RTL could mislead triage). Confidence: OBSERVED.

## R9 | phase P1 | subsystem Gate 6 CDC engine vs single-clock RTL | files run_workspaces/counter_01,02,03,07 .mind transcripts; contracts async_inputs=null
- Observed evidence: counter_01/02/03/07 (single-clock synchronous counters; contracts declare `async_inputs: null`) fail all turns at Gate 6 with `CDC analysis detected N unregistered clock-domain crossing(s) (rtl-buddy-cdc engine)` while Gates 1/3/2/4 all PASS (e.g. counter_01: G1 clean, G3 100%/100%, G2 BMC pass depth 25, G4 WNS 0.000). Genuineness of the reported crossings vs engine false-positive is undetermined read-only (rbcdc JSON report not located in run_workspaces; only .mind snapshots + transcript.jsonl survive for failed tasks since workspaces roll back).
- Failure class: UNRESOLVED - candidates: MODEL_GENERATION_FAILURE (if RTL really has async crossings) vs BENCHMARK_GRADER_FAILURE/Gate-infra (if engine flags single-clock sync logic). The P0-P7 taxonomy has no CDC class; do not force-fit.
- Proposed minimal fix: none yet. Next step: recover the rbcdc report (re-run Gate 6 only on the preserved snapshots) and inspect the named crossing instances against the RTL.
- Regression test to add: single-clock sync counter fixture through Gate 6 expecting PASS (if engine is at fault) - or keep failing if RTL is genuinely crossing.
- Severity: major (4/10 benchmark tasks; blocks signoff either way). Confidence: OBSERVED verdicts, INFERRED cause - confirming evidence: rbcdc per-instance report + RTL inspection.

## R10 | phase P1 | subsystem Gate 4 exact-zero slack | file run_workspaces/counter_01/.mind/transcript.jsonl
- Observed evidence: counter_01 Gate 4 `Timing closure confirmed: setup WNS = 0.000 ns` on all turns (threshold behavior at exactly zero; max_wns_ps comparison not traced this pass).
- Failure class: none filed (MET, not violated). Watch-item for R1: exact-zero passes deserve the same vacuity scrutiny as `No paths found`.
- Proposed minimal fix: none (log only; consider recording the threshold comparison inputs in the gate report).
- Severity: low. Confidence: OBSERVED text, INFERRED significance.

## Per-task failure classes (stage22, from regenerated snapshot; genuine-vs-infra split where evidence allows)
- counter_04, counter_09: FULL_SIGNOFF (all gates PASS incl. Gate 6; artifacts/stage22_fresh_30b/transcripts/counter_04.json, counter_09.json). Confidence: OBSERVED.
- counter_05, counter_06, counter_08: first failure Gate 2 FORMAL_INVARIANT_BREACH (T=9 / T=3 / T=3; stage23 records + transcripts). Class: GATE2_GENUINE_FORMAL_FAILURE suspected - INFERRED (counterexample traces not inspected; counter_05 also matches independent Stage-16 forensics `wrong algorithm: window-timing logic absent`). Confirming evidence: sby trace.vcd inspection per task.
- counter_10: first failure Gate 3 COVERAGE_DEFICIT (branch 75.0%/toggle 20.0% vs 95%/90%; all turns; downstream NOT_RUN). Class: GATE3_GENUINE_COVERAGE_FAILURE suspected - INFERRED (thin auto-stimulus contribution not separated from RTL cause). Confirming evidence: coverage.dat uncovered-point review.
- counter_01, counter_02, counter_03, counter_07: first failure Gate 6 CDC_VIOLATION (Gates 1/3/2/4 PASS). Class: UNRESOLVED per R9 (no CDC class in taxonomy; genuineness undetermined).
- Ground-truth functional correctness independent of gates: NOT OBSERVED (no independent oracle run this pass); 2/10 full signoff, 0/8 repaired-to-pass.

## Explicitly NOT items (checked this pass, nothing to file)
- allow_mock_fallback paths (verifier.py:1376/1476/1613/1656/1924/2149/2279/2370/2639/2853/2901/2962): every branch returns labelled SIMULATED (`[SIMULATED - NOT REAL TOOL OUTPUT]`, simulated=True) or fails closed; all live call sites pass False (driver.py:1720, baselines.py:184/453, runner.py:373). SAFE.
- `return True` hits (verifier.py:859 helper, :2720-2728 CDC-requirement decision+reason, release.py:89 bundle message, driver.py:1411/1838 post-pass-through, contracts.py:859 temporal predicate): none is a gate verdict. SAFE.
- skip_gate symbol: absent from src; skips exist only as labelled SKIPPED/NOT_RUN reports. SAFE.
- Bare except/except-continue (verifier.py:473,920,1414,1538; driver.py:224,477,492,513): all fail closed (None->error, missing->label, unavailable->False). SAFE.
- assert(1'b1)/trivially-true assertions: none in src. SAFE.
- Empty formal property set (verifier.py:1852-1862): explicit FAIL `EMPTY_FORMAL_PROPERTY_SET`. SAFE.
- Unsupported property (verifier.py:1870-1884 -> UNSUPPORTED_FORMAL_PROPERTY FAIL; :1952 TOK_PROPERTY/unsupported/syntax-error -> FAIL): fail closed. SAFE.
- Tool-error/timeout/exception->PASS: none observed; all error branches return passed=False with named categories. SAFE.
- Parser P2 behaviors (fenced/direct/AST/malformed): NOT re-proven this pass (suite not executed per read-only scope); existing tests at tests/test_p2_parser.py listed, not run. No parser item filed.
- Combinational Gate 2 cases: NOT OBSERVED (all 10 stage22 tasks are sequential counters; negative_controls/ has combinational RTL but no stage22-grade Gate 2 evidence was staged for them). No false claim made.
- 30-task VerilogEval run (MIND_TASK P6 baseline qwen2.5-coder:30b temp 0): NOT OBSERVED (only 10-task stage22 diagnostic exists). Not re-run per instructions.
