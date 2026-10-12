# C3 Diagnosis — Generator Recovery (qwen2.5-coder:7b, model unchanged)

## C2 probe results (live, Ollama 0.31.1, 2026-10-07)

- `format=json` (pipeline historical default) → model emits
  `{ "response": "module ok; endmodule" }`. Under strict parsing this is
  `RESPONSE_PARSE_FAILURE` (not WriteFileAction, not fenced, not one module)
  **even though the model complied with the prompt**. H1 SUPPORTED as the
  primary mechanism: the pipeline forces JSON, then rejects JSON-shaped output.
- No `format` (Track F setting) → clean `module ok; endmodule`. The model is
  perfectly capable of bare-module output when not coerced into JSON.
- JSON-schema `format` (Track J setting) → schema-valid WriteFileAction on
  the first try. Track J is feasible on this Ollama version.
- Stop sequences STRIP the stop token from output (`endmodule` removed).
  Rule confirmed: never stop at the first `endmodule`; no stops are used.
- Decode plumbing verified: `temperature/seed/num_predict/num_ctx` accepted,
  `prompt_eval_count`/`eval_count` returned on every call.

R0 CLAIM REACHED: failures are mostly pipeline-made. The 19/20 Stage-6
`RESPONSE_PARSE_FAILURE` rate is explained by the format coercion, not by
model inability — probe 2 shows the same model emitting clean modules.

## Shape classification (pilot: 5 tasks × seed 42, legacy prompt + format json)

Artefacts: `artifacts/exp_c3_pilot/` (report + `shapes.md`).

- First-raw shapes: 2× json-other-shape (metadata `display_name/description`,
  no RTL), 1× AST-dict (`module/ports/internal_signals`, no implementation),
  1× empty-initial-transport-failure (initial call raised; repairs proceeded),
  1× empty-no-model-call (`arbiter_02`: CONTRACT_CONSISTENCY_FAILURE at
  stage 0 — spec-side, the local analogue of the Stage-6 SPECIFICATION_ERROR).
- Strict parse: 0/5 pass@1, 0/5 with-retry. Repairs re-emit port-list JSON
  (`module_name/ports`, no implementation); one task degraded across retries
  into `{"response": "module top; $display Hello World"}` — repeated
  format-nags can degrade output. Watch item for C6 evaluation.
- No output truncation, no prompt overflow on pilot (H2/H3 still open
  pending full runs, but not firing here).
- H1 further SUPPORTED: under free-form JSON the model free-associates
  metadata shapes. Free-form JSON is the worst of both worlds — motivates
  Track J (schema) vs Track F (no JSON) directly.
- Off-by-one fixed during pilot: parse budget is now pre-checked before
  each repair MODEL_CALL, so total parse attempts ≤ PARSE_MAX_ATTEMPTS (3)
  exactly; parse failures never consume EDA stage turns (verified in code,
  transcript accounting pending full runs).

## Hypothesis status
- H1 (json-format conflict): SUPPORTED (probe).
- H2 (prompt truncation): OPEN — needs prompt_eval_count vs num_ctx from runs.
- H3 (output truncation): OPEN — needs eval_count vs num_predict from runs.
- H4 (sanitizer/regex rejects valid output): OPEN — replay fixtures say the
  documented shapes behave; live raws will confirm or refute.
- H5 (parse burns EDA budget): SUPPORTED historically (fifo_01); C6 fix in
  place, verified by transcript budget accounting after reruns.
- H6 (repair prompt has no format discipline): SUPPORTED by code inspection;
  C5 format blocks added, effect measured in tracks.
- H7 (template misconfiguration): REFUTED as a blocker — default ChatML
  template observed, probes comply with format instructions.
- H8 (interface mismatch post-parse): OPEN — funnel stage reports after runs.

### Full C3 baseline seed 42 (done 2026-10-07)
`artifacts/exp_c3_baseline_s42/` — reproduces Stage 6 exactly: 0/20 strict
parse pass@1, 0/20 with-retry, 0/20 sim, 0/20 full-verified
(Wilson95 [0%, 16.1%]). 19 RESPONSE_PARSE_FAILURE + 1 SPEC (arbiter_02).

- First-raw shapes: 15× json-other-shape, 4× other-json-broken (incl.
  filename-keyed JSON and AST-dicts), 1× empty-no-model-call.
- H3 FIRES on 2/20 (arbiter_03, fsm_heldout_04 output-truncated); the C6
  num_predict bump engaged but parse still failed — truncation contributes,
  but the binding constraint is JSON-shaped output (fuller JSON still fails
  strict). H2 quiet: zero prompt-overflow flags at num_ctx 8192.
- Retries move shapes toward code-bearing JSON (`{"code"|"response":
  "<escaped module>"}`) but never to strict-parseable output.
- No valid-but-rejected raws → H4 still open, no sanitizer suspect.
- Seeds 43/44 running to complete the 3-seed baseline.

### Track F pilot: 5 tasks x seed 42 (done 2026-10-07, PRE netlist-fix)
`artifacts/exp_c5_trackF_s42/` — 4/5 strict parse pass@1 (all raw-module
shape), zero with-retry delta (first attempts parsed), 0/5 full-verified.
Initial failures: 3x COVERAGE_BUILD_FAILURE, 1x TYPE_WIDTH_ERROR
(fifo_01 real width errors), 1x SPEC (arbiter_02 task bug).

### C7 verifier bug: stale netlists poison every repair turn (FOUND + FIXED)
Track F counter_04 generated parsing RTL, then failed Gate 1 with
"'counter_04' has already been declared": verify() re-globs workspace
sources each pass, and the previous pass's Yosys <top>_netlist.v was
compiled alongside the RTL. Mechanism: turn 0 Gate-3 coverage build fails
on the just-written netlist (COVERAGE_BUILD_FAILURE); every later turn
fails Gate-1 iverilog spuriously (SYNTAX_ERROR). No valid design could ever
pass twice — latent because no valid RTL ever reached Gate 1 before Track F.
Fix: _select_signoff_sources() excludes *_netlist.v (LEC/timing use
explicit netlist paths, unaffected) + tests/test_netlist_exclusion.py
(2 tests, green). The 3 pilot COVERAGE_BUILD_FAILUREs are tainted by this
bug and excluded from the C5 track decision; Track F pilot re-runs post-fix.
