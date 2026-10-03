# Mind 3.0 Benchmark Report

Generated: `2026-09-30T09:29:44Z`
Task-set SHA-256: `539e79afaf6fa445a95ad82c2337ff70f60d60d4e912f114dd9a3cf402f59c8c`

## Evidence scope
- Transcripts observed: 1
- Real generation outputs included in metrics: 1
- Fixtures excluded: 0

## Metrics
| Metric | Count | Rate | 95% CI |
|---|---:|---:|---:|
| Initial success (Pass@1) | 0/1 | 0.0% | [0.0%, 79.3%] |
| Functional success | 0/1 | 0.0% | [0.0%, 79.3%] |
| Full verified success | 0/1 | 0.0% | [0.0%, 79.3%] |
| Repair success | 0/1 | 0.0% | — |

## Guardrails
- Performance claims require at least 100 real holdout tasks.
- Schema-validation fixtures and mock-provider runs are never counted as benchmark evidence.
- Full verified means the configured signoff pipeline passed; this is not foundry tapeout signoff.

## Failure categories
- `RESPONSE_PARSE_FAILURE`: 1

## Baselines
No same-task-set baselines were supplied.

## Tool versions
- `openroad`: `missing`
- `sby`: `SBY v0.69`
- `sta`: `3.1.0`
- `verilator`: `Verilator 5.052 2026-09-05 rev vUNKNOWN-built20260905`
- `yosys`: `Yosys 0.69+post (git sha1 143eb14f9cc55d6f8927e68523b0c9d2166ed02c, Release, AppleClang clang++ 21.0.0.21000101)`
