# Mind 3.0 Benchmark Report

Generated: `2026-10-05T12:08:58Z`
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
| Initial success (Pass@1) | 0/10 | 0.0% | [0.0%, 27.8%] |
| Functional success | 0/10 | 0.0% | [0.0%, 27.8%] |
| Full verified success | 0/10 | 0.0% | [0.0%, 27.8%] |
| Repair success | 0/10 | 0.0% | — |

## Guardrails
- Performance claims require at least 100 real holdout tasks.
- Schema-validation fixtures and mock-provider runs are never counted as benchmark evidence.
- Full verified means the configured signoff pipeline passed; this is not foundry tapeout signoff.

## Failure categories
- `RESPONSE_PARSE_FAILURE`: 10

## Baselines
No same-task-set baselines were supplied.

## Tool versions
