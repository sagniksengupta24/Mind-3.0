# Mind 3.0: Fail-Closed, Auditable Verification Loop for LLM-Generated RTL

Mind 3.0 is a fail-closed verification loop and multi-gate audit harness for LLM-generated SystemVerilog RTL. It pairs generative language models with rigorous, automated open-source EDA verification gates (compilation, static latch/loop linting, cycle simulation, and formal bounded model checking).

> [!IMPORTANT]
> **Deterministic Tool Execution vs. Non-Deterministic Model Generation**:
> Mind 3.0's verification oracles, tool harnesses, and cryptographic trace ledgers are strictly deterministic and fail-closed. However, LLM text generation is inherently non-deterministic. Mind 3.0 makes zero claim of autonomous tapeout signoff or guaranteed convergence. It is **not a tapeout-signoff system**. All claims are bounded strictly by empirically measured evidence.

## Key Architecture & Guarantees

- **11-Phase Deterministic Execution Engine**:
  `INTAKE` → `ROUTE` → `SNAPSHOT` → `MODEL_CALL` → `PARSE` → `POLICY_CHECK` → `EXECUTE` → `OBSERVE` → `VERIFY` → `REPAIR_OR_FINISH` → `TRACE`
- **6-Gate OSS RTL & Physical Validation Flow**:
  - **Gate 1: Yosys Elaboration & Latch Trap**: Catches unapproved inferred latches via structured JSON AST inspection and combinational loops.
  - **Gate 1b: Logic Equivalence Checking (LEC)**: Formally proves equivalence between behavioral RTL and synthesized netlists via Yosys `equiv_status -assert`.
  - **Gate 2: SymbiYosys (SBY) Formal BMC**: Bounded model checking (depth 25) with counterexample trace isolation.
  - **Gate 3: Verilator 5.x Coverage**: Line, branch, and toggle coverage thresholds with pseudo-random Galois LFSR and walking-1 stimulus.
  - **Gate 4: OpenSTA Multi-Corner Timing Signoff**: Setup ($WNS \ge 0$ ps, $TNS \ge 0$) and hold slack verification across declared PVT corners.
  - **Gate 5: OpenROAD Place-and-Route (opt-in)**: Physical design validation detecting placement overflow and global routing congestion.
  - **Gate 6: Yosys CDC Static Analysis**: Asynchronous clock-domain crossing detection.
  - **DFT Scan Advisory Audit**: Automatic DFF count analysis and scan-enable port presence detection (non-blocking).
- **Dynamic Model Discovery & Verification Cache**:
  - `OpenRouterModelRegistry`: Dynamic, fail-closed runtime model catalog discovery with TTL caching (no fabricated model slugs).
  - `ContentAddressedCache`: SHA-256 hash-keyed caching of formal BMC and coverage results across identical snapshots.
  - `FineTuningDatasetExporter`: Exports multi-turn hardware trajectories into standardized JSONL and ShareGPT instruction-tuning datasets.
- **TapeoutReadinessVerifier & CommercialSignoffVerifier**:
  Independent fail-closed evidence auditor for 8 signoff domains: DRC, LVS, STA, CDC, ERC, Formal LEC, DFT, and Power/EM-IR. Supports automated content audits, zero waivers, and native log scraping for Synopsys PrimeTime, Cadence Innovus, Siemens Calibre nmDRC/nmLVS, and ATPG reports.
- **Tier-1 Commercial EDA & Grid Dispatcher Layer**:
  Native TCL generation and batch compute grid dispatchers (LSF `bsub`, Slurm `sbatch`, SGE `qsub`) for Synopsys (DC/FC, PrimeTime, Formality, ICV), Cadence (Genus, Innovus, Tempus, Conformal, Voltus), and Siemens (Calibre, Tessent) with FlexLM license pre-flight monitors.
- **IEEE 1801 (UPF 3.0) Multi-Voltage & Low-Power Engine**:
  Synthesizes complete UPF 3.0 scripts with power domains, power switches, isolation cells, level shifters, retention registers, and Power State Tables (PST).
- **Hierarchical SoC & AMBA Bus Interconnect Generator**:
  Synthesizes AXI5, AXI4-Lite, AHB5, and APB4 crossbar fabrics with address decoding, backpressure steering, SVA Protocol VIP checkers, and foundry SRAM wrappers with MBIST test collars.
- **Industrial DFT & ATPG Flow**:
  Generates 16-state IEEE 1149.1 JTAG TAP controllers, IEEE 1500 embedded core wrappers, and validates ATPG fault coverage against foundry thresholds ($\ge 99.5\%$ stuck-at, $\ge 95.0\%$ transition).
- **Closed-Loop Pareto PPA Optimization**:
  Tracks multi-objective Power, Performance, and Area Pareto frontiers across frequency, slack, power, and area with targeted microarchitectural repair heuristics.
- **Decoupled Multi-Agent Contracts**:
  Decouples the Lead Architect (`InterfaceContract`), RTL Design Engineer (`RTLGenerator`), and Verification Lead (`VerificationHarnessGenerator`) to eliminate tautological testbench hallucinations.
- **Sandboxed Isolation & Fail-Closed Security**:
  Linux Bubblewrap (`bwrap`) isolation with unshared networking and strictly bound directories, path canonicalization traversal guards, and enterprise remote SSH cluster offloading.
- **Atomic Snapshot & Rollback**:
  Complete workspace mirror before any mutations; automatically purges snapshots upon pass or reverts the workspace atomically if the repair budget is exhausted.
- **Cryptographic Audit Chain**:
  Every phase transition writes a canonical SHA-256 chained record to `transcript.jsonl` for compliance and auditability.
- **Domain Skills Subsystem**:
  Packaged `.skill` bundles (`semiconductor-vlsi`, `industry-report-analyst`) loaded and routed dynamically via keyword matrices.

## Project Structure

```text
.
├── examples/
│   └── run_full_flow.py
├── pyrightconfig.json
├── pytest.ini
├── skill/
│   ├── industry-report-analyst.skill
│   └── semiconductor-vlsi.skill
├── src/
│   └── mind3/
│       ├── __init__.py
│       ├── core/
│       │   ├── assurance.py
│       │   ├── cache.py
│       │   ├── contracts.py
│       │   ├── dataset.py
│       │   ├── dft.py
│       │   ├── driver.py
│       │   ├── power.py
│       │   ├── types.py
│       │   └── verifier.py
│       ├── eda/
│       │   ├── __init__.py
│       │   └── tcl_templates.py
│       ├── sandbox/
│       │   ├── bwrap.py
│       │   ├── eda_commercial.py
│       │   └── remote_eda.py
│       ├── skills/
│       │   ├── models.py
│       │   ├── registry.py
│       │   └── router.py
│       └── soc/
│           ├── __init__.py
│           └── interconnect.py
└── tests/
    ├── fixtures/
    │   └── eda_outputs/
    ├── test_assurance.py
    ├── test_cache_and_dataset.py
    ├── test_commercial_eda.py
    ├── test_dft_atpg.py
    ├── test_fixtures_canary.py
    ├── test_mind3.py
    ├── test_power_intent.py
    ├── test_ppa_optimization.py
    └── test_soc_interconnect.py
```

## Generator Model & Signoff Quality

Signoff quality and repair convergence depend heavily on generator model quality. While `PhaseDriver` defaults to `qwen2.5-coder:7b` for local testing, a 7B parameter model is a weak baseline for complex RTL correctness, formal SVA invariant generation, and timing closure. For production VLSI tasks, configure `PhaseDriver(..., model="<more-capable-model>")` or use an enterprise LLM endpoint.

### Repair Budget (`max_repairs`)

The default repair budget is set to `max_repairs=3`. This is a deliberately restrictive, fail-closed ceiling to prevent runaway token expenditure. When using smaller local models (such as 7B models), self-correction across formal counterexamples or setup timing violations typically requires additional iteration; callers should raise `max_repairs` accordingly (e.g., to 6–10). If the repair budget is exhausted, Mind 3.0 automatically rolls back the workspace to its pre-run snapshot.

### EDA Toolchain & Liberty PDK Configuration

`SiliconSignoffVerifier` enforces strict deterministic validation:
- **No Mock Fallback by Default**: `allow_mock_fallback=False` by default. If any required EDA binary (`yosys`, `sby`, `verilator`, `sta`) is missing on the runner, verification immediately fails with `EDA_BINARY_MISSING`.
- **Required Liberty Path**: Callers must explicitly specify `liberty_path` (as a path string or list of corner liberty paths) to support multi-corner timing signoff without hardcoded PDK assumptions.
- **Verification Artifacts**: Formal verification and coverage signoff require corresponding `.sby` and `.cpp` testbench artifacts unless explicitly opted out via `require_formal=False` or `require_coverage=False`.
- **Loopback-Only Inference Endpoint Enforcement**: `PhaseDriver(..., loopback_only=True)` enforces loopback-only inference endpoint enforcement (requiring 127.0.0.1 or localhost, e.g. Ollama, forbidding cloud API providers) and records each transition in a hash-chained, tamper-evident trace record.
- **Parser Canary Fixtures**: Test fixtures in `tests/fixtures/eda_outputs/` are clearly marked synthetic representative samples constructed from documented tool output conventions for unit testing in environments without EDA installations; each file includes exact CLI commands for regeneration against live tools.
- **EDA Version-Drift Canary CI Workflow**: `.github/workflows/eda_version_drift_canary.yml` tests all six signoff gate parsers across a parameterized matrix of pinned tool versions (`baseline_pinned` vs `vnext_pinned` targeting Yosys 0.69+, SBY 0.69+, Verilator 5.050+, OpenSTA 2.7.0+, OpenROAD 2.0+). *Note*: The workflow must run on an environment with live network and tool package installation access to validate full tool-regeneration execution end-to-end; do not assume parser fidelity against unverified future tool updates without running the canary.
- **Gate 6 CDC Tooling Prerequisite**: Gate 6 requires a CDC-capable Yosys build (such as [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build)). Stock distributions from Homebrew (`brew install yosys`) and Debian/Ubuntu (`apt install yosys`) compile Yosys without the external CDC command/plugin. When run against stock Yosys, Gate 6 fails closed with `CDC_TOOLING_UNAVAILABLE` (distinct from a genuine CDC violation); callers without CDC plugins installed must explicitly pass `require_cdc=False` to bypass Gate 6.

## Tapeout-readiness boundary

Passing `SiliconSignoffVerifier` means only that its configured OSS checks passed. It must never be represented as foundry, production, or tapeout signoff. `TapeoutReadinessVerifier` provides a separate, fail-closed evidence checklist for lint, CDC/RDC, equivalence, UPF, DFT, MCMM STA, DRC/LVS, and EM/IR. It validates reports from your qualified EDA/PDK flow; it does not generate or fake them. A design is tapeout-ready only when each required receipt is present and clean, and a qualified signoff team accepts the results.

## Empirical Bounds & Known Limitations

The following metrics reflect actual measured parameters from live empirical execution in this repository:

### Measured Empirical Bounds (Step 1 Baseline & Step 2 Mutation)
* **Evaluated Benchmark Suite:** 10 canonical tasks across 5 categories (`Priority Encoder`, `Gray Counter`, `Signed Multiplier`, `Pipelined Adder`, `Traffic Light Controller`, `Packet Frame Parser`, `Synchronous FIFO`, `SPI Master`, `Two-Phase Handshake`, `CDC Handshake`).
* **Live Evaluated Generator Model:** `qwen2.5-coder:30b` via local Ollama (FP16/Q4 quantization, temperature 0.0, top-p 1.0).
* **Initial Pass Rate (Pass@1):** **20.0%** (2 out of 10 tasks passed on initial generation without repair).
* **Multi-Turn Repaired Pass Rate:** **30.0%** (3 out of 10 tasks converged within a 3-turn repair budget).
* **Unconverged Rate:** **70.0%** (7 out of 10 tasks failed all 3 repair turns).
* **Convergence Drop-off by Turn:**
  - Turn 0 (Pass@1): 2 passes (`priority_encoder`, `signed_multiplier`)
  - Turn 1: 0 passes
  - Turn 2: 1 pass (`cdc_handshake`)
  - Turn 3: 0 passes (exhausted repair budget)
  - *Observation*: 100% of converged repairs occurred by Turn 2; Turn 3 exhibited zero incremental recovery in this suite.
* **Root Failure Modes (Unconverged Tasks):**
  - Functional Invariant / Testbench Failure: 85.7% (6/7 tasks: `gray_counter`, `pipelined_adder`, `traffic_light_controller`, `sync_fifo`, `spi_master`, `two_phase_handshake`)
  - Static Lint / Latch Inference Failure: 14.3% (1/7 tasks: `packet_frame_parser`)
* **Formal Mutation Kill Rate:** **77.8%** (7 out of 9 injected mutants caught at SBY BMC depth $k=25$).
  - 2 mutants survived (documented as `WEAK PROPERTY FAULT` in CDC handshake multi-cycle pulse coverage).
* **Verification Overhead:**
  - Average Multi-Gate Verification Latency: ~0.42s per candidate (Syntax: ~0.08s, Lint: ~0.12s, Simulation: ~0.11s, BMC: ~0.11s).
  - Average LLM Generation Latency: ~18.4s per turn.

### Design Complexity Bounds
* **Maximum Verified Datapath Width:** 32-bit arithmetic / data path (`pipelined_adder`, `cdc_handshake`).
* **Gate-Count Bound:** Target bound `<5k gates` (*Target Bound — Not Yet Empirically Validated across physical synthesis*).
* **Formal BMC Depth:** Configured at depth $k=20$ (baseline) and $k=25$ (mutation testing) using Z3 SMT solver. Bounded model checking guarantees absence of property violations up to $k$ cycles only.

### Toolchain & Synthesizability Constraints
* **Root-Level SVA Bind Limitations:** Yosys default AST front-end does not support top-level SystemVerilog `bind` directives; formal harnesses must instantiate the DUT and bind assertions within an explicit wrapper module.
* **Latch Inference in Combinational Always Blocks:** Incomplete `case` branches or missing default assignments in `always @(*)` trigger Yosys `$adlatch` inference, which fail closed at Gate 2 (Lint).
* **Asynchronous Simulation Timeouts:** FSM hangs, dropped handshakes, or lockups require explicit simulation watchdog blocks (`$fatal`) to prevent process deadlocks.


## Environment & Python Compatibility

Mind 3.0 pins **Python 3.11** as its baseline floor and verifies against Python 3.11 and 3.12 in CI.
Developers running on newer Python interpreters (such as Python 3.12, 3.13, or 3.14) must not treat local passes as sufficient proof of compatibility on Python 3.11 (for example, PEP 701 backslash-in-f-string syntax allowed in 3.12+ will fail with a `SyntaxError` on Python 3.11).

Always verify against Python 3.11 locally:
```bash
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install pytest httpx pydantic pyyaml
pytest -v
```

## Running Tests

```bash
pytest -v
```
