# Mind 3.0 — Known Limitations (Public Beta)

This document lists what Mind 3.0 does **not** yet do. It is normative for the
public beta: any claim contradicting this file is a bug in that claim, not in
this file.

## 1. Generator quality is model-dependent

- RTL generation quality depends entirely on the configured model. The pinned
  default is `ollama / qwen2.5-coder:7b`.
- LLM output is non-deterministic; a passing run does not guarantee the next
  run passes.

## 2. Generator benchmark is diagnostic, not release-eligible

- Stage 6 evidence (strict parser, seed 42): **0/20** full-verified on the
  development set and **0/42** on a partial heldout run. Evidence tier:
  **`diagnostic`**.
- Real transcripts captured: **20 / 42**. Release eligibility requires
  **≥100 real heldout tasks** plus the Stage 2b thresholds
  (functional ≥70% / full-verified ≥40% for useful-specialist).
- The dominant failure mode is `RESPONSE_PARSE_FAILURE`: the strict parser
  rejects this model's typical prose-wrapped formatting before any EDA gate
  runs. This is a measured result, not a tuning prompt.
- Heldout cleanliness is `[UNVERIFIED]`: the 20 development tasks are a subset
  of the 120 heldout tasks and were executed live before/during Stage 6.

## 3. Linux / OpenROAD / CDC tooling gaps (Stage 5)

- **OpenROAD (Gate 5)** is not installed on macOS hosts and was not executed;
  Gate 5 support is `[PENDING-HUMAN]`.
- **Yosys CDC (Gate 6)**: the macOS Homebrew Yosys and the pinned OSS CAD
  Suite `2026-09-29` linux-arm64 build both lack the `cdc` command
  (`No such command or cell type: cdc`). Gate 6 fails closed as
  `CDC_TOOLING_UNAVAILABLE`. CDC verification on a CDC-capable Yosys build is
  `[PENDING-HUMAN]`.
- **Bubblewrap sandbox** is Linux-only; macOS uses the Seatbelt
  (`sandbox-exec`) sandbox. Outbound-egress blocking was verified on macOS
  Seatbelt; Linux Bubblewrap egress evidence remains `[PENDING-HUMAN]`.
- Full SkyWater 130nm PDK-gated checks require `MIND3_SKY130_ROOT` and are
  skipped without it.

## 4. Formal verification scope

- Bounded Model Checking only (SymbiYosys + Z3); unbounded proofs are out of
  scope.
- Only the deterministic typed bounded-property template subset is supported
  (see `docs/gate2_formal.md`). Unbounded temporal operators (`eventually`,
  `s_until`, liveness) and unconstrained SVA are not supported.
- Vacuityrisk: properties that pass vacuously are flagged where the templates
  detect them, but general vacuity detection is not claimed.

## 5. Parser modes

- **Strict (default)**: accepts only `WriteFileAction` JSON, fenced
  Verilog/SystemVerilog blocks, repair patches with `base_code`, or exactly
  one raw Verilog module. Anything else is `RESPONSE_PARSE_FAILURE`.
- **Lenient (explicit opt-in)**: bounded recovery of documented malformed
  local-model shapes. Lenient results are not equivalent to strict results.

## 6. Platform and dependency notes

- Python ≥3.11 required (developed/tested on 3.14; Docker image pins 3.11).
- Requires external EDA binaries on PATH: `yosys`, `sby`, `verilator`, and
  `sta`/`opensta` for timing. Missing required tools fail closed; they are
  never silently mocked in the live path.
- No license file is shipped yet (`[PENDING-HUMAN]` — owner must choose
  terms). No `LICENSE` should be assumed.
- A `SiliconSignoffVerifier` PASS means the configured live checks passed for
  that run. It is not foundry, production, or tapeout signoff.
