# Mind 3.0 Benchmark Report

Generated: `2026-10-05T17:09:53Z`
Task-set SHA-256: `bae56a8db36a0f3d47f6bef1c2ec325bdd1e14dd16addb68461a1b59dbdd2c24`

## Evidence scope
- Evidence tier: **diagnostic**
- Live provenance: **True**
- Transcripts observed: 10
- Real generation outputs included in metrics: 10
- Fixtures excluded: 0
- Required minimum tasks: 10
- Caveat: *Diagnostic evidence only: run was explicitly executed in diagnostic mode with 10 real transcripts (required_min_tasks=10). Not eligible for release claims.*

## Metrics
| Metric | Count | Rate | 95% CI |
|---|---:|---:|---:|
| Initial success (Pass@1) | 1/10 | 10.0% | [1.8%, 40.4%] |
| Functional success | 1/10 | 10.0% | [1.8%, 40.4%] |
| Full verified success | 1/10 | 10.0% | [1.8%, 40.4%] |
| Repair success | 0/10 | 0.0% | — |

## Guardrails
- Performance claims require at least 100 real holdout tasks.
- Schema-validation fixtures and mock-provider runs are never counted as benchmark evidence.
- Full verified means the configured signoff pipeline passed; this is not foundry tapeout signoff.

## Failure categories
- `COVERAGE_DEFICIT`: 5
- `FORMAL_INVARIANT_BREACH`: 3
- `CDC_VIOLATION`: 1
- `NONE`: 1

## Baselines
No same-task-set baselines were supplied.

## Tool versions
- `openroad`: `f12e2f474102bfb875eeee57fb610d7d7de17770`
- `sby`: `SBY v0.69`
- `sta`: `2.3.1`
- `verilator`: `Verilator 5.020 2024-01-01 rev (Debian 5.020-1)`
- `yosys`: `Yosys 0.33 (git sha1 2584903a060)`
