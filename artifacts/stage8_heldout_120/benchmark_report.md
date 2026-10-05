# Mind 3.0 Benchmark Report

Generated: `2026-10-05T08:00:33Z`
Task-set SHA-256: `bae56a8db36a0f3d47f6bef1c2ec325bdd1e14dd16addb68461a1b59dbdd2c24`

## Evidence scope
- Evidence tier: **release-eligible**
- Live provenance: **True**
- Transcripts observed: 120
- Real generation outputs included in metrics: 120
- Fixtures excluded: 0
- Required minimum tasks: 100
- Caveat: *Release-eligible evaluation: evaluated 120 real non-mock transcripts meeting the 100+ task threshold (required_min_tasks=100). Metrics represent measured empirical model performance.*

## Metrics
| Metric | Count | Rate | 95% CI |
|---|---:|---:|---:|
| Initial success (Pass@1) | 0/120 | 0.0% | [0.0%, 3.1%] |
| Functional success | 0/120 | 0.0% | [0.0%, 3.1%] |
| Full verified success | 0/120 | 0.0% | [0.0%, 3.1%] |
| Repair success | 0/120 | 0.0% | — |

## Guardrails
- Performance claims require at least 100 real holdout tasks.
- Schema-validation fixtures and mock-provider runs are never counted as benchmark evidence.
- Full verified means the configured signoff pipeline passed; this is not foundry tapeout signoff.

## Failure categories
- `RESPONSE_PARSE_FAILURE`: 119
- `SPECIFICATION_ERROR`: 1

## Baselines
No same-task-set baselines were supplied.

## Tool versions
