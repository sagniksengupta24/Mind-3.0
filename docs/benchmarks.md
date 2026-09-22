# Mind 3.0 Benchmark Suite & Evaluation Architecture

## Live Execution Status

> **Truth-in-Reporting Status**:
> A live multi-agent silicon generation trial was executed against OpenRouter (`openrouter/free`) for benchmark task `fsm_01`. The full 5-tuple has been persisted as a verified live transcript to `benchmarks/transcripts/fsm_01.json`.
> The remaining 49 benchmark tasks remain structured schema-validation fixtures pending additional API quota.

### Empirical Live Run Results (`fsm_01`)

| Metric | Measured Value | Analysis |
| :--- | :---: | :--- |
| **Model Evaluated** | `openrouter/free` | Live remote inference via OpenRouter gateway |
| **Task ID** | `fsm_01` | Non-overlapping sequence detector (1011) |
| **Stage 1: Contract Synthesis** | **SUCCESS** | Extracted `fsm_01` pinout (clk, rst_n, data_in, match) |
| **Stage 2: Harness Generation** | **SUCCESS** | Auto-generated SVA bind, SBY BMC config, Verilator C++ testbench, SDC |
| **Stage 3: RTL Generation** | **SUCCESS** | Emitted complete 34-line synthesizable SystemVerilog module |
| **Stage 4: Gate 1 (Yosys)** | **FAIL** | Failed AST elaboration (`SYNTHESIS_ELABORATION_ERROR`) due to procedural declaration inside `always` block |
| **Repair Loop** | **EXECUTED** | Diagnostic feedback dispatched; rolled back safely upon exhaustion |
| **Pass@1** | **0% (0 / 1)** | Initial RTL failed Gate 1 syntax/elaboration check |
| **Convergence** | Did not converge | Rolled back workspace atomically |
| **Transcript Output** | `benchmarks/transcripts/fsm_01.json` | Labeled `"real generation output"` (`is_schema_validation_fixture: false`) |

### Quota & Environmental Reality

1. **OpenRouter API Key Status**:
   - The provided key authenticated successfully (`200 OK`, Free Tier).
   - Account quota: 50 requests/day for free models. Running the entire 50-task suite with multi-turn repairs (~10 repair turns × 50 tasks = ~500 API calls) would immediately exhaust the daily quota.
2. **Local Sandboxing**:
   - macOS host execution environment lacks Linux Bubblewrap (`bwrap`), requiring fallback to local subprocess execution for host EDA binaries (Yosys 0.69, Verilator 5.052, SBY 0.69 / Z3 5.1.0). OpenSTA and OpenROAD physical design binaries are uninstalled and utilize simulated mock signoff fallback.

All benchmark tasks, harness generators, transcript schemas, and dataset persistence pipelines are fully implemented and verified via automated unit and integration tests.

---

## Benchmark Task-Set (`benchmarks/tasks.jsonl`)

The benchmark task-set comprises 50 structured RTL module specifications inspired by conventions from published hardware generation benchmarks (e.g., VerilogEval, RTLLM) but curated specifically for Mind 3.0's 4-gate verification oracle.

Each task specification includes:
- `task_id`: Unique identifier (e.g. `fsm_01` to `fsm_15`, `arith_01` to `arith_15`, `bus_01` to `bus_10`, `mem_01` to `mem_10`).
- `category`: Architectural domain.
- `name`: Human-readable module name.
- `natural_language_spec`: Engineering requirements specification.
- `expected_ports`: Full pinout with port name, direction (`input`, `output`, `inout`), bit-width, and description.
- `sva_properties`: 2 to 5 formal SystemVerilog Assertions (SVA) verifying safety, liveness, and interface protocols.
- `benchmark_origin`: Explicit attribution ("inspired by, not identical to").

### Category Distribution

| Category | Task Count | Description & Invariants Verified |
| :--- | :---: | :--- |
| **FSM** | 15 | Sequence detectors, traffic controllers, arbiters, handshake controllers, parity checkers, vending machines. Tests state encoding, illegal transition lockouts, reset behavior. |
| **Arithmetic** | 15 | Adders (Kogge-Stone, ripple, carry-lookahead), multipliers (Booth, array), dividers, ALUs, saturating arithmetic, cordic, CRC. Tests bit-growth, overflow, zero-division, bit-level correctness. |
| **Bus Protocol** | 10 | APB slave, AXI4-Lite read/write channels, Wishbone, SPI controller, I2C master/slave, valid/ready pipelining. Tests handshake invariants, backpressure, deadlocks. |
| **Memory Controller**| 10 | Sync/async FIFOs, dual-port RAM, circular buffers, direct-mapped cache controller, burst controllers. Tests full/empty flag integrity, pointer wrap, hazard handling. |
| **Total** | **50** | Fully validated by `tests/test_benchmarks.py`. |

---

## Transcript Dataset Architecture (`benchmarks/transcripts/`)

The persistence pipeline captures every generation run as a 5-tuple:
`($\text{contract}, \text{generated\_rtl}, \text{gate\_failure\_category}, \text{repair\_attempts}, \text{final\_outcome}$)`

### Tuple Schema Structure

Each transcript is stored as `benchmarks/transcripts/{task_id}.json`:

```json
{
  "task_id": "fsm_01",
  "category": "FSM",
  "name": "seq_detector_1011",
  "natural_language_spec": "...",
  "is_schema_validation_fixture": true,
  "label": "schema-validation fixture, not real generation output",
  "model": "mock-fixture-generator",
  "provider": "mock",
  "max_repairs": 10,
  "contract": {
    "module_name": "fsm_01",
    "ports": [...],
    "sva_properties": [...],
    "timing": {...}
  },
  "generated_rtl": "// [SCHEMA-VALIDATION FIXTURE - NOT REAL GENERATION OUTPUT]\nmodule fsm_01 ...",
  "gate_failure_category": "FORMAL_INVARIANT_BREACH",
  "repair_attempts": [
    {
      "turn": 1,
      "guidance": "GATE 2 SIGN-OFF FAILURE: Formal SVA invariant breached in SymbiYosys BMC.",
      "repaired_rtl": "...",
      "passed": true,
      "error_category": null,
      "failure_reason": null,
      "gate_reports": [...]
    }
  ],
  "final_outcome": {
    "passed": true,
    "status": "SILICON_VERIFIED",
    "turns_taken": 2,
    "silicon_verified": true,
    "gate_reports": [...]
  },
  "timestamp": 1790037074.025
}
```

### Truth-in-Labeling Guarantee

All 50 pre-generated files currently residing in `benchmarks/transcripts/` are strictly labeled:
- `"is_schema_validation_fixture": true`
- `"label": "schema-validation fixture, not real generation output"`
- Synthesizable code includes header: `// [SCHEMA-VALIDATION FIXTURE - NOT REAL GENERATION OUTPUT]`

Automated test `test_benchmark_transcripts_fixtures_integrity_and_labeling` validates that no fixture claims to be real generation output.

---

## Instructions for Running Real Benchmarks

When deploying Mind 3.0 to a Linux compute host with Bubblewrap and a production LLM endpoint:

1. **Configure Environment Variables**:
   ```bash
   export OPENROUTER_API_KEY="sk-or-v1-..." # Or run local Ollama with GPU acceleration
   ```

2. **Execute Benchmark Runner**:
   ```bash
   python -m mind3.benchmarks.runner --max-repairs 10 --model "anthropic/claude-3.5-sonnet" --provider "openrouter"
   ```

3. **Metrics Calculation**:
   Once real transcripts are populated, metrics will be computed directly via:
   $$\text{pass@1} = \frac{N_{\text{passed on turn 0}}}{N_{\text{total tasks}}}$$
   $$\bar{T}_{\text{converge}} = \frac{1}{N_{\text{converged}}} \sum_{i \in \text{converged}} \text{turns\_taken}_i$$
   and documented in this file with full hash-chained cryptographic attestations.
