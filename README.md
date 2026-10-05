# Mind 3.0: Fail-Closed RTL Generation & Verification Workbench

Mind 3.0 is a fail-closed workbench for generating small-to-medium SystemVerilog IP and checking it through an auditable verification pipeline. The intended sweet spot is blocks such as FIFOs, arbiters, counters, DMA/control blocks, bus peripherals, protocol adapters, and control FSMs.

> [!IMPORTANT]
> Mind 3.0 is **not** a foundry, production, or tapeout signoff system. A green `SiliconSignoffVerifier` result only means the configured live checks passed for that run. LLM generation remains non-deterministic; every performance claim must come from real, versioned benchmark evidence.

## 1. Implemented

Mind 3.0 is an evidence-backed, fail-closed SystemVerilog IP generation and verification workbench. The implemented capabilities include:

### Deterministic execution and evidence pipeline
- **10-Phase Pipeline**: `INTAKE` → `ROUTE` → `SNAPSHOT` → `MODEL_CALL` → `PARSE` → `POLICY_CHECK` → `EXECUTE` → `OBSERVE` → `VERIFY` → `REPAIR_OR_FINISH` → `TRACE`.
- **Audit Trails**: Every execution produces a hash-chained internal trace record (deterministic SHA-256 chain, tamper-evident but not a PKI/hardware attestation), preserved RTL, structured verification evidence, tool versions, and artifact hashes.
- **Fail-Closed Gate Philosophy**:
  ```text
  REAL TOOL    → REAL RESULT
  MISSING TOOL → EXPLICIT SKIP/BLOCK
  MOCK         → NEVER PRESENTED AS VERIFIED
  ```
- **Bounded Repair**: Repair loops are constrained by budget, edit scope, and strict failure evidence; runaway rewrites are rejected.

### Six validation gates
- **Gate 1 — Elaboration & Syntax (Yosys)**: Full hierarchy elaboration, strict `$dlatch` / latch detection, and combinational loop detection.
- **Gate 1b — LEC (Yosys)**: Logic equivalence checking for synthesis transformations (opt-in).
- **Gate 3 — Simulation & Coverage (Verilator)**: Cycle-accurate C++ testbench execution with statement, toggle, and branch coverage measurement.
- **Gate 2 — Formal Verification (SymbiYosys + SMT)**: Bounded Model Checking (BMC) with deterministic typed formal-property templates.
- **Gate 4 — Static Timing Analysis (OpenSTA)**: Setup/hold slack validation against target technology Liberty (.lib) files.
- **Gate 5 — Physical Signoff (OpenROAD)**: Opt-in macro placement and routing checks.
- **Gate 6 — Clock Domain Crossing (Yosys CDC)**: Formal structural analysis of asynchronous clock crossings; missing CDC tooling fails closed.

> [!NOTE]
> **Execution Order & Reporting**:
> Actual execution proceeds sequentially: Gate 1 → Gate 1b → Gate 3 → Gate 2 → Gate 4 → Gate 5 → Gate 6. Verification fails closed on the first violation. Consequently, if an earlier gate (such as Gate 3) fails, Gate 2 is not executed and is not recorded in the result reports.

### 12-Category Failure Taxonomy
Deterministic mapping from raw tool stderr/stdout and structured evidence into canonical machine-readable categories:
`SPECIFICATION_ERROR`, `RTL_SYNTAX_ERROR`, `RTL_SEMANTIC_ERROR`, `SIMULATION_FAILURE`, `FORMAL_FAILURE`, `TIMING_FAILURE`, `CDC_FAILURE`, `COVERAGE_FAILURE`, `REPAIR_FAILURE`, `ENVIRONMENT_FAILURE`, `TIMEOUT`, `UNKNOWN`.

### Negative-Control Suite
16 intentionally broken designs with pre-declared expected failure gates located in `tests/negative_controls/`:
1. `latch_inference.sv` (Gate 1: `LATCH_INFERRED`)
2. `combinational_loop.sv` (Gate 1: `COMBINATIONAL_LOOP`)
3. `incorrect_reset_behavior.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
4. `reset_deassertion_problem.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
5. `cdc_violation.sv` (Gate 6: `CDC_VIOLATION`)
6. `fifo_overflow.sv` (Gate 3: `SIMULATION_FAILURE`)
7. `fifo_underflow.sv` (Gate 3: `SIMULATION_FAILURE`)
8. `off_by_one_counter.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
9. `incorrect_handshake.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
10. `incorrect_fsm_transition.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
11. `width_truncation.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
12. `signed_unsigned_error.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
13. `timing_violation.sv` (Gate 4: `TIMING_SLACK_VIOLATION`)
14. `false_formal.sv` (Gate 2: `FORMAL_INVARIANT_BREACH`)
15. `sim_behavioral_failure.sv` (Gate 3: `SIMULATION_FAILURE`)
16. `coverage_deficit.sv` (Gate 3: `COVERAGE_DEFICIT`)

### Real Held-Out Benchmark Framework
- **Heldout-v1 Suite**: 120 real RTL tasks (`benchmarks/heldout/tasks.jsonl`) with immutable SHA-256 manifest (`bae56a8db36a0f3d47f6bef1c2ec325bdd1e14dd16addb68461a1b59dbdd2c24`).
- **13 Design Families**: Counters, FIFOs, Arbiters, FSMs, UART, SPI, Register interfaces, APB peripherals, AXI interfaces, DMA blocks, CDC-sensitive modules, Reset-heavy designs, Protocol adapters.
- **Adversarial Scenarios**: Boundary conditions, simultaneous read/write, mid-operation reset, handshake races, signed arithmetic, and parameter width edge cases.
- **Fixture Separation**: 50 development fixtures in `benchmarks/transcripts/` are strictly isolated from held-out benchmark evaluation.

### Three Baselines Comparison
Automated comparison across identical tasks and seeds:
- **Baseline A (Direct 1-shot)**: Spec → Model → RTL → Verification (no repair).
- **Baseline B (Naive repair)**: Spec → Model → RTL → Verification → Unstructured Repair → Verification.
- **Mind 3.0**: Spec → Contract Analysis → RTL → Independent Verification → Structured Evidence → Bounded Repair → Release Gate.

### Release Gate & Human Approval Hard Gate
Enforced via `ArtifactReleaseBundle` in `src/mind3/core/release.py`. A release bundle requires all 8 immutable components:
1. `bundle_id`
2. `rtl`
3. `specification`
4. `verification_evidence`
5. `tool_versions`
6. `run_id`
7. `commit_sha`
8. `evidence_hash` + cryptographic `approval_record`
Any missing, altered, or unapproved component immediately blocks release.

---

## 2. Verified Locally

The following capabilities have been genuinely executed and verified on the local host environment:

- **Full Pytest Suite**: **297 passed, 5 skipped** on the macOS host (environment skips: OpenROAD binary missing, `bwrap` Linux-only, SkyWater PDK-gated canaries). Zero failures. Inside the `mind3-test` Docker container (no EDA stack): 199 passed, 13 skipped.
- **Security & Anti-Tamper Tests**: Verified rejection of tampered evidence dictionaries, forged approval hashes, replayed stale hashes, missing release components, and mock results masquerading as verified (`tests/test_integrity_and_adversarial.py`).
- **Reproducibility Test Suite**: Verified deterministic run hashing, manifest verification, and baseline metrics computation (`tests/test_benchmark_reproducibility.py`).
- **EDA Toolchain Smoke Test**: Live probe via `./bin/mind3 smoke-test` verifying local binaries:
  - Yosys `0.69+post` (elaboration & netlist optimization smoke verified)
  - Verilator `5.052` (syntax & lint smoke verified)
  - SymbiYosys `0.69` with Z3 SMT solver (BMC formal pass verified)
- **Negative-Control Execution**: Ran live against host EDA tools (`./bin/mind3 negative-controls`). 14 negative controls caught at the exact expected failure gates; 2 cleanly skipped with explicit environment provenance.
- **Held-Out Diagnostic Benchmark Runs (Stage 6)**: Live `ollama / qwen2.5-coder:7b` runs with the strict parser (seed 42): 20/20 real development transcripts (`artifacts/stage6_dev20/`) and a 42/120 partial heldout run (`artifacts/stage6_heldout/`), both 0 full-verified. Both are **diagnostic, not release-eligible** (release requires ≥100 real heldout tasks). Earlier `results/summary.json` figures describe an exploratory run, not live-inference evidence under the current runner, and are superseded by the Stage 6 diagnostic result.
- **Packaging**: Wheel cleanly built via `pip wheel --no-deps --no-build-isolation -w dist .` yielding `dist/mind3-3.1.0-py3-none-any.whl`.
- **Docker Test Container**: `mind3-test` image re-verified this stage (`docker run --rm mind3-test pytest -q`): 199 passed, 13 skipped (EDA-gated tests skip without a Linux EDA stack).

---

## 3. Requires EDA Environment

The following features require the full Linux OSS CAD Suite environment and are cleanly skipped on macOS or unprovisioned hosts:

- **OpenSTA / Gate 4 Timing**: Requires `sta` / `opensta` binary and target Liberty (.lib) libraries.
- **OpenROAD / Gate 5 Physical**: Requires `openroad` binary and SkyWater 130nm / equivalent PDK flow.
- **Yosys CDC / Gate 6**: Requires a Yosys build exposing the `cdc` command. Executed Stage 5 evidence shows it absent from both the macOS Homebrew build and the pinned OSS CAD Suite `2026-09-29` linux-arm64 build (`yosys -p "help cdc"` → `No such command or cell type: cdc` in both); other builds untested. Gate 6 fails closed as `CDC_TOOLING_UNAVAILABLE` when absent.
- **Bubblewrap Sandbox**: Requires Linux kernel user namespace support (`bwrap`).

For a fully provisioned environment, build and run via Docker:
```bash
docker build -f Dockerfile.eda -t mind3-eda .
```

---

## 4. Benchmark Results

Stage 6 diagnostic evidence (`ollama / qwen2.5-coder:7b`, strict parser, seed 42) — **diagnostic, NOT release-eligible**:

| Metric | Development-20 (20 real transcripts) | Heldout partial (42/120 real transcripts) |
|---|---|---|
| **Initial pass** | 0/20 (0.0%, Wilson CI [0.0%, 16.1%]) | 0/42 (0.0%, Wilson CI [0.0%, 8.4%]) |
| **Functional pass** | 0/20 | 0/42 |
| **Full verified pass** | **0/20** | **0/42** |
| **Repair success** | 0/20 | 0/42 |
| **Failure split** | 19 `RESPONSE_PARSE_FAILURE`, 1 `SPECIFICATION_ERROR` | 41 `RESPONSE_PARSE_FAILURE`, 1 `SPECIFICATION_ERROR` |
| **Evidence tier** | `diagnostic` | `diagnostic` |

Release eligibility requires ≥100 real heldout tasks plus the Stage 2b thresholds; it is not established. Do not read the 20/42 diagnostic figures as a final accuracy claim. The strict parser rejects this model's typical formatting (prose-wrapped modules), which dominates the failure split; see `docs/parser_modes.md` and `KNOWN_LIMITATIONS.md`.

---

## 5. Not Yet Demonstrated

To maintain strict scientific integrity, the following claims are **not** made:

- **Foundry Signoff / Tapeout Ready**: Mind 3.0 is an RTL generation and verification workbench, not an ASIC tapeout signoff tool.
- **Physical Closure on Complex SoCs**: Automated placement, routing, and DRC/LVS closure on multi-million gate hierarchies has not been evaluated.
- **Unconstrained Asynchronous CDC Closure**: Asynchronous crossings without explicit SDC constraints or synchronization templates are not guaranteed.
- **Frontier LLM Live Pass Rate**: Live API inference across paid proprietary models (e.g., Claude 3.5 Sonnet, GPT-4o) on the full 120-task suite without mock provider mediation remains to be executed in an automated evaluation harness with live API keys.

The current workflow pins the OSS CAD Suite release tag `2026-09-29` (see https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-29).

## Benchmark usage

Dry-run the live environment check:

```bash
python -m mind3.benchmarks.runner --dry-run
```

Require every live prerequisite:

```bash
python -m mind3.benchmarks.runner --dry-run --require-live
```

Run real tasks on a prepared Linux host:

```bash
python -m mind3.benchmarks.runner \
  --model "your-model" \
  --provider "ollama" \
  --max-repairs 3 \
  --min-tasks 100
```

Evaluate an existing transcript directory without re-running generation:

```bash
python -m mind3.benchmarks.runner \
  --evaluate-existing \
  --transcripts benchmarks/transcripts \
  --min-tasks 100
```

Reports are written to `artifacts/benchmark_report/` as JSON, Markdown, and HTML. Same-task-set baselines can be supplied with `--baselines baselines.json`; different task-set hashes are rejected. A baseline row contains its name, exact task-set SHA-256, task count, measured functional/full-verified rates, and source.

## Readiness checker

```bash
tools/check_readiness.sh
```

This intentionally returns **experimental** when live EDA has not been executed. For a live environment:

```bash
MIND3_RUN_LIVE_EDA=1 tools/check_readiness.sh
```

The readiness checker will not infer performance from unit tests or the 50 mock fixtures.

### Human approval before release export

A release evidence bundle requires a real benchmark result and a human approval file bound to the exact SHA-256 of `benchmark_summary.json`. The exporter refuses to run when the evidence threshold or approval hash does not match:

```bash
python scripts/create_release_approval_template.py
# Replace reviewer / approval_id / approved_at in human_approval.json.
python scripts/export_verified_bundle.py --approval human_approval.json
```

## Security boundary

Mind 3.0 requires sandboxed local execution (Bubblewrap on Linux; Seatbelt `sandbox-exec` on macOS) and does not silently downgrade to an unsandboxed executor. SSH-based remote EDA uses configured host-key pins rather than disabling host-key checks. Required EDA failures are explicit and fail closed.

## Project structure

```text
.
├── benchmarks/
│   ├── tasks.jsonl
│   └── transcripts/                  # schema fixtures only; excluded from metrics
├── docs/
│   ├── benchmarks.md
│   ├── performance-criteria.md
│   └── phase4_readiness.md
├── scripts/
│   ├── run_negative_controls.py
│   └── export_verified_bundle.py
├── tools/
│   ├── check_readiness.sh
│   └── install_oss_cad_suite.py
├── src/mind3/
│   ├── benchmarks/runner.py
│   ├── core/
│   │   ├── contracts.py
│   │   ├── driver.py
│   │   ├── formal_templates.py
│   │   ├── release.py
│   │   └── verifier.py
│   ├── sandbox/
│   └── ...
└── tests/
    ├── negative_controls/
    └── ...
```

## Development

Python 3.11 is the project baseline. Run the non-EDA suite on a development machine without the live EDA stack:

```bash
python -m pytest -q -m 'not eda'
```

Run the complete suite on a Linux host with the pinned EDA environment:

```bash
python -m pytest -q
```
