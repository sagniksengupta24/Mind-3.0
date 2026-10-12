# C0 Baseline Manifest — Generator Recovery (qwen2.5-coder:7b, model unchanged)

Frozen before the first rerun. Any threshold or config change after this point
needs a written amendment committed before the rerun it affects.

## Codebase
- Commit: `31a42e3daf18995f9849907bbdcd2e815bf87124` (tag: `baseline/generator-recovery-c0`)
- Claim ladder ceiling so far: R0 only (Stage 6 diagnostic 0/20 + 0/42).

## Task sets (SHA-256)
- `benchmarks/heldout/tasks.jsonl` (120): `bae56a8db36a0f3d47f6bef1c2ec325bdd1e14dd16addb68461a1b59dbdd2c24`
- `benchmarks/development-20/tasks.jsonl` (20): `539e79afaf6fa445a95ad82c2337ff70f60d60d4e912f114dd9a3cf402f59c8c`
- `benchmarks/tasks.jsonl` (50 fixtures): `9d137519b913a519d7e45c7f940378a27292e71ca88c728c4a8ad2cecf58e7c4`
- Contamination: dev-20 ⊆ heldout-120 (overlap 20/20). Confirmation set =
  heldout-minus-dev = 100 tasks, frozen in `confirmation_ids.json`.
  No tuning on the confirmation set, ever.

## Model (unchanged by this plan)
- Ollama 0.31.1, model `qwen2.5-coder:7b` (blob `sha256-60e05f21000714…`,
  Q4_K_M, 7.6B params, 32k context).
- Chat template: ChatML (`<|im_start|>` roles); default system
  "You are Qwen, created by Alibaba Cloud…". No custom Modelfile.
- Modelfile *parameter* changes (temperature/seed/num_ctx/num_predict) are
  allowed as "model unchanged"; weight/quantization changes are forbidden.
- Structured-output verdict: Ollama 0.31.x supports JSON-schema `format`,
  so Track J (schema-constrained) is feasible; C2 probe must confirm
  empirically before Track J relies on it.

## Host EDA (this machine, macOS arm64)
- yosys 0.69+post, sby 0.69, verilator 5.052 — present.
- sta/opensta, openroad, bwrap — MISSING (Gate 4/5/6 paths skip or fail
  closed as before; generator-recovery claims stop at Gate 3/2 anyway).

## Pre-registered thresholds (locked)
- Tune further only if dev strict-parse < 80% (3-seed mean).
- Confirmation only if strict parse ≥ 80% AND sim-entry ≥ 30%.
- Escalation if both tracks < 50%, or 50–80% after 3 rounds: one boxed
  sanitizer/regex timebox, then declare the written ceiling (R3).
- Track decision: win on mean ≥ 3 tasks AND ≥ 2 of 3 seeds, else Track F
  on simplicity; tie documented. The ≥3-task margin is inside n=20
  Wilson noise — seed consistency carries the decision.
- Always report pass@1 and with-retry separately; claim only CI lower bounds.
- Budget: max 3 tuning rounds on dev-20, one confirmation sample, no seconds.
  Any checkpoint > 2× its time estimate stops and re-plans.
