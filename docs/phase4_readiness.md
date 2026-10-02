# Phase 4–7 Readiness Dossier — 2026-09-30

This document supersedes the older host-specific Phase 4 dossier. Earlier absolute paths, tool versions, and “live PASS” statements were tied to a previous machine and are not current repository evidence.

## Current status

Mind 3.0 has the code paths needed for trustworthy formal verification, structured repair, live benchmarking, and evidence-gated release checks. The current development host cannot execute the live EDA path because Bubblewrap, Yosys, SymbiYosys, Verilator, and OpenSTA are not installed.

The authoritative current checks are:

```bash
pytest -q -m 'not eda'
tools/check_readiness.sh
python -m mind3.benchmarks.runner --dry-run --require-live
python scripts/run_negative_controls.py --require-live
```

The first command currently reports **176 passed, 4 skipped, 10 deselected**. The skips are explicit environment/PDK prerequisites and are not considered verified passes. The live commands correctly refuse to claim verification when required tools are absent.

## Completed changes since the previous stopped session

### Formal-property integrity

`src/mind3/core/formal_templates.py` is now the deterministic compilation boundary for supported formal properties. The compiler accepts a bounded typed property set and conservatively classifies selected legacy SVA. Unsupported temporal constructs fail closed. Reset and clock semantics come from the contract, and clockless contracts do not receive invented sequential semantics.

### Structured repair

`VerificationFailureEvidence` carries gate, category, diagnostics, failing-property, trace, metrics, and artifact evidence into the repair prompt. Repair output is constrained by changed-line ratio and line-growth limits, preventing a model from silently replacing the whole design during recovery.

### Benchmark evidence

`src/mind3/benchmarks/runner.py` now executes real tasks only through the sandboxed `PhaseDriver` with `allow_mock_fallback=False`. It records task-set hash, tool versions, artifact hashes, runtime, failure categories, repair turns, and Wilson 95% confidence intervals. Fixtures and mock-provider transcripts are excluded from performance metrics.

### Negative controls

The repository contains explicit broken designs covering latch inference, combinational loops, formal assertion failure, coverage deficit, timing slack violation, and CDC violation. The live runner accepts a negative-control result only when the expected failure category is observed and the result is not simulated.

### Reproducible live EDA path

- `tools/install_oss_cad_suite.py` downloads and verifies an exact OSS CAD Suite Linux x64 release.
- `Dockerfile.eda` defines a Python 3.11 EDA-oriented container.
- `.github/workflows/eda_live.yml` installs the pinned `2026-09-29` release and runs the live EDA tests plus negative controls.
- `.github/workflows/ci.yml` remains the fast Python/unit gate.

## Historical evidence and invalidation

Older empirical artifacts remain under `artifacts/` for provenance. The earlier audit explicitly invalidated claims about the 77.8% mutation kill rate, unexecuted public benchmark comparisons, mixed BMC-depth statements, and inflated model-provenance language. See `artifacts/audit/invalidated_claims.md`.

The current repository therefore makes **no model-performance claim** from those artifacts.

## What still needs real execution

A release-level capability claim requires a Linux host with the pinned EDA environment, successful negative controls, and a real held-out benchmark. The current release criteria call for at least 100 real tasks; stronger thresholds require independent repeats, multiple benchmark families, and human review.
