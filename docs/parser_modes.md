# Model-Response Parser Modes (Stage 3)

Mind-3.0 parses model output into synthesizable SystemVerilog with
`_parse_model_code_response` (`src/mind3/core/driver.py`). There are exactly
two modes. The parser never silently transforms ambiguous model output into
something different from what the model supplied.

## Strict mode (default)

Strict mode is the default. It is used whenever no `parser_mode` is configured.

Accepted formats, in order:

1. A valid `WriteFileAction` schema object (`{"action": "write_file",
   "path": ..., "content": ...}`). The content is used verbatim.
2. A markdown-fenced Verilog/SystemVerilog block
   (```verilog, ```systemverilog, ```sv, or bare ```) containing `module`
   and `endmodule`. The fenced content is used verbatim. Fences are not
   extracted from raw JSON objects.
3. A repair-loop patch object (`patch`/`replacement` with `line` or
   `source_context`), but only when the caller supplies `base_code`.
   Initial generation never supplies `base_code`, so this branch is
   unreachable outside the bounded repair flow. Patch text is used verbatim.
4. Raw text that is exactly one Verilog module block (leading comments or
   file headers allowed, nothing else). Returned verbatim.

Ambiguity behavior: anything else — prose-wrapped modules, JSON objects
under any key (including `content`, `module_code`, `response`), structural
AST dicts, truncated modules — raises `ModelResponseParseError`.

Failure behavior: the caller treats the failure as a bounded compile-stage
repair opportunity (`RESPONSE_PARSE_FAILURE`); nothing is written to disk.

Strict mode never searches arbitrary JSON keys, never reconstructs modules
from AST parts, and never applies `unicode_escape` decoding. Non-ASCII
comments survive unchanged.

## Lenient mode (explicit opt-in)

Lenient mode is for local-model formatting deviations. It is enabled only by
passing `parser_mode="lenient"` explicitly to `PhaseDriver`,
`BaselineComparisonRunner`, `BenchmarkRunner.run_live_task`,
`execute_full_benchmark`, or the `--parser-mode` CLI flags. It is never
inferred from provider name, model name, failure count, environment, or
hostname. Any other `parser_mode` value raises `ValueError`.

Lenient mode keeps items 1–2 from strict mode, then adds bounded recovery
for JSON responses limited to documented shapes:

- Structural AST dicts: a module identifier (`module`, `name`,
  `module_name`, `label`, or `task_id`) plus an implementation alias
  (`implementation`, `synthesizable_code`, `code`, `body`, `source_code`,
  `source`, `rtl`, `design`, `verilog`, `systemverilog`) or structural
  parts (`internal_signals`/`signals`/`registers`, `always_blocks`/
  `processes`, `assign_statements`/`assigns`) with `parameters` and
  `pinout`/`ports`/`pins`/`port_declarations`/`interfaces`.
- Documented known keys, in order: `module_code`, `verilog_code`, `code`,
  `content`, `response`, `rtl`, `text`. Only these keys are ever inspected.
- Repair-loop patch objects when `base_code` is supplied (same rule as strict).

Only JSON string values recovered through the two JSON branches above are
unescaped once (local models frequently double-escape newlines). Fenced,
raw, schema, and patch content is always verbatim.

A JSON object matching no documented shape is rejected immediately; the
free-text fallbacks (verbatim first-module-block extraction) never run on
JSON input, so arbitrary JSON values are never scanned. Ambiguous lenient
input still raises `ModelResponseParseError`.

## Mode recording

The configured mode is stored as `PhaseDriver.parser_mode` and passed to
every `_parse_model_code_response` call. It is recorded in execution
traces on `MODEL_CALL` payloads (`Principal RTL Design Engineer`,
`Independent RTL Verification Repair Engineer`) and on `VERIFY`
`RESPONSE_PARSE_FAILURE` payloads, in benchmark transcript `environment`
data, and in benchmark summary `methodology` (`parser_mode`,
`observed_parser_modes`, plus a non-equivalence note). A benchmark run
with `parser_mode="lenient"` must not be presented as equivalent to a
`parser_mode="strict"` run.

## Repair-loop separation

Repair-loop patch application (`base_code` supplied) is a repair-loop
mechanism, not initial-parse recovery. Repair budgets, diff statistics,
and patch validation (`test_safe_patch_application_repair`) are unchanged
by parser modes.
