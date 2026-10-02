# Mind 3.0 Failure Forensics

## Current live 20-task benchmark

The requested representative 20-task live benchmark could not start in this environment. The fail-closed command exited with code 1 before any model task was executed because the required EDA toolchain is absent: `bwrap`, `yosys`, `sby`, `verilator`, and `sta`. `ollama` is also not installed. Therefore no current-run RTL/compiler/simulation/formal/repair artifacts exist, and no current before/after percentage is reported.

## Historical real evidence used for diagnosis

`artifacts/P6` contains a preserved real Ollama + real EDA run. On a deterministic 20-task slice, the failure-forensics classifier produced:

- `OTHER` (model-response / generation failures): 11/20 (55%)
- `ENVIRONMENT_FAILURE` (formal/tool infrastructure): 8/20 (40%)
- `SYNTAX_ERROR` (actual RTL syntax/elaboration evidence): 1/20 (5%)

This is historical diagnostic evidence only, not a new held-out benchmark result. The underlying P6 records show model response/parse failures dominating the first group, one genuine Gate-1 RTL syntax/elaboration failure, and unsupported formal/infrastructure failures dominating the second.

## Current held-out static audit

All 120 held-out tasks can be converted into immutable contracts and all generated verification harnesses build successfully. One task, `arbiter_02`, is internally inconsistent: its expected interface contains no `clk`, while its formal properties sample `clk`. The new contract validator classifies this deterministically as `SPECIFICATION_ERROR` and blocks generation rather than inventing an interface signal.

## Evidence preservation

The exact 20 development specifications are copied to `development20_specifications.jsonl`. Historical representative P6 logs are copied under `p6_representative_logs/`. The evidence inventory explicitly marks unavailable live-run fields rather than fabricating them.
