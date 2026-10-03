# Mind 3.0 RTL Pipeline Changelog

| Iteration | Dominant failure / defect | Change | Compile | Simulation | Formal | Full verified |
|---|---|---|---:|---:|---:|---:|
| 0 | Evidence/metric collapse; historical runs mixed model/parser failures with verifier infrastructure failures | Forensic baseline only; no new performance claim in current environment | N/A | N/A | N/A | N/A |
| 1 | Contract/interface drift and clock/reset hallucination risk | Immutable benchmark contract derived from evaluator metadata; deterministic contract consistency checks | N/A | N/A | N/A | N/A |
| 2 | Compile failures reaching later verification stages | Compile-first Gate 1 using real compiler/linter before synthesis/formal | N/A | N/A | N/A | N/A |
| 3 | Repairs lacked localized evidence | Structured compile/simulation/formal repair evidence with bounded 3/3/3 attempts | N/A | N/A | N/A | N/A |
| 4 | Signoff ordering allowed simulation to be skipped by formal failure | Independent validation reordered to compile → simulation → formal → timing | N/A | N/A | N/A | N/A |
| 5 | Benchmark harness could report misleading mock/zero metrics | Live benchmark fail-closed; mock runs excluded from performance evidence | N/A | N/A | N/A | N/A |
| 6 | Provider usage/cost were silently reported as zero | Capture provider token usage; cost is marked known only when explicit pricing rates are configured | N/A | N/A | N/A | N/A |

`N/A` means no defensible live RTL benchmark measurement was possible in the present execution environment. It is intentionally not converted to 0%.

## Iteration 11 — macOS live-benchmark execution path

**Observed blocker:** the production benchmark runner instantiated `BubblewrapSandbox` unconditionally. Bubblewrap is Linux-specific, so a macOS host could not execute the benchmark even when Yosys, SBY, and Verilator were installed. The CLI also required 100 real transcripts by default, which made a 20-task development run evidence-insufficient even after successful execution.

**Change:**
- Added `MacOSSandbox` using macOS `sandbox-exec`/Seatbelt with deny-by-default policy, no network, read-only system/toolchain paths, and read/write only inside the task workspace and isolated temp directory.
- Added `get_local_sandbox()` platform selection; Linux retains Bubblewrap, Darwin uses Seatbelt, unsupported local platforms fail closed.
- Production benchmark runner now uses the platform-aware sandbox.
- Prerequisite detection is platform-aware and accepts either `sta` or `opensta`.
- OpenSTA invocation now uses the available `sta`/`opensta` executable.
- Remote EDA mode no longer incorrectly requires a local `bwrap` installation.
- Development benchmark evidence threshold defaults to `min(100, selected task count)`; explicit `--min-tasks` remains available for stricter gates.

**Measured software regression:** `209 passed, 13 skipped` on this development environment. Live EDA tests remain skipped here because the Linux EDA/sandbox prerequisites are unavailable to the container.

**Important:** no RTL benchmark improvement is claimed from this iteration until the real model + EDA stack executes the fixed 20-task suite.
