# Mind 3.0 Benchmark Report

Generated: `2026-10-02T22:30:04Z`
Task-set SHA-256: `539e79afaf6fa445a95ad82c2337ff70f60d60d4e912f114dd9a3cf402f59c8c`

## Evidence scope
- Evidence tier: **diagnostic**
- Live provenance: **True**
- Transcripts observed: 20
- Real generation outputs included in metrics: 20
- Fixtures excluded: 0
- Required minimum tasks: 20
- Caveat: *Diagnostic evidence only: run was explicitly executed in diagnostic mode with 20 real transcripts (required_min_tasks=20). Not eligible for release claims.*

## Metrics
| Metric | Count | Rate | 95% CI |
|---|---:|---:|---:|
| Initial success (Pass@1) | 0/20 | 0.0% | [0.0%, 16.1%] |
| Functional success | 0/20 | 0.0% | [0.0%, 16.1%] |
| Full verified success | 0/20 | 0.0% | [0.0%, 16.1%] |
| Repair success | 0/20 | 0.0% | — |

## Guardrails
- Performance claims require at least 100 real holdout tasks.
- Schema-validation fixtures and mock-provider runs are never counted as benchmark evidence.
- Full verified means the configured signoff pipeline passed; this is not foundry tapeout signoff.

## Failure categories
- `RESPONSE_PARSE_FAILURE`: 19
- `SPECIFICATION_ERROR`: 1

## Baselines
No same-task-set baselines were supplied.

## Tool versions
