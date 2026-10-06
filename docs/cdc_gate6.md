# Gate 6 — CDC Semantics (Stage 4)

Gate 6 (`_run_gate6_cdc_analysis` in `src/mind3/core/verifier.py`) runs Yosys
`cdc -verbose` static analysis to detect unregistered clock-domain crossings.

## One clock does not eliminate CDC

A single-clock design can still contain crossings: an asynchronous reset
removes the reset without the clock, and an asynchronous external input
(interrupt, async enable, async status/control) is sampled by clocked logic
without any clock relationship. Clock count therefore never decides whether
Gate 6 runs. The decision reads explicit contract state; the tool itself
analyzes whatever clocks the RTL actually contains.

## Contract declarations (source of truth)

`InterfaceContract.async_inputs` lists asynchronous input signals:

- `None` (default) means the contract does not declare async-input state,
  so CDC analysis is required.
- An explicitly empty list `[]` declares the design has no asynchronous
  inputs.
- A non-empty list declares asynchronous inputs, which require analysis.

`ResetContract.synchronous` declares reset timing. An asynchronous reset
requires CDC analysis even with a single clock.

`validate_contract_consistency` rejects async inputs that are not declared
input ports. `contract_from_benchmark_record` leaves `async_inputs` as
`None` (unknown): benchmark metadata never implies async-input absence.

## Decision branches

| Design condition | CDC required? | Gate 6 result |
| ---------------- | ------------- | ------------- |
| Contract declares `async_inputs == []` and reset absent/synchronous | No | `SKIPPED` (`cdc_skip_reason: contract_declares_no_cdc`) |
| Async reset declared | Yes | Tool runs |
| Async inputs declared (non-empty) | Yes | Tool runs |
| `async_inputs` undeclared (`None`) or no contract | Yes | Tool runs |
| `require_cdc=False` (explicit caller opt-out) | No | `SKIPPED` (`cdc_skip_reason: explicit_opt_out`) |

The two skip reasons have distinct `details` text and distinct
`cdc_skip_reason` values; an opt-out is never indistinguishable from
"not needed".

## Failure categories (never collapsed)

- `EDA_BINARY_MISSING` — no `yosys` binary at all (required CDC).
- `CDC_TOOLING_UNAVAILABLE` — CDC was required but Yosys lacks the `cdc`
  command. Never PASS.
- `CDC_VIOLATION` — the tool ran and reported unregistered crossing(s),
  with tool evidence in `cdc_violations`. Never PASS.
- `CDC_ANALYSIS_FAILED` — the tool ran but errored (nonzero exit without
  violation markers). Never PASS.

The failure taxonomy preserves each fine-grained category exactly;
tool-absence and tool-error are not relabeled as violations.

## Aggregate signoff

Any of the three failure categories fails overall verification
(`passed=False`). A contract-declared no-CDC skip is vacuous by explicit
declaration and does not invalidate `silicon_verified`. Simulated
(`allow_mock_fallback`) results never count as signoff.

## Fallback engine: rtl-buddy-cdc (verified on Linux)

When Yosys lacks the `cdc` command but the `rtl-buddy-cdc` binary is
available, Gate 6 runs `rtl-buddy-cdc lint --top <top> --sdc <sdc>
--format json <sources>` instead of failing closed. Only error-severity
findings fail (`CDC_VIOLATION`); warnings are reported, never fatal. The SDC
is taken from the workspace when present, otherwise derived minimally from
clock-like port names (10 ns clocks, all pairs asynchronous) and labeled as
derived in the report. Absence of both engines still fails closed as
`CDC_TOOLING_UNAVAILABLE` — never a pass, never simulated.

## Current host limitations

Stock Homebrew Yosys (observed: 0.69+post on macOS) does not bundle the
`cdc` command: `yosys -p "help cdc"` reports
`No such command or cell type: cdc`. On such hosts, CDC-required designs
fail closed with `CDC_TOOLING_UNAVAILABLE`, and the `cdc_violation`
negative control skips (it is not a pass). The statement that the OSS CAD
Suite Linux distribution supplies `cdc` remains [UNVERIFIED] until a Linux
OSS CAD Suite environment demonstrates it; nothing in this stage changes
that claim.
