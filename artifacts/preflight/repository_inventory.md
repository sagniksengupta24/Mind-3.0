# Mind 3.0 Repository Architecture & Inventory

**Generated:** 2026-09-28T05:24:00+05:30  
**Repository:** `/home/mind/Desktop/AI/Mind-3.0`  
**Git Head:** `9201daf0b7c6cb515ce060011a2f8eb55fe552e6`  
**Python Runtime:** Python 3.11.16 (`.venv`)  

---

## 1. Directory Structure

```text
Mind-3.0/
├── benchmarks/
│   ├── tasks.jsonl               # 50 task specifications (FSM, Arith, Bus, Mem)
│   └── transcripts/              # 50 task transcript JSON records
├── docs/
│   ├── benchmarks.md             # Benchmark suite documentation & truth-in-labeling
│   └── phase4_readiness.md       # Readiness dossier citing prerequisites and gaps
├── examples/
│   └── run_full_flow.py          # End-to-end driver usage example
├── skill/
│   ├── industry-report-analyst.skill  # Domain skill bundle
│   └── semiconductor-vlsi.skill       # VLSI synthesis/timing skill bundle
├── src/
│   └── mind3/
│       ├── __init__.py           # Package exports
│       ├── benchmarks/
│       │   ├── __init__.py
│       │   └── runner.py         # Benchmark runner, transcript models, fixture generators
│       ├── core/
│       │   ├── assurance.py      # TapeoutReadinessVerifier (8 signoff domains)
│       │   ├── cache.py          # ContentAddressedCache (SHA-256 keyed)
│       │   ├── contracts.py      # InterfaceContract, RTLGenerator, VerificationHarnessGenerator
│       │   ├── dataset.py        # FineTuningDatasetExporter (JSONL, ShareGPT)
│       │   ├── dft.py            # IEEE 1149.1 JTAG TAP, IEEE 1500, ATPG fault coverage
│       │   ├── driver.py         # PhaseDriver: 11-phase execution engine & OpenRouter/Ollama
│       │   ├── power.py          # IEEE 1801 UPF 3.0 multi-voltage engine
│       │   ├── types.py          # Enums, AgentAction, TraceRecord, PhaseEnum
│       │   └── verifier.py       # SiliconSignoffVerifier & RTLVerifier (6 gates)
│       ├── eda/
│       │   ├── __init__.py
│       │   └── tcl_templates.py  # Synopsys/Cadence/Siemens TCL generators
│       ├── sandbox/
│       │   ├── __init__.py
│       │   ├── bwrap.py          # Linux Bubblewrap process isolation engine
│       │   ├── eda_commercial.py # LSF/Slurm grid dispatchers & FlexLM pre-flight
│       │   └── remote_eda.py     # SSH cluster offloader
│       ├── skills/
│       │   ├── __init__.py
│       │   ├── models.py         # Skill metadata models
│       │   ├── registry.py       # Dynamic .skill archive loader
│       │   └── router.py         # Keyword-matrix skill router
│       └── soc/
│           ├── __init__.py
│           └── interconnect.py   # AXI5/AHB5/APB4 crossbar and SRAM wrapper generator
└── tests/
    ├── fixtures/eda_outputs/     # Real & synthetic EDA log fixtures for canaries
    ├── test_assurance.py         # Signoff evidence auditor tests
    ├── test_benchmarks.py        # Benchmark task-set & transcript schema tests
    ├── test_cache_and_dataset.py # SHA-256 caching & fine-tuning export tests
    ├── test_commercial_eda.py    # TCL generation & grid submission tests
    ├── test_dft_atpg.py          # JTAG & ATPG generation tests
    ├── test_fixtures_canary.py   # Canary tests against real EDA log fixtures (20/20 PASS)
    ├── test_mind3.py             # Core driver, sandbox, and gate tests (92/92 PASS)
    ├── test_pdk_gates_canary.py  # Real OpenSTA & OpenROAD in bwrap on Sky130 (3/3 PASS)
    ├── test_power_intent.py      # UPF 3.0 generation tests
    ├── test_ppa_optimization.py  # Pareto PPA tracking tests
    ├── test_soc_interconnect.py  # AMBA crossbar generator tests
    └── test_version_drift_canary.py # Version-drift parser canaries (11/11 PASS)
```

---

## 2. Core Architecture Subsystems

### 2.1 Execution Lifecycle (`PhaseDriver`)
Mind 3.0 replaces heuristic prompt-response loops with an 11-phase state machine:
1. `INTAKE`: Normalizes user specification and task parameters.
2. `ROUTE`: Dispatches domain skills via `SkillRouter`.
3. `SNAPSHOT`: Creates an atomic workspace snapshot before mutating code.
4. `MODEL_CALL`: Dispatches strict typed JSON schema queries to Ollama or OpenRouter.
5. `PARSE`: Validates and sanitizes returned JSON, extracting candidate RTL.
6. `POLICY_CHECK`: Verifies path security, null bytes, and traversal restrictions.
7. `EXECUTE`: Persists candidate RTL into the sandboxed workspace.
8. `OBSERVE`: Inspects file modifications and syntax structure.
9. `VERIFY`: Dispatches the candidate RTL through `SiliconSignoffVerifier` (6 gates).
10. `REPAIR_OR_FINISH`: If any gate fails, collects diagnostic feedback and triggers repair (bounded to `max_repairs`); reverts snapshot if budget is exhausted.
11. `TRACE`: Appends a canonical SHA-256 hash-chained record to `transcript.jsonl`.

### 2.2 Verification Infrastructure (`SiliconSignoffVerifier`)
The core verification oracle consists of 6 sequential gates:
- **Gate 1 (Elaboration & Latch Detection):** Yosys AST JSON elaboration detects combinational loops and unapproved inferred latches.
- **Gate 1b (Logic Equivalence Checking):** Yosys `equiv_status -assert` formally compares behavioral RTL against technology-mapped gate netlists.
- **Gate 2 (Formal BMC):** SymbiYosys (SBY) with Z3 SMT engine evaluates bounded model checking up to depth $k=25$ on SystemVerilog Assertions (SVA).
- **Gate 3 (Cycle Simulation & Coverage):** Verilator compiles C++ testbenches, injects Galois LFSR pseudorandom and boundary stimuli, and validates toggle and line coverage.
- **Gate 4 (Static Timing Signoff):** OpenSTA evaluates multi-corner static timing against SkyWater 130nm Liberty models, enforcing $WNS \ge 0$ ps and $TNS \ge 0$ ps.
- **Gate 5 (Physical Design Signoff):** OpenROAD performs floorplanning, track generation, placement legalization, and global routing with 0 DRC violations.
- **Gate 6 (Clock Domain Crossing):** Yosys static analysis inspects asynchronous clock domain crossings.

### 2.3 Sandboxing & Process Isolation (`BubblewrapSandbox`)
All EDA tool binaries are executed inside Linux Bubblewrap (`bwrap`) with:
- Network namespace unsharing (`--unshare-all`), blocking outbound network traffic.
- Read-only binding of system libraries, tool suites (`/home/mind/oss-cad-suite`, `/home/mind/openroad-env`), and PDK models.
- Writable binding restricted strictly to the designated execution scratch directory.

### 2.4 Prompt & Multi-Agent Contracts (`contracts.py`)
To prevent testbench hallucination, generation is decoupled into three independent agents:
- `InterfaceContract`: Defines pinouts, clocks, resets, and formal SVA invariant schemas.
- `RTLGenerator`: Receives only the interface specification and natural language requirements; has zero access to verification harnesses.
- `VerificationHarnessGenerator`: Authors independent SVA assertions and simulation testbenches without seeing RTL internal signal names.
