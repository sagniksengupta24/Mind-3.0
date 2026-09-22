# Mind 3.0 Benchmark Suite & Evaluation Architecture

## Live Execution Status

> **Important Operational Finding**:
> "No real benchmark runs have been executed against a live model in this environment. The task-set and persistence pipeline are ready; running them against a real model and reporting real numbers is the next required step, not yet done."

### Environmental Reality & Execution Prerequisites

Under Global Rule 1 (Zero Fabrication), no fabricated metrics (pass@1, pass@k, or repair turns to converge) are reported in this document. Live multi-turn silicon generation across the 50-task benchmark set was not executed in this environment due to the following concrete system constraints:

1. **Host Sandboxing Invariant**:
   Mind 3.0 strictly forbids unsandboxed execution, requiring Linux Bubblewrap (`bwrap`) via `BubblewrapSandbox`. The current host OS is macOS (`Darwin`), where `bwrap` is not natively available (`RuntimeError: bwrap binary not found on PATH. Mind 3.0 forbids unsandboxed execution`).
2. **Cloud Provider Authentication**:
   External cloud LLM access via OpenRouter is not configured (`OPENROUTER_API_KEY` is unset in the execution environment).
3. **Local Inference Latency & Schema Adherence**:
   While a local Ollama daemon is reachable at `http://127.0.0.1:11434` hosting `qwen2.5-coder:7b`, local CPU/GPU inference requires 15–30s per turn. Executing 50 tasks with up to 10 repair turns (~12 turns × 50 = ~600 inferences) would require ~3–4 hours, exceeding single-session interactive execution limits. Furthermore, 7B parameter models frequently deviate on nested JSON schema keys without constrained decoding or fine-tuning.

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
