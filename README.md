# Mind 3.0 — Fail-Closed RTL Generation & Verification Workbench

> **Brutal truth first:** the verification plumbing is real and genuinely
> fail-closed. The generator scores **0%**. If you want a tool that writes
> working Verilog today, this is not it. If you want a strict harness that
> refuses to lie about broken RTL, that's exactly what this is.

Mind 3.0 generates small-to-medium SystemVerilog IP (FIFOs, arbiters,
counters, FSMs, bus peripherals, protocol adapters) with an LLM, then checks
it through a 10-phase pipeline and 6 verification gates. It would rather fail
loudly than pass quietly.

**This is NOT foundry signoff. NOT tapeout-ready. NOT production EDA.**
A green `SiliconSignoffVerifier` result means "the configured live checks
passed on this run" — nothing more.

---

## 1. The honest scoreboard

| What | Result | Verdict |
|---|---|---|
| Full pytest suite (macOS host) | **297 passed, 5 skipped** | Real. Zero failures. Skips are env-gated (no OpenROAD, no `bwrap` on Mac, no PDK). |
| Docker `mind3-test` (no EDA) | **199 passed, 13 skipped** | Real. EDA tests skip without a Linux EDA stack. |
| EDA smoke (Yosys 0.69+post, Verilator 5.052, SBY 0.69 + Z3) | Pass | Real, on host. |
| Negative controls (16 intentionally broken designs) | **14 caught at exact expected gate, 2 env-skipped** | The best evidence this repo has. The gates actually catch bugs. |
| Generator, Stage 6 diagnostic (`ollama / qwen2.5-coder:7b`, strict parser, seed 42) | **0/20 dev, 0/42 heldout partial. 0% full-verified.** | Real, and terrible. ~95% of failures are `RESPONSE_PARSE_FAILURE` — the strict parser rejects the model's prose-wrapped output before any EDA tool even runs. |
| Release-eligible benchmark (≥100 real heldout tasks) | **Never run. Does not exist.** | Do not quote any accuracy number for this project. There is none. |
| Frontier models (GPT-4o, Claude, etc.) | **Never tested live** | Unknown. Anyone claiming otherwise is guessing. |
| Gate 6 CDC | **Unverifiable.** `cdc` command missing from Homebrew Yosys AND pinned OSS-CAD `2026-09-29` linux-arm64. Always `CDC_TOOLING_UNAVAILABLE`. | Fails closed correctly, but CDC is effectively untested. |
| Gate 5 OpenROAD / Sky130 PDK | **Never executed on Mac. `[PENDING-HUMAN]`.** | Code exists. Evidence doesn't. |
| Formal (Gate 2) | BMC depth-25 subset only. No liveness, no unbounded proofs, partial vacuity detection. | Honest but narrow. |

**Bottom line:** plumbing ~solid, generator ~useless with the pinned default
model, physical/CDC coverage ~missing. The 0% is a *measured* result, not a
bug in measurement — the strict parser is doing its job, the model just
doesn't emit clean RTL in the required shape.

---

## 2. What actually works

- **Fail-closed gate philosophy, enforced in code — not slogans:**
  `REAL TOOL → REAL RESULT / MISSING TOOL → EXPLICIT SKIP-BLOCK / MOCK → NEVER PRESENTED AS VERIFIED.`
  The benchmark path hard-blocks mocks (`allow_mock_fallback=False`). The demo script (`examples/run_full_flow.py`) uses `allow_mock_fallback=True` — **do not copy that into evaluation code.**
- **10-phase pipeline** (`INTAKE → ROUTE → SNAPSHOT → MODEL_CALL → PARSE → POLICY_CHECK → EXECUTE → OBSERVE → VERIFY → REPAIR_OR_FINISH → TRACE`) with SHA-256 hash-chained traces, tool versions, and artifact hashes. Tamper-evident, not PKI attestation.
- **6 gates, executed in this order, fail-fast:** Gate 1 (Yosys elaboration + latch/loop) → 1b (LEC, opt-in) → 3 (Verilator sim + coverage) → 2 (SBY/Z3 BMC formal) → 4 (OpenSTA timing) → 5 (OpenROAD, opt-in) → 6 (CDC, fails closed without tooling).
- **12-category failure taxonomy** — every failure maps to a machine-readable bucket (`SPECIFICATION_ERROR`, `RTL_SYNTAX_ERROR`, …, `TIMEOUT`, `UNKNOWN`). No silent failures.
- **Bounded repair loop** — budget + edit-scope capped. It won't rewrite itself into oblivion.
- **Release gate** (`ArtifactReleaseBundle`): 8 immutable fields + human approval hash bound to the exact `benchmark_summary.json` SHA. Missing/altered/unapproved = blocked. Exporter refuses to run without threshold + hash match.
- **Reproducibility:** task-set SHA manifest (heldout-v1: 120 tasks, `bae56a8d…`), Wilson CIs, isolated workspaces, same-task-set baseline rejection.
- **Sandboxing:** Bubblewrap `--unshare-all` on Linux, Seatbelt `sandbox-exec` on macOS. Fails closed if the sandbox is missing. No silent unsandboxed fallback.

## 3. What's broken / missing / misleading

1. **The generator doesn't generate.** With `qwen2.5-coder:7b` + strict parser, output is prose-wrapped modules the parser correctly rejects. Lenient mode exists but is unmeasured — no, switching to lenient doesn't fix the score, it just changes what you're measuring.
2. **No release-eligible evidence exists.** Anything in `results/summary.json` from before Stage 6 is exploratory and superseded. The only live-inference numbers are the 0/20 + 0/42 diagnostics.
3. **`examples/run_full_flow.py` will mislead you.** Hardcoded FIFO demo, mock fallback allowed. Fine as a plumbing demo, garbage as a benchmark.
4. **`cli.py` docstring lied.** It advertised `bundle export` / `verify` subcommands that don't exist — fixed 2026-10-08 to list the real CLI (`benchmark`, `smoke-test`, `negative-controls` only).
5. **`FINAL_VERIFICATION_AUDIT.md` is stale** (claims 176/4, superseded by 297/5 + Stage 6). Read it as history, not truth.
6. **`MIND_TASK.md` / `MIND_STATE.md` are agent scaffolding**, not user docs.
7. **No `LICENSE` ships.** `[PENDING-HUMAN]` — owner must pick terms. Assume all-rights-reserved until then.
8. **`.gitignore` leaks.** `results/`, `artifacts/*` (except `runs/`), `*.whl`, `.env` are not ignored. Clean before you commit.
9. **`Dockerfile.eda` defaults to non-EDA tests** (`CMD pytest -q -m 'not eda'`). The EDA image doesn't run EDA tests unless you override the command.
10. **Heldout cleanliness is `[UNVERIFIED]`** — the 20 dev tasks overlap the 120 heldout tasks and ran live first. Don't claim heldout purity.

See `KNOWN_LIMITATIONS.md` — it is normative. Any claim contradicting it is a bug in the claim.

---

## 4. Quickstart

**Requirements:** Python ≥3.11, plus EDA binaries on PATH for live gates: `yosys`, `sby`, `verilator`, `sta`/`opensta` for timing. Linux + `bwrap` for sandboxing and Gates 4–6. Gate 4 (timing) additionally needs a real PDK liberty file passed via `--liberty` (e.g. Sky130) — the 4.8KB stub in `src/mind3/pdata/` breaks Yosys ABC mapping; without it Gate 4 reports `ENVIRONMENT_FAILURE` by design.

```bash
pip install -e '.[dev]'

# Sanity: do tools exist and work?
./bin/mind3 smoke-test

# Fast suite, no EDA needed:
python -m pytest -q -m 'not eda'

# Full suite, pinned Linux EDA host only:
python -m pytest -q

# Do the gates catch known-bad RTL?
./bin/mind3 negative-controls
./bin/mind3 negative-controls --require-live   # fail if any skip

# Readiness verdict (returns `experimental` without live EDA — by design):
tools/check_readiness.sh
MIND3_RUN_LIVE_EDA=1 tools/check_readiness.sh  # live env only
```

**Provision EDA (Linux):**

```bash
python tools/install_oss_cad_suite.py --tag 2026-09-29
# or
docker build -f Dockerfile.eda -t mind3-eda .
```

**Benchmarks (prepared Linux host + Ollama running):**

```bash
python -m mind3.benchmarks.runner --dry-run
python -m mind3.benchmarks.runner --dry-run --require-live

python -m mind3.benchmarks.runner \
  --model "qwen2.5-coder:7b" \
  --provider "ollama" \
  --max-repairs 3 \
  --min-tasks 100
```

Evaluate existing transcripts without re-running generation:

```bash
python -m mind3.benchmarks.runner \
  --evaluate-existing \
  --transcripts benchmarks/transcripts \
  --min-tasks 100
```

Reports land in `artifacts/benchmark_report/` (JSON + Markdown + HTML).
Same-task-set baselines only — different task-set hashes are rejected.

**Release export (human gate — no bypass):**

```bash
python scripts/create_release_approval_template.py
# fill in reviewer / approval_id / approved_at in human_approval.json
python scripts/export_verified_bundle.py --approval human_approval.json
```

---

## 5. Project structure

```text
src/mind3/
  core/verifier.py        # SiliconSignoffVerifier + all gates (THE authority — one impl per gate)
  core/driver.py          # 10-phase pipeline, strict parser, repair loop, hash-chained trace
  core/contracts.py       # InterfaceContract, RTL + harness generators (SVA bind, SBY cfg, Verilator TB, SDC)
  core/formal_templates.py# Typed BMC property DSL (depth 25; unsupported → UNSUPPORTED_FORMAL_PROPERTY)
  core/failure_taxonomy.py# 12 failure categories
  core/release.py         # ArtifactReleaseBundle (8 fields + approval hash binding)
  core/power.py, dft.py, assurance.py, cache.py, dataset.py
  benchmarks/runner.py + reproducibility.py + baselines.py
  sandbox/bwrap.py (Linux) / macos.py (Seatbelt) / remote_eda.py / eda_commercial.py
  eda/smoke_test.py + tcl_templates.py
  soc/interconnect.py | skills/registry,router,models.py | cli.py | pdata/sky130/
benchmarks/
  tasks.jsonl (50) | heldout/tasks.jsonl (120) + manifest | development-20/ (20) | transcripts/ (50 fixtures, NOT metrics)
tests/ (30 files + negative_controls/ 16 broken designs + fixtures/)
docs/ benchmarks.md, performance-criteria.md, parser_modes.md, gate2_formal.md, cdc_gate6.md, linux_verification.md
tools/check_readiness.sh, install_oss_cad_suite.py
scripts/ (20 one-off audit runners, not installed)
skill/ (2 prompt packs: semiconductor-VLSI, industry-report-analyst)
examples/run_full_flow.py   # DEMO ONLY — mock fallback on, do not benchmark with this
bin/mind3                   # shim → python3 -m mind3.cli
```

Key config: `pyproject.toml` (`mind3==3.1.0`, deps only `httpx/pydantic/PyYAML`), `pytest.ini`, `pyrightconfig.json`.

---

## 6. Performance criteria (what "good" would look like)

From `docs/performance-criteria.md` — none of these tiers have been reached:

| Tier | Functional | Full-verified | Status |
|---|---|---|---|
| Experimental | — | — | **We are here.** |
| Useful-specialist | ≥70% | ≥40% | Not reached (measured: 0%). |
| Strong | ≥80% | ≥60% | Not reached. |
| Tapeout-assist | ≥85% | ≥70% | Not reached — and still wouldn't mean tapeout signoff. |

Release eligibility = ≥100 real heldout tasks + Stage 2b thresholds. Diagnostic runs (<100 tasks) don't count, no matter how good they look.

## 7. Security boundary

- Sandboxed execution required (bwrap / Seatbelt). No silent downgrade.
- SSH remote EDA uses pinned host keys, never `StrictHostKeyChecking=no`.
- `OPENROUTER_API_KEY` via env only. OpenRouter = WAN egress; loopback Ollama (`127.0.0.1:11434`) is the loopback-only default with `LOOPBACK_ONLY_NO_EGRESS` chain.
- Path-traversal guards on. Tampered evidence / forged approvals / replayed hashes are rejected and tested (`tests/test_integrity_and_adversarial.py`).

See `SECURITY.md`.

---

## 8. For the next AI reading this (what to do first)

1. Read `KNOWN_LIMITATIONS.md` before believing any number in any other file.
2. Run `./bin/mind3 smoke-test` and `python -m pytest -q -m 'not eda'` to ground yourself.
3. To move the needle: fix the **generator→parser contract** (prompt template emits prose, strict parser wants exactly-one-module or JSON actions). That's where the 0% lives — not in the gates.
4. Then run a real ≥100-task heldout evaluation with a capable model. Until that exists, there is no accuracy claim. Period.
5. Don't "fix" Gate 6 by stubbing CDC. Either get a CDC-capable Yosys or keep `CDC_TOOLING_UNAVAILABLE` failing closed.
6. Pick a `LICENSE`. Add `results/`, `artifacts/`, `*.whl`, `.env` to `.gitignore`. Fix the `cli.py` docstring. Delete or label `FINAL_VERIFICATION_AUDIT.md` as superseded.
