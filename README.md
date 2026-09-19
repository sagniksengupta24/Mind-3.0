# Mind 3.0: Deterministic AI Engineering Agent Framework

Mind 3.0 is a fail-closed, deterministic AI engineering-agent framework for RTL generation, bounded formal checks, simulation coverage checks, and OSS static-timing validation. It is **not a tapeout-signoff system**.

## Key Architecture & Guarantees

- **11-Phase Deterministic Execution Engine**:
  `INTAKE` → `ROUTE` → `SNAPSHOT` → `MODEL_CALL` → `PARSE` → `POLICY_CHECK` → `EXECUTE` → `OBSERVE` → `VERIFY` → `REPAIR_OR_FINISH` → `TRACE`
- **6-Gate OSS RTL & Physical Validation Flow**:
  - **Gate 1: Yosys Elaboration & Latch Trap**: Catches unapproved inferred latches and combinational loops.
  - **Gate 2: SymbiYosys (SBY) Formal BMC**: Bounded model checking (depth 25) with counterexample trace isolation.
  - **Gate 3: Verilator 5.x Coverage**: Line, branch, and toggle coverage thresholds with pseudo-random LFSR and walking-1 stimulus.
  - **Gate 4: OpenSTA Multi-Corner Timing Signoff**: Setup ($WNS \ge 0$ ps, $TNS \ge 0$) and hold slack verification across PVT corners.
  - **Gate 5: OpenROAD Place-and-Route (opt-in)**: Physical design validation detecting placement overflow and global routing congestion.
  - **Gate 6: Yosys CDC Static Analysis**: Asynchronous clock-domain crossing detection.
  - **DFT Scan Advisory Audit**: Automatic DFF count analysis and scan-enable port presence detection (non-blocking).
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
│       │   ├── contracts.py
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
    ├── test_assurance.py
    ├── test_commercial_eda.py
    ├── test_dft_atpg.py
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

## Tapeout-readiness boundary

Passing `SiliconSignoffVerifier` means only that its configured OSS checks passed. It must never be represented as foundry, production, or tapeout signoff. `TapeoutReadinessVerifier` provides a separate, fail-closed evidence checklist for lint, CDC/RDC, equivalence, UPF, DFT, MCMM STA, DRC/LVS, and EM/IR. It validates reports from your qualified EDA/PDK flow; it does not generate or fake them. A design is tapeout-ready only when each required receipt is present and clean, and a qualified signoff team accepts the results.

## Running Tests

```bash
pytest -v
```
