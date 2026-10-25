# Mind 3.0

**A fail-closed verification workbench for LLM-generated RTL.**

Mind 3.0 asks a model for SystemVerilog, then tries to *disprove* it through a
deterministic 11-phase pipeline and seven verification gate checks. Missing
tools, skipped gates, and unproven properties are reported as missing — never
silently upgraded to a pass.

[![CI](https://github.com/sagniksengupta24/Mind-3.0/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sagniksengupta24/Mind-3.0/actions/workflows/ci.yml)
[![Live EDA](https://github.com/sagniksengupta24/Mind-3.0/actions/workflows/eda_live.yml/badge.svg?branch=main)](https://github.com/sagniksengupta24/Mind-3.0/actions/workflows/eda_live.yml)
![Status](https://img.shields.io/badge/status-experimental-orange)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

> **Status: experimental.** The verifier is real and has live evidence. The
> generator is not: the last measured run scored **0% full-verified (0/20 dev,
> 0/42 heldout)** with the default local model, mostly because the strict parser
> rejects prose-wrapped output before any gate runs. No release-eligible
> benchmark has ever been run. A green result means "the configured live checks
> passed on this run" — it is **not** tapeout, foundry, or production signoff.

---

## Contents

- [See it work](#see-it-work)
- [What this is / is not](#what-this-is--is-not)
- [Verified status](#verified-status)
- [Quickstart](#quickstart)
- [How verification works](#how-verification-works)
- [Evidence model](#evidence-model)
- [Benchmarks](#benchmarks)
- [Repository map](#repository-map)
- [Configuration](#configuration)
- [Limitations](#limitations)
- [Security boundary](#security-boundary)
- [Documentation](#documentation)
- [Troubleshooting](#troubleshooting)
- [Verifying a claim](#verifying-a-claim)
- [Contributing](#contributing)
- [License](#license)

---

## See it work

From a checkout, with the EDA binaries on `PATH` for the second command
(`pytest` alone needs no EDA):

```bash
pip install -e '.[dev]'

# Runs 16 intentionally broken designs; 15 must be caught at the exact gate.
# The 16th (timing) skips without a liberty file.
./bin/mind3 negative-controls

# 525 unit/integration tests; the 59 live-EDA tests are deselected by marker.
python -m pytest -q -m 'not eda'
```

The interesting line is the negative-control summary:

```text
[PASS] cdc_violation  -> expected=CDC_VIOLATION, observed=CDC_VIOLATION
...
Overall Negative-Control Verdict: SUCCESS
```

That is a real tool failure, not a mock: each control is a bug that *must* be
caught, and a control that passes for the wrong reason is a test failure.

## What this is / is not

| This is | This is not |
|---|---|
| A strict gate harness that refuses to certify RTL it could not check | A Verilog generator you can rely on today |
| A tamper-evident run record (SHA-256 hash-chained trace + tool versions) | A PKI attestation or signed provenance system |
| A bounded BMC checker (SymbiYosys + Z3, depth 25 typed-property subset) | An unbounded/liveness formal verification suite |
| A local-first pipeline (loopback Ollama by default) | A cloud service; `openrouter` is opt-in WAN egress |
| A research artifact with explicit, timestamped evidence | Tapeout signoff, production EDA, or a benchmark leaderboard entry |

Target domain: small-to-medium IP blocks — FIFOs, arbiters, counters, FSMs,
bus peripherals, protocol adapters. **11 phases · 7 gate checks · 12 failure
classes · 584 tests.**

**Who it's for:** verification/EDA engineers and researchers who need an
auditable answer to "is this generated RTL safe to use?" — not teams looking for
a faster code generator. The interesting output is the failure report, not the
Verilog.

## Verified status

**Evidence snapshot: 2026-10-26** on macOS 26.6.1 / Python 3.14.7, at commit
`fc04f82` plus the test/type fixes in the commit that added this file. Re-run
the command in the last column; if a number here disagrees with your run, your
run wins.

| Check | Result | Reproduce |
|---|---|---|
| Non-EDA suite | **525 passed, 59 deselected** (584 collected) | `python -m pytest -q -m 'not eda'` |
| Negative controls | **15/16 caught at the expected gate, 1 skipped** (`timing_violation`: no liberty file); verdict `SUCCESS` | `./bin/mind3 negative-controls` |
| EDA smoke | **4/5 tools OK** — Yosys 0.69+post, Verilator 5.052, SBY 0.69 + Z3, OpenSTA 3.1.0; `openroad` missing | `./bin/mind3 smoke-test` |
| Readiness gate | **13/13 checks pass**, verdict `EXPERIMENTAL` (live EDA not opted in) | `bash tools/check_readiness.sh` |
| Live EDA (Linux CI) | Negative controls `SUCCESS`; **8 EDA tests passed, 51 skipped** (hosted runner has no Bubblewrap namespaces); `cdc_execution_result: passed` | [Live EDA run](https://github.com/sagniksengupta24/Mind-3.0/actions/workflows/eda_live.yml) |
| Generator, last measured (2026-10-02) | **0/20 dev, 0/42 on a partial heldout run (42/120 transcribed), 0% full-verified**; 19/20 and 41/42 failures are `RESPONSE_PARSE_FAILURE` | [`docs/benchmarks.md`](docs/benchmarks.md) |
| Release-eligible accuracy | **None exists.** Requires ≥100 real heldout tasks plus the release thresholds | [`docs/performance-criteria.md`](docs/performance-criteria.md) |
| CI | `unit` job: pytest + pyright on Python 3.11 and 3.12; Live EDA workflow runs the EDA-marked suite + negative controls on Ubuntu | [Actions](https://github.com/sagniksengupta24/Mind-3.0/actions) |

Two things this snapshot deliberately does **not** claim:

1. **No accuracy number for the generator.** `0%` is a diagnostic on 62
   transcripts, not a benchmark result. The 20-task dev set overlaps the 120-task
   heldout set, so heldout cleanliness is `[UNVERIFIED]`.
2. **No CDC/OpenROAD signoff.** Gate 6 runs a pinned *structural* checker when
   no external CDC tool is present (it caught the CDC negative control on this
   host); Gate 5 has no `openroad` binary here and is `[PENDING-HUMAN]`.

## Quickstart

**Requirements:** Python ≥3.11; `yosys`, `verilator`, `sby` (+ Z3), and
`opensta` on `PATH` for the live gates; Linux + Bubblewrap, or macOS + Seatbelt,
for sandboxed runs. Missing tools fail closed — they are never mocked.

```bash
git clone https://github.com/sagniksengupta24/Mind-3.0.git
cd Mind-3.0
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

`./bin/mind3` works straight from a checkout (it sets `PYTHONPATH=src`); the
`pip install` is only needed for `python -m mind3...` entry points and `pyright`.

**Verify the harness, in order of increasing cost:**

```bash
./bin/mind3 smoke-test                # are the EDA binaries real and functional?
python -m pytest -q -m 'not eda'      # no EDA needed
./bin/mind3 negative-controls         # do the gates catch known-bad RTL?
bash tools/check_readiness.sh         # evidence summary + verdict
```

Live EDA (Linux or a prepared macOS host):

```bash
MIND3_RUN_LIVE_EDA=1 bash tools/check_readiness.sh
python -m pytest -q                   # includes the `eda` marker
```

**Provision the OSS CAD suite (Linux)** — Yosys, Verilator, SBY, OpenSTA:

```bash
python tools/install_oss_cad_suite.py --tag 2026-09-29
# or, inside the container image:
docker build -f Dockerfile.eda -t mind3-eda .
docker run --rm mind3-eda pytest -q -m 'not eda'   # smoke
docker run --rm mind3-eda pytest -q -m 'eda'       # live EDA
```

The `mind3-eda` image defaults to non-EDA tests so it is safe to run without a
mounted PDK; pass `-m eda` explicitly when you want the live suite.

## How verification works

Every candidate RTL file goes through 11 recorded phases:

```
INTAKE → ROUTE → SNAPSHOT → MODEL_CALL → PARSE → POLICY_CHECK
      → EXECUTE → OBSERVE → VERIFY → REPAIR_OR_FINISH → TRACE
```

Each phase emits an event into a SHA-256 hash-chained trace, together with tool
versions and artifact hashes. A failure is mapped into one of 12 categories
(`failure_taxonomy.py`) — no `UNKNOWN` bucket is silently treated as success.

**Gate checks, in execution order, fail-fast:**

| # | Gate | Real tool | Proves | If unavailable |
|---|---|---|---|---|
| 1 | Elaboration & latch trap | Yosys | RTL parses, elaborates, has no inferred latch / combinational loop | Fails closed |
| 1b | Logic equivalence (opt-in) | Yosys `lec` | Behavioral RTL ≡ synthesized netlist | Skipped unless `require_lec` |
| 3 | Simulation & coverage | Verilator | Testbench behavior + branch/toggle coverage | Fails closed |
| 2 | Formal BMC | SymbiYosys + Z3 | Typed bounded properties, depth 25; vacuous-only contracts abort | Fails closed |
| 4 | Multi-corner timing | OpenSTA | Setup/hold against a real liberty file | Fails closed without a real PDK liberty |
| 5 | Place & route (opt-in) | OpenROAD | Synthesizable, placeable, routed netlist | Skipped unless `require_pnr` |
| 6 | CDC | external `yosys cdc` → `crux` → pinned structural checker | Clock-domain crossings / unsafe direct paths | Blocks if no backend; chosen backend is announced |
| — | DFT scan audit (advisory) | — | Scan-readiness hints | Never blocks signoff |

`SiliconSignoffVerifier` is the single authority: one implementation per gate.
It returns `silicon_verified=False` if any non-optional gate was skipped or
simulated, so a mock can never be reported as a verified run.

**Result semantics.** A gate is `passed`, `failed`, `skipped` (opt-in /
contract-declared no-CDC), or `not_run` (an earlier gate failed first). Missing
tools produce an explicit blocked/skip reason (`CDC_TOOLING_UNAVAILABLE`,
`ENVIRONMENT_FAILURE`), never a silent pass. `silicon_verified` is the only
field to trust for "all configured live checks passed"; the per-gate reports are
where the reasons live.

## Evidence model

- **Real** — produced by a live tool invocation in this run.
- **Fixture** — checked-in transcript/artifact, explicitly excluded from metrics.
- **Mock** — allowed only by the demo `examples/run_full_flow.py`; the benchmark
  path hard-blocks it (`allow_mock_fallback=False`) and mock outcomes are never
  counted as performance.

Benchmarks enforce the same task-set hash, reject cross-task-set baselines, and
refuse to open a holdout suite without `--unseal` plus a matching manifest hash.
Release export (`ArtifactReleaseBundle`) binds eight immutable fields and a human
approval record to the SHA-256 of `benchmark_summary.json`; a missing, altered,
or stale approval blocks the export.

## Benchmarks

| Suite | Tasks | Purpose |
|---|---|---|
| `benchmarks/tasks.jsonl` | 50 | Smoke/diagnostic corpus |
| `benchmarks/development-20/` | 20 | Diagnostic subset (overlaps heldout — not clean) |
| `benchmarks/heldout/` | 120 | Sealed evaluation set (`heldout-v1`) |
| `benchmarks/transcripts/` | 50 fixtures | Parser/evaluator tests — **not** metrics |

**Release tiers** ([`docs/performance-criteria.md`](docs/performance-criteria.md)):

| Tier | Functional | Full-verified | Status |
|---|---:|---:|---|
| Experimental | report only | report only | **current** |
| Useful specialist | ≥70% | ≥40% | not reached (measured 0%) |
| Strong specialist | ≥80% | ≥60% | not reached |
| 9/10 claim | ≥85% | ≥70% | not reached |

A tier also requires ≥100 real heldout tasks, negative controls, and (for the
higher tiers) independent repetition and human review. Diagnostic runs under 100
tasks never qualify, regardless of the score.

```bash
# Dry run: prerequisites, tier, parser mode. No inference.
python -m mind3.benchmarks.runner --dry-run

# Real run (requires Ollama or an API key; ≥100 tasks for release eligibility).
python -m mind3.benchmarks.runner \
  --model qwen2.5-coder:7b --provider ollama \
  --max-repairs 3 --min-tasks 100

# Re-score saved transcripts without re-running generation.
python -m mind3.benchmarks.runner --evaluate-existing \
  --transcripts benchmarks/transcripts --min-tasks 100
```

Reports land in `artifacts/benchmark_report/` (JSON + Markdown + HTML). The CLI
equivalent is `./bin/mind3 benchmark --help`; its default suite is
`development-20` and it refuses heldout paths without `--unseal`.

**Release export (human gate, no bypass):**

```bash
python scripts/create_release_approval_template.py
# fill reviewer / approval_id / approved_at, then:
python scripts/export_verified_bundle.py --approval human_approval.json
```

## Repository map

```text
src/mind3/
  cli.py                    # benchmark | smoke-test | negative-controls
  core/
    driver.py               # 11-phase pipeline, parser, repair loop, hash-chained trace
    verifier.py             # SiliconSignoffVerifier — the single gate authority
    contracts.py            # interface contracts + TB/SVA/SBY/SDC generators
    formal_templates.py     # typed bounded-property DSL (depth 25)
    failure_taxonomy.py     # 12 categories
    release.py              # ArtifactReleaseBundle + approval binding
    power.py dft.py assurance.py cache.py dataset.py vcd_evidence.py
  benchmarks/               # runner, reproducibility, baselines, task mining
  sandbox/                  # bwrap (Linux), seatbelt (macOS), remote EDA, commercial
  eda/                      # smoke test + TCL templates
  soc/ | skills/ | pdata/
tools/cdc_checker/          # pinned structural CDC checker (Gate 6 fallback)
tools/check_readiness.sh    # evidence summary + verdict
benchmarks/                 # 50 smoke / 20 dev / 120 heldout / 50 fixtures
tests/                      # 59 files incl. negative_controls/ (16 broken designs)
docs/                       # normative design + evidence notes
scripts/                    # one-off audit/benchmark runners (not installed)
examples/run_full_flow.py   # demo only — mock fallback ON
bin/mind3                   # checkout shim → python -m mind3.cli
```

Runtime deps are deliberately small: `httpx`, `pydantic`, `PyYAML`. Python ≥3.11;
CI covers 3.11 and 3.12, local development is on 3.14.

## Configuration

Environment variables that change verification behavior. Defaults are chosen so
the strict path is the default; "off" flags only ever *weaken* evidence, and a
weakened run is recorded as such.

| Variable | Default | Effect |
|---|---|---|
| `MIND3_RUN_LIVE_EDA` | unset | Opt in to live EDA in `check_readiness.sh` (otherwise `EXPERIMENTAL`) |
| `MIND3_LIBERTY_PATH` | unset | Real liberty file for Gate 4 (a stub is not sufficient) |
| `MIND3_GATE_FIXES` | **on** | Gate-1 partial-reset trap and formal compiler fixes |
| `MIND3_EVIDENCE_V2` | off | VCD witness decoding + sensitivity guard in repair |
| `MIND3_SKIP_UNCHANGED` | off | Skip a repair turn when RTL is byte-identical |
| `MIND3_REPAIR_MODE` | `r1` | `r2` = anti-anchoring regeneration |
| `MIND3_REPAIR_INVARIANTS` | off | Restate synthesis invariants in repair prompts |
| `MIND3_CDC_NO_FALLBACK` / `MIND3_CDC_NO_CRUX` | off | Disable CDC fallbacks entirely (fail closed sooner) |
| `MIND3_WRITE_RESULTS` | off | Allow tracked writes under `results/` during audit scripts |
| `OPENROUTER_API_KEY` | unset | Required only for `--provider openrouter` (WAN egress) |

## Limitations

[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) is **normative** — if a claim in
any other file contradicts it, the claim is the bug. The short version:

- Generator quality is model-dependent; the pinned default produces prose the
  strict parser rejects. Lenient parsing exists but is not equivalent and is not
  measured.
- Formal is bounded (depth 25), no liveness/unbounded proofs; vacuity detection
  is partial.
- OpenROAD (Gate 5) and a CDC-capable external tool are absent on this host.
- Gate 6's structural fallback is rule-based, not a full CDC signoff.
- Heldout cleanliness is `[UNVERIFIED]` (dev set overlaps heldout).
- No license is granted yet (see below).
- `FINAL_VERIFICATION_AUDIT.md` is historical and superseded; `MIND_TASK.md`,
  `MIND_STATE.md`, and `PORT_LOG.md` are working notes, not user docs.

## Security boundary

- **Sandboxed pipeline.** Model-generated RTL runs under Bubblewrap
  `--unshare-all` on Linux or Seatbelt `sandbox-exec` on macOS; a missing
  sandbox fails closed. One explicit exception: the negative-control harness
  records `sandboxed: false` and runs real tools unsandboxed on hosts without
  Bubblewrap — it says so in its output and report rather than pretending
  otherwise.
- **Egress control.** Loopback Ollama (`127.0.0.1:11434`) is the default.
  OpenRouter is explicit opt-in and documented in [`SECURITY.md`](SECURITY.md).
- **No SSH trust shortcuts.** Remote EDA pins host keys; never
  `StrictHostKeyChecking=no`.
- **Tamper evidence.** Path-traversal guards, evidence-hash checks, forged
  approval rejection, and replay rejection are covered by
  `tests/test_integrity_and_adversarial.py`.
- **Credentials** are read from the environment (`OPENROUTER_API_KEY`) and are
  never hardcoded in the repository or written into run artifacts as plaintext.

## Documentation

| Document | Read it when |
|---|---|
| [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | Before believing any number anywhere |
| [`SECURITY.md`](SECURITY.md) | Deploying, or reasoning about trust boundaries |
| [`docs/benchmarks.md`](docs/benchmarks.md) | Evidence tiers, thresholds, Stage 6 results |
| [`docs/parser_modes.md`](docs/parser_modes.md) | Strict vs lenient parsing and why strict fails |
| [`docs/gate2_formal.md`](docs/gate2_formal.md) | Supported property subset and vacuity states |
| [`docs/cdc_gate6.md`](docs/cdc_gate6.md) | CDC contract declarations and backends |
| [`docs/linux_verification.md`](docs/linux_verification.md) | Platform evidence separation and CI limits |
| [`docs/performance-criteria.md`](docs/performance-criteria.md) | What "useful" would require |
| [`CHANGELOG.md`](CHANGELOG.md) | Release-level changes |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ENVIRONMENT_FAILURE` at Gate 4 | No liberty file, or only the 4.8 KB stub | Pass a real PDK `.lib` via `MIND3_LIBERTY_PATH` / `--liberty` |
| `CDC_TOOLING_UNAVAILABLE` at Gate 6 | All CDC backends disabled or failed to start | Unset `MIND3_CDC_NO_FALLBACK` / `MIND3_CDC_NO_CRUX`; install `crux` for the strong backend |
| `openroad` reported missing | Gate 5 is opt-in and OpenROAD is not installed | Install the OSS CAD suite, or accept Gate 5 as `[PENDING-HUMAN]` |
| `bwrap` namespace errors in CI | Hosted runners forbid user-namespace creation | Run live EDA on a prepared Linux host; skip/fail closed is the correct CI outcome |
| `RESPONSE_PARSE_FAILURE` dominates | Model emits prose instead of fenced/JSON RTL | Use a model that follows the format, or opt into lenient parsing (not equivalent evidence) |
| `EXPERIMENTAL` readiness verdict | Live EDA not opted in | `MIND3_RUN_LIVE_EDA=1 bash tools/check_readiness.sh` |

## Verifying a claim

Every number in this README is paired with the command that produced it. If you
want to audit the project rather than use it:

1. `bash tools/check_readiness.sh` — mechanized claim check, prints a verdict.
2. `./bin/mind3 negative-controls --require-live` — fails if any control skips.
3. `python -m pytest -q` on a prepared EDA host — the full suite.
4. `git log` — every gate fix is a separate, reviewable commit.

## Contributing

1. Read [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) before changing a claim.
2. Local parity with CI:
   ```bash
   pip install -e '.[dev]'
   python -m pytest -q -m 'not eda'
   pyright src
   ```
3. Any change to a gate needs a test that proves the gate *fails* when it
   should — a negative control or a mutant. Passing tests alone are not
   evidence that a gate works.
4. Never hand-edit files under `results/` or `artifacts/`; regenerate them with
   the script that produced them.

Because no license has been chosen yet, please open an issue before sending a
patch — the terms for accepting contributions are undefined until then.

## License

**No license is granted.** There is no `LICENSE` file; the owner must choose
terms (`[PENDING-HUMAN]`). Until then, treat the code as all-rights-reserved.
Issues and discussion are welcome; redistribution is not permitted without a
license.
