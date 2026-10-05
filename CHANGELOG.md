# Changelog

All entries describe changes actually made. No entry claims a capability is
"fully supported" unless the cited evidence establishes it.

## Unreleased (public-beta packaging)

- Added `KNOWN_LIMITATIONS.md` listing diagnostic benchmark status, Linux /
  OpenROAD / CDC gaps, formal scope, and parser modes.
- Corrected `README.md`: replaced the stale 120-task benchmark table with the
  Stage 6 diagnostic result (0/20, 0/42, diagnostic tier); fixed
  "cryptographically verifiable" wording; refreshed pytest counts (297 passed,
  5 skipped host / 199 passed, 13 skipped container); removed stray control
  characters; documented macOS Seatbelt sandbox alongside Bubblewrap.
- Removed stray terminal-session log `src/mind3/benchmarks/fr.md` (2.2 MB,
  accidentally committed; not source, not evidence, previously shipped in the
  wheel).
- Added `artifacts/stage6_heldout/transcripts/uart_04.json` (genuine 44th live
  transcript, same `RESPONSE_PARSE_FAILURE` class; the committed summary still
  reflects the 42-transcript evaluation).

## 2026-10-03 — `66bbaae` feat(benchmark): capture real generator performance evidence

- Captured 20/20 real development transcripts and 42 heldout transcripts with
  `ollama / qwen2.5-coder:7b`, strict parser; 0 full-verified; diagnostic tier.

## 2026-10-02 — `f504815` ci(verification): add reproducible Linux EDA and sandbox checks

- Added Linux toolchain probes, macOS Seatbelt sandbox tests, OSS CAD Suite
  installer pin (`2026-09-29`).

## 2026-10-02 — `5c7e7ec` fix(formal): strengthen temporal property and vacuity evidence

## 2026-10-02 — `5b38b4b` fix(cdc): make Gate 6 semantics explicit

## 2026-10-02 — `f5ae79e` fix(parser): make strict parsing default and lenient recovery explicit

## 2026-10-02 — `81654a9` fix(verification): make gate execution states explicit

## 2026-10-02 — `d2dfeeb` fix(benchmarks): make evidence tiers and live provenance explicit
