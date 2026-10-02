# Mind 3.0 Benchmark Suite & Evaluation Architecture

## Current evidence status

The checked-in `benchmarks/transcripts/` directory contains 50 **schema-validation fixtures**. They exercise transcript parsing, persistence, task-set validation, and report generation. They are intentionally excluded from performance metrics.

The historical transcripts in `results/transcripts/` contain 120 records from earlier exploratory runs under `gemini-1.5-pro`. None of these transcripts (0/120) achieved `full_verified_pass`, and they do not constitute release-eligible performance evidence.

At the time of this repository update:

- real model-generated benchmark transcripts meeting release standards: **0**;
- live EDA execution on the development host: **not available**;
- benchmark performance claims: **not established**.

This is deliberate. The evaluator refuses to count mock-provider or schema-fixture rows as model performance.

## Benchmark specifications vs. Evidence records

Task files define problem specifications, not evidence:

- `benchmarks/tasks.jsonl` contains 50 task specifications spanning FSM, arithmetic, bus/protocol, and memory-controller examples.
- `benchmarks/development-20/tasks.jsonl` contains 20 development tasks for local diagnostic iteration.
- `benchmarks/heldout/tasks.jsonl` contains 120 heldout task specifications.

A task specification file is hashed at evaluation time, and the SHA-256 is stored in the report so a result can be tied to an exact task set. A task specification file only becomes benchmark evidence when evaluated by live non-mock model inferences recorded in transcripts.

## Evidence tiers & provenance honesty

Every benchmark summary (`benchmark_summary.json` and `results/summary.json`) explicitly records five honesty fields:

1. `live_provenance` (boolean): `True` **only** when the benchmark evaluated real, non-mock model inference (`actual_real_transcripts > 0`). It is strictly `False` for mock providers, dry runs, or schema fixtures.
2. `actual_real_transcripts` (integer): the actual number of real non-mock model-generated transcripts in the run. This is never simply copied from the task specification count.
3. `required_min_tasks` (integer): the threshold configured for the run.
4. `evidence_tier` (string):
   - `"diagnostic"`: Assigned to development runs (such as 20-task runs), runs with fewer than 100 real tasks, runs using mock providers or schema fixtures, or runs explicitly flagged with `--diagnostic`. Diagnostic runs cannot be presented as release evidence.
   - `"release-eligible"`: Assigned **only** when `live_provenance == True`, `actual_real_transcripts >= 100`, `required_min_tasks >= 100`, and the run was not flagged as diagnostic.
5. `caveat` (string): a plain-language explanation derived from the run state stating why the result is diagnostic or release-eligible.

The 100-task release floor cannot be silently lowered. If a smaller task set or `--min-tasks < 100` is used, the run receives the `"diagnostic"` evidence tier.

## Live benchmark flow

`python -m mind3.benchmarks.runner` executes each task in an isolated workspace and requires the same fail-closed sandboxed verification path used by the product. A live transcript records:

1. the architect contract;
2. generated RTL;
3. the initial gate failure category, if any;
4. structured repair turns and their evidence;
5. final outcome and gate reports;
6. tool versions, duration, and artifact hashes.

The benchmark runner uses `allow_mock_fallback=False` and does not accept simulated passes as benchmark evidence.

## Metrics

The evaluator reports:

- **Pass@1:** successful verified outcome without a repair turn;
- **functional pass:** Gate 3 succeeds in the configured live chain;
- **full verified pass:** the final outcome is both passed and marked `silicon_verified`;
- **repair success:** final success occurred after at least one repair turn;
- mean and p50 turns taken;
- failure-category counts;
- 95% Wilson confidence intervals.

These are descriptive measurements, not guarantees about unseen designs.

## Release thresholds

| Level | Functional | Full verified | Evidence |
|---|---:|---:|---|
| Experimental | report only | report only | exact model/tool versions + reproducible transcripts |
| Useful specialist tool | ≥70% | ≥40% | 100+ held-out tasks, negative controls, cost and latency |
| Strong specialist tool | ≥80% | ≥60% | independent repeat and human review |
| 9/10 evidence threshold | ≥85% | ≥70% | multiple benchmark families and real-user validation |

## Negative controls

The negative-control corpus is separate from performance benchmarks. A live run must demonstrate that intentionally broken designs are rejected with the expected category rather than being treated as success:

`LATCH_INFERRED`, `COMBINATIONAL_LOOP`, `FORMAL_INVARIANT_BREACH`, `COVERAGE_DEFICIT`, `TIMING_SLACK_VIOLATION`, `CDC_VIOLATION`.

Run:

```bash
python scripts/run_negative_controls.py --require-live
```

Timing uses the bundled small SkyWater Liberty fixture by default and accepts an override through `MIND3_NEGATIVE_CONTROL_LIBERTY`. All checks still require the corresponding live binaries and a Bubblewrap-enabled Linux host.

## Report outputs

`BenchmarkRunner.write_report()` emits three artifacts:

- `benchmark_summary.json` — machine-readable evidence;
- `benchmark_report.md` — review-friendly text report;
- `benchmark_report.html` — self-contained report suitable for a browser or CI artifact viewer.

No report should be presented as a product-performance claim unless the real task count, benchmark hash, model, provider, and live tool versions are present.

## Human-approved export

Release evidence is exported only after the benchmark summary satisfies the release thresholds and a human approval JSON matches the exact SHA-256 of `benchmark_summary.json`. This prevents stale approval files from being applied to new evidence. The command is:

```bash
python scripts/export_verified_bundle.py --approval human_approval.json
```

The checked-in fixture report intentionally fails the release threshold because it contains zero real benchmark tasks.
