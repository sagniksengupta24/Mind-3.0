# Mind 3.0 Final Verification Audit — 2026-09-30

## 1. Executive summary

The unfinished reliability work from the previous Codex session has been completed in the repository: deterministic formal-property handling, structured repair evidence, a live benchmark/evidence runner, negative controls, reproducible OSS EDA installation, EDA CI, and an evidence-gated readiness checker are now present.

The repository is **code-ready but not empirically release-ready**. The development host used for this audit does not contain Bubblewrap, Yosys, SymbiYosys, Verilator, or OpenSTA, so live EDA execution was not possible here. The checked-in benchmark transcripts are 50 schema-validation fixtures and are explicitly excluded from performance metrics.

## 2. Verification performed

- Python source compilation: PASS.
- Non-EDA test suite: **176 passed, 4 skipped**.
- The four skips are environment/PDK dependent and are not counted as verified passes.
- 10 EDA-marked tests are excluded from the local non-EDA run; the live Linux workflow executes them when the toolchain is available.
- Benchmark dry-run: correctly reports missing live prerequisites.
- `--dry-run --require-live`: correctly refuses to proceed when live tools are missing.
- Existing 50 transcripts: correctly evaluated as **0 real benchmark tasks + 50 fixtures**, so no performance rate is claimed.
- Readiness checker: all code/integrity checks pass and the final verdict is `EXPERIMENTAL — code-ready, live EDA not executed on this host`.

## 3. Completed reliability work

### Foundation / portability

- Project packaging, CI, container setup, and fail-closed Bubblewrap policy are present.
- Benchmark/production paths do not enable `allow_mock_fallback=True`.
- SSH remote EDA no longer disables host-key verification; configured keys are used.
- SkyWater PDK tests use `MIND3_SKY130_ROOT` rather than a developer-specific absolute path.

### Formal verification

- `src/mind3/core/formal_templates.py` defines a bounded, typed formal-property DSL.
- Unsupported legacy SVA constructs are rejected instead of being weakened or converted to a tautology.
- Reset and clock semantics are derived from the contract.
- Clockless contracts do not receive invented clock/reset semantics.
- The verification harness uses the deterministic compiler rather than passing arbitrary LLM SVA directly to the formal tool.

### Repair loop

- Repair agents receive structured verifier evidence.
- Repair output is constrained by changed-line ratio and line-growth limits.
- Oversized repair patches are rejected before replacing the working RTL.
- Contract, RTL, verification evidence, and repair turns are preserved in benchmark transcripts.

### Benchmarking

`src/mind3/benchmarks/runner.py` now supports isolated live runs, truthful transcript labels, fixture exclusion, task-set hashing, tool-version capture, artifact hashes, runtime, failure categories, Wilson 95% confidence intervals, and JSON/Markdown/HTML reports.

The evaluator cannot turn the existing mock fixtures into reported model performance. A real claim requires the configured minimum of 100 held-out tasks.

### Negative controls

The repository contains intentionally broken designs for latch inference, combinational loops, false formal properties, coverage deficit, timing slack violation, and CDC violation. The runner requires the real EDA path and only accepts a case when the expected failure category is observed without simulation.

## 4. Reproducible live EDA path

`tools/install_oss_cad_suite.py` installs a selected OSS CAD Suite Linux x64 release and records provenance. `.github/workflows/eda_live.yml` installs the pinned `2026-09-29` release, runs the non-EDA suite, EDA-marked tests, and negative controls. `Dockerfile.eda` provides a corresponding container definition.

This audit does **not** claim that the live workflow passed; it was not executed by this local environment.

## 5. Benchmark evidence boundary

The previous audit artifacts correctly invalidate earlier 10-task/30-task performance claims and the 77.8% mutation figure. They remain in `artifacts/audit/invalidated_claims.md` for provenance but are not authoritative performance evidence.

Current benchmark evidence is: **50 fixtures, 0 real benchmark runs**.

## 6. Remaining blockers to a 9/10 empirical claim

1. Execute the live Linux EDA workflow with the pinned toolchain and verify all negative controls.
2. Execute a versioned 100+ task held-out benchmark with real model outputs.
3. Add an independent repeat and at least one external/public benchmark family.
4. Review accepted RTL manually and report cost/latency.
5. Use the resulting report, not unit tests, as the basis for a release-level performance claim.

## 7. Current conclusion

**Engineering quality improved substantially, but empirical capability is not established yet.** The system now has the mechanisms needed to measure itself honestly; it does not have enough live evidence to claim that the agent is already an 8/10 or 9/10 RTL generator.
