# Evidence Closure Report (2026-10-03)

Config frozen: `ollama / qwen2.5-coder:7b`, strict parser, seed 42.
Heldout task-set SHA-256: `bae56a8db36a0f3d47f6bef1c2ec325bdd1e14dd16addb68461a1b59dbdd2c24`.

## Environment

- Platform Darwin 26.6.1, arch arm64, Python 3.14.7. Docker 29.8.0
  (desktop-linux); real Linux proven via `docker run --rm ubuntu:22.04`
  → `Linux aarch64`. No podman/lima/colima.
- Host tools (executed): Yosys 0.69+post, SBY 0.69, Z3 5.1.0,
  Verilator 5.052, OpenSTA (`sta`) 3.1.0, `sandbox-exec`. Absent: `opensta`
  alias, `openroad`, `bwrap`.
- Pinned OSS CAD Suite `2026-09-29` linux-arm64 downloaded with checksum
  match (`bdfee8ce…7842cd75`) to `/tmp/oss-cad/suite` (outside repo, not
  committed). Suite Yosys: 0.69+156.

## Linux proof

- `yosys -p "help cdc"` in container → `No such command or cell type: cdc`
  (exit 0, log hash `f26c6b2d36`). Pinned-build CDC absence confirmed on
  Linux, corroborating `docs/linux_verification.md`. Gate 6 stays fail-closed
  `CDC_TOOLING_UNAVAILABLE`. No CDC-capable execution exists anywhere tested.
- No `openroad` / `opensta` / `sta` binary in the pinned suite or container:
  OpenROAD and Linux-OpenSTA stay `[PENDING-HUMAN]`. Nothing mocked.
- Full `eda_live.yml` on ubuntu-24.04 not run here: `[PENDING-HUMAN]`.
- Note: the suite ships a stub `bin/bwrap` (69-byte shell script, always
  exits 1). The repo test correctly does not pass with it.

## Sandbox proof

- Linux: repo test `test_bubblewrap_sandbox_network_isolation_outbound_blocked`
  **PASSED** in a privileged `python:3.11-slim` container with Debian
  bubblewrap 0.12.0 (host loopback baseline connected; in-sandbox attempts
  blocked) → `EGRESS_BLOCK_VERIFIED` for the sandbox mechanism. Caveats:
  Debian bwrap, not the suite stub; `--privileged` needed for nested
  namespaces under Docker Desktop; repo mounted read-only.
- macOS: `tests/test_macos_sandbox.py` 5/5 pass, including
  `test_macos_seatbelt_egress_blocked_by_real_socket_attempt` (real loopback
  listener baseline; in-sandbox connect denied, `errno=1`) → Seatbelt egress
  block verified on Darwin.

## Formal proof

- Bounded BMC at fixed depth 25 + same-bound cover mode (`verifier.py:1628,
  1913`); no induction or `prove` mode exists → bounded only, as documented.
  `UNBOUNDED_FORMAL = NOT CURRENTLY PROVEN`. No semantics touched.

## Benchmark proof

- No new run this pass (anti-tuning lock + ~2h cost). Standing evidence:
  20 real dev + 42 real heldout-partial transcripts, `qwen2.5-coder:7b` /
  `ollama`, strict, 0 initial / 0 functional / 0 full-verified / 0 repair.
  Task-set hash above; config frozen in `audit/stage6_dataset_freeze.json`.
  Tier: **diagnostic**. Release (≥100 + Stage 2b thresholds) not established.

## Repository hygiene

- Secrets: filename + pattern scan (values redacted) → only placeholder test
  keys; zero real secrets in source, configs, or transcripts; no `.env`.
- License: no `LICENSE`/`COPYING` file, no pyproject declaration, none in git
  history → `REQUIRES HUMAN DECISION`, nothing invented.
- Claims: full README/docs/metadata sweep → no vague labels found; Stage 7
  corrections stand; no new corrections needed (`MIND_STATE.md` is marked
  historical).
- Package/install: wheel rebuilt 3.1.0 (40 files, entry point present, no
  stray log, no secrets); clean-worktree install + CLI + smoke + tests pass;
  `mind3-test` container suite 199 passed / 13 skipped.

## Remaining gaps

Linux CI run, OpenROAD execution, Linux OpenSTA execution, unbounded formal,
heldout cleanliness (`UNVERIFIED`), license choice, full ≥100-task heldout
run, release eligibility. See `audit/evidence_gap_matrix.md`.
