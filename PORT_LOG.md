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
