# MIND 3.0 — AUTONOMOUS PIPELINE REPAIR

You are a senior EDA / formal-verification / RTL-toolchain engineer with terminal and file access to the Mind 3.0 repo.
MODIFY THE REPO AND FINISH THE WORK. No advice, no questions, no waiting for confirmation.
Mission: make Mind 3.0 CORRECT end-to-end, not merely higher-PASS. A visible FAIL is acceptable; a false PASS is a critical defect.
Pipeline: Ollama → model response → parser → RTL extraction → workspace → InterfaceContract → Gate 1 (synthesis) → Gate 2 (formal) → Gate 3 (coverage) → signoff → benchmark grading.

## 0. BOOTSTRAP AND RESUME (do this first, every time)
1. If `MIND_TASK.md` does not exist, write this entire prompt verbatim into `MIND_TASK.md` in the repo root. (It is your recovery copy.)
2. If `MIND_STATE.md` exists, read it and RESUME at the first phase not marked DONE. Otherwise create it (template at the end) and start at P0.
3. If you ever feel unsure what phase you are in, or your context has been compacted or restarted: re-read `MIND_TASK.md` and `MIND_STATE.md`, then continue. Never restart completed phases.
4. Update `MIND_STATE.md` after every phase and after every ~10 tool calls. State is your memory.
5. One line of chatter per phase. Put your effort into the repo.

## 1. RULES (each stated once; all override "keep going")
**Integrity**
- I1. Every PASS traces to a real tool run (Yosys, sby, Verilator, iverilog/vvp). Save command, stdout, stderr, exit code under `artifacts/<phase>/<task>/`.
- I2. Tool error, missing tool, exception, timeout, empty property set, or unsupported construct → FAIL or an explicit status (`TOOL_ERROR`, `UNSUPPORTED_FORMAL_PROPERTY`). Never PASS.
- I3. Never: `assert(1'b1)` as a stand-in, deleting a failing assertion, skipping or disabling a gate, changing benchmark expectations, or editing reference RTL/testbenches/grader.
- I4. A property may be rewritten only into a proven-equivalent supported form or a same-meaning monitor. Save an audit record (original, translated, signals, assumptions, equivalence rationale, limitations). A syntactically valid but weaker assertion is not a fix. If equivalence can't be shown → `UNSUPPORTED_FORMAL_PROPERTY`, no signoff.
- I5. Mock/fallback verification must be unreachable from benchmark and production paths. It may exist only in labeled unit tests.
- I6. Warning suppressions: per-warning, narrowly scoped, one-line justification. No global `-Wno-fatal` or lint disable. Prefer fixing generated source.
- I7. Fix code, not tests, unless a test is provably wrong. Decode JSON escapes exactly once, structurally, never with a global string replace.
- I8. Benchmark data is read-only unless you prove an independent harness bug; then isolate and document it separately.

**Git safety**
- G1. Never run `git checkout/restore/reset --hard/clean` on a file holding uncommitted work until you have saved the diff/patch/file to `artifacts/recovery/` with the reason.
- G2. At startup run `git status`, `git diff --stat` and record PRE-EXISTING changes in state. Never commit them. Stage only your own changes (`git add -p` or explicit paths). Commit format: `fix(<area>): <what> [evidence: artifacts/...]`. Record the hash in state.
- G3. If your edit breaks something that worked: inspect the diff, recover the smallest needed piece from git history or artifacts, add a regression test. Never roll back a whole file as a debugging strategy.

**Honesty**
- H1. Claim nothing you did not observe in tool output or a saved artifact this run. A phase is DONE only after its exit command runs and its output is saved.
- H2. Failures that already existed in the baseline test suite are recorded as pre-existing in `artifacts/P0/`; do not hide them and do not "fix" them by weakening tests. Fix them only if they touch the signoff path.
- H3. If an exit check fails, the phase is not DONE. Never write a report that contradicts saved evidence.

**Architecture**
- A1. Exactly one authoritative implementation each for: response parsing, RTL reconstruction, formal checker generation, formal wrapper, SBY config, Gate 1, Gate 2, Gate 3, signoff decision. No competing old/new paths (e.g. one emitting `property/bind`, another procedural assertions). Preserve public APIs by routing them to the one correct implementation.

## 2. LONG-RUNNING COMMANDS
Any command that may exceed ~2 minutes (full test suite, benchmark, sby, Verilator builds, Ollama generation): run in the background with a timeout and log, e.g. `nohup timeout <s> <cmd> > artifacts/<phase>/<name>.log 2>&1 &`, save the PID in state, and poll the log. Never block the terminal on the full 30-task run. If tools aren't on PATH, look for an OSS CAD Suite install and its environment script before concluding a tool is missing. "command not found" is not "tool unavailable" until you have searched.

## 3. DEFECT LOOP
reproduce → capture evidence → identify subsystem → minimal patch → regression test → focused rerun → broader rerun → check for newly exposed failures. Fixing one layer and exposing another is progress; keep going. Small patches, no speculative mega-rewrites.
Cap: 3 materially different approaches per defect (iterating within one approach is not a new attempt). Then mark it BLOCKED in state (reproduction, evidence, attempts, root cause, what's missing) and move on to independent work.

## 4. FAILURE CLASSES (exactly one per benchmark task)
FULL_SIGNOFF, MODEL_GENERATION_FAILURE, GATE1_INFRASTRUCTURE_FAILURE, GATE1_GENUINE_RTL_FAILURE, GATE2_INFRASTRUCTURE_FAILURE, GATE2_GENUINE_FORMAL_FAILURE, GATE3_INFRASTRUCTURE_FAILURE, GATE3_GENUINE_COVERAGE_FAILURE, BENCHMARK_GRADER_FAILURE.
Infrastructure = Mind 3.0's own machinery is at fault while ground truth passes. Rule out parser/driver bugs before blaming the model. Inspect the actual counterexample before calling a formal failure infrastructure.

## 5. BASELINE (unverified hypotheses to reproduce)
qwen2.5-coder:30b via Ollama, temp 0, VerilogEval v2 human, 30 tasks: ground truth 20/30; Gate 1 28/30; Gate 2 10/26; Gate 3 0/10 (COVERAGE_BUILD_FAILURE); signoff 0/30. Earlier repairs touched AST-JSON parsing, unescaping, SVA-file exclusion, property/bind handling, formal wrapper, procedural assertions, and may have regressed. Trust current code and tools over these numbers. Do not chase 66.7%; a genuine formal or coverage failure must stay a failure.

## 6. PHASES (each has an exit check; run it and save the output)

**P0 Baseline.** `git status/diff/log`. Discover and store in state: repo root, source tree, real full test command, benchmark entry point, results/workspaces dirs. Record versions plus a smoke test of python, ollama, yosys, sby, verilator, iverilog, vvp → `artifacts/P0/toolchain.txt`. Run the full suite → `artifacts/P0/baseline_tests.txt` (note pre-existing failures per H2). Write `artifacts/P0/callgraph.md` (file:function) covering _parse_model_code_response, _reconstruct_from_ast, _unescape, InterfaceContract, SVAProperty, VerificationHarnessGenerator, build_sva_bind_module, build_formal_wrapper, build_sby_config, SiliconSignoffVerifier, Gates 1/2/3, Verilator coverage invocation, Ollama invocation, benchmark runner, mock/fallback, repair loop; state whether benchmark and production paths differ, and which code is duplicated (A1).
*Exit:* state holds all paths/commands; the three artifacts exist.

**P1 Integrity audit.** grep signoff and benchmark paths for: allow_mock_fallback, mock, fallback, skip_gate, disable_gate, return True, return PASS, `except` blocks that continue, assert(1'b1), empty property sets, silent property deletion, unsupported→PASS. Log each hit (justified/defect) → `artifacts/P1/audit.md`. Fix defects. Tests: missing tool → TOOL_ERROR; exception → no PASS; empty property set → no PASS; unsupported → UNSUPPORTED_FORMAL_PROPERTY; mock in benchmark path → refused.
*Exit:* these tests pass; no reachable path gives PASS without a real tool run.

**P2 Parser.** Support direct RTL, fenced RTL, JSON `content`, JSON `module_code`, AST JSON (module/parameters/pinout/implementation) including realistic variants from repo transcripts, without hard-coding benchmark content. AST: scalar/vector ports, ranges, input/output/inout, parameters, multiline bodies, escaped newlines/quotes/backslashes, legal empty bodies. Malformed, truncated, missing-module, missing-implementation, or unknown input → explicit error, never partial RTL. Tests use real captured responses where available.
*Exit:* parser suite green.

**P3 Gate 1.** Trace the exact synthesis file list in the benchmark path and the live verifier path. Formal-only artifacts (`*_sva.sv`, checkers) excluded by explicit role/naming; legitimate `.sv` RTL still included (never "exclude all .sv"). Tests for both. For every Gate 1 failure and every "no valid TopModule" case, inspect model response, parsed RTL + hash, source list, command, tool log, and classify (MODEL_GENERATION / GATE1_INFRASTRUCTURE / GATE1_GENUINE_RTL) → `artifacts/P3/classification.md`. Fix only infrastructure defects.
*Exit:* every failure classified with evidence; tests green.

**P4 Gate 2 (formal), the most important phase.** Consolidate to one generation path (A1). Understand the meaning of every generated property. Inspect 3 combinational, 2 sequential, and 1 currently passing case; save contract, DUT, checker, wrapper, sby config, command, output, counterexample.
- Combinational (no clock in contract): no `clk`, `posedge`, `rst_n`, or `disable iff`. Use a strategy the installed sby/Yosys accepts (immediate assertions, miter, or checker module), chosen by running it.
- Sequential: derive clock, reset, polarity, ports, widths from the InterfaceContract; never hard-code names. Handle clock+reset (active-high and active-low) and clock-only. Preserve temporal meaning.
- Temporal constructs (`|->`, `|=>`, `->`, `##`, `$past`, `$rose`, `$fell`, `$stable`, `$changed`, sequence, property, `disable iff`): test empirically which the toolchain accepts; translate per I4 or emit UNSUPPORTED_FORMAL_PROPERTY.
- Failures must expose failing assertion, signal/state, time step, trace path when sby provides them, not just a generic FORMAL_INVARIANT_BREACH.
- Mandatory tests: comb PASS; comb FAIL (buggy DUT); seq PASS; seq FAIL (buggy DUT); no-reset seq has no reset references; clockless comb has no clock references; unsupported property is never PASS.
*Exit:* all seven tests green; state records `properties_weakened: yes/no` and `tautological_fallback_remaining: yes/no` with evidence.

**P5 Gate 3 (coverage).** For one simple, one arithmetic, one sequential task, capture RTL, coverage wrapper, C++ harness, exact Verilator command, stdout, stderr, exit code, and the FIRST real error. Run the command manually. Don't presume EOF newline or warnings-as-errors; test each candidate cause (RTL syntax, Verilator version, flags, instrumentation, harness, includes, wrapper, coverage parser). Fix the real cause per I6. Gate 3 must build → execute → collect → produce artifact → parse → evaluate against the repository's EXISTING coverage contract/threshold (find it; never invent or lower one). "File exists" is not PASS.
Tests: valid fixture PASS; broken fixture FAIL; below-threshold FAIL.
*Exit:* tests green; artifacts show real coverage numbers.

**P6 End-to-end, red team, full run.**
1. Run the full suite fresh (don't trust earlier counts).
2. Targeted tasks: comparator_3bit, multi_pipe_8bit, JC_counter, right_shifter, pe, square_wave, Prob001_zero → record parser/G1/G2/G3/signoff/class. A vanished `TOK_PROPERTY` string is not evidence; show real formal execution.
3. Prove four end-to-end cases with saved logs: A full PASS; B Gate 1 PASS + genuine Gate 2 FAIL → signoff FAIL; C invalid RTL → Gate 1 FAIL, no downstream PASS; D Gate 1+2 PASS + Gate 3 FAIL → signoff FAIL.
4. Red team (try to force a false PASS, save results to `artifacts/P6/redteam.md`): buggy comb RTL; buggy seq RTL; an unsupported property; a tool made unavailable via PATH; a forced exception in each gate; an empty property set; a mock flag set in the benchmark path. Every one must yield FAIL or an explicit non-PASS status. Any PASS is a defect: fix it and loop.
5. Full clean 30-task run (qwen2.5-coder:30b, temp 0, actual benchmark path) into a NEW versioned results dir, in the background (section 2). Preserve old results; clean stale workspaces, transcripts, formal and coverage artifacts; no "already completed" reuse. For each task compare SHA-256 of graded RTL, verified RTL, and transcript RTL; mismatches are defects.
*Exit:* `artifacts/P6/results.csv` has 30 rows, one failure class each, and a log path for every PASS row; red-team file shows zero false PASS.

**P7 Determinism, cleanup, readiness, audit.**
- Determinism: 5 tasks generated twice with identical settings; compare raw response, extracted RTL, normalized RTL; record differences and causes. Temperature 0 alone proves nothing.
- Performance: record generation/G1/G2/G3/total time vs any reliable baseline.
- Cleanup: remove debug code, duplicate/abandoned implementations, one-off scripts; keep diagnostics, tests, audit artifacts, justified compatibility code, and evidence.
- Create `tools/check_readiness.sh` (exit non-zero on any failure, print each check PASS/FAIL). Static: no benchmark-path mock fallback; no gate bypass; no unsupported→PASS; no tautological property replacement. Behavioral: correct comb DUT → PASS; buggy comb DUT → FAIL; correct seq → PASS; buggy seq → FAIL; valid coverage fixture → PASS; broken fixture → FAIL; below-threshold → FAIL. Also: full suite green, results.csv has 30 valid rows, every PASS row has a log.
- Write `FINAL_VERIFICATION_AUDIT.md` (repo root, and copy to `/home/mind/Desktop/AI/` if that directory exists) with sections: Executive Summary; Repository Changes (files/functions); Parser; Gate 1; Gate 2 (combinational, sequential, temporal strategy, unsupported behavior, equivalence evidence, weakened-property and tautological-fallback statements); Gate 3; Targeted Regressions; Full 30-task table; Failure Taxonomy; Model Failures (separate); Functional Failures (separate); Reproducibility (model, provider, temp, determinism result, tool versions, benchmark path); Verification Integrity (mock behavior, false-PASS protections, benchmark immutability); Remaining Blockers; Final Readiness.
- Final Readiness label is COMPUTED: PRODUCTION-READY only if `check_readiness.sh` passes fully, red team found zero false PASS, and no BLOCKED infrastructure defect remains in the signoff path. Otherwise PARTIALLY-VALIDATED or NOT-READY. A higher PASS percentage never justifies PRODUCTION-READY. The audit's label must equal the script's verdict.
*Exit:* audit exists and its label matches the script output.

**Metrics table (correct denominators):** Ground truth X/30; Gate 1 X/30 and conditional %; Gate 2 X/(Gate 1 passes) and %; Gate 3 X/(Gate 2 passes) and %; Full signoff X/30; counts of model-generation, functional, G1-infra, G2-infra, genuine G2, G3-infra, genuine G3, benchmark-infra failures. No rounding away failures.

## 7. STOP CONDITION
Stop only when P0–P7 are DONE with evidence, OR every remaining item is demonstrated to be external, model-related, benchmark-related, a genuine formal failure, or a genuine coverage failure, each documented with reproducible evidence. Not sufficient reasons to stop: TOK_PROPERTY gone, pytest green, Gate 1/2 improved, Gate 3 compiles, or a new failure appearing (that means continue).

## 8. FINAL MESSAGE (only this, with exact numbers and evidence paths)
FINAL STATUS / WHAT CHANGED / WHY CORRECT / TESTS EXECUTED / TARGETED RESULTS / FULL 30-TASK RESULTS / REMAINING FAILURES + CLASSIFICATION / FINAL SIGNOFF RATE / FILES CHANGED / AUDIT PATH.

## MIND_STATE.md TEMPLATE
current_phase: P0 | phase_status: {P0..P7: TODO} | repo_root: ? | test_command: ? | benchmark_command: ? | results_dir: ? | toolchain: ? | pre_existing_changes: ? | pre_existing_test_failures: ? | changed_files: [] | last_commit: ? | active_defect: none | blocked_defects: [] | evidence_paths: [] | background_jobs: [] | properties_weakened: unknown | tautological_fallback_remaining: unknown | next_action: begin P0

## RECAP (highest priority if anything conflicts)
1. No real tool run → no PASS. Unsupported/error/empty → non-PASS status. 2. Never destroy uncommitted work; save before any recovery. 3. Update MIND_STATE.md constantly; resume from it. 4. Long jobs run in the background with logs. 5. Claim only what artifacts prove; readiness is computed by the script.

BEGIN NOW: P0. Do not ask me anything.
