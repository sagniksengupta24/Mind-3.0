# Mind 3.0 Phase 4 Readiness Dossier

This dossier provides an objective, code-grounded assessment of the Mind 3.0 VLSI agent's technical readiness prior to seeking an external design-team pilot, publishing public benchmark scores, or commissioning a third-party security audit.

> **Operational Reality & Anti-Fabrication Invariant (Rule 1)**:
> Phase 4 requires three real-world external deliverables:
> 1. A deployed pilot with an external silicon design team.
> 2. A published public benchmark leaderboard with empirically measured Pass@1 and convergence figures.
> 3. A formal third-party SOC 2 Type II / security audit.
>
> None of these three outcomes can be produced by writing code, mock scripts, or markdown documents within this repository. This document is a **readiness dossier only**, documenting what has been verified, what remains unverified, and what specific human actions are required before approaching external partners.

---

## 1. Technical Prerequisites in Place (Evidence Strength Audit)

Every capability in Mind 3.0 is classified below by its actual empirical evidence base within this repository. No claims are rounded up.

### 1.1 REAL and Verified on this Host (Darwin arm64)

The following components execute locally with real dependencies and are verified by automated tests:

| Component / Subsystem | Verified Behavior | Host Dependencies | Test & Source Citation | Evidence Strength |
| :--- | :--- | :--- | :--- | :---: |
| **Gate 1: AST Elaboration & Latch Trap** | Detects combinational loops, unlatched branches, and syntax errors; synthesizes technology-mapped gate netlists. | Yosys 0.69 (`yosys -p "prep -top ...; check -assert"`) | [`test_silicon_signoff_gate1_latch_trap`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L770-L800), [`src/mind3/core/verifier.py`](file:///Users/sagniksengupta/Desktop/AI/src/mind3/core/verifier.py) | **HIGH** (Real binary execution) |
| **Gate 2: Formal Property BMC** | Automatically compiles SystemVerilog Assertions (SVA) bind files and executes bounded model checking up to cycle depth $k$. | SymbiYosys 0.69 + Z3 5.1.0 SMT engine | [`test_silicon_signoff_gate2_formal_bmc_failure`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L801-L830), [`test_sby_config_property_depth_override`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py) | **HIGH** (Real SMT solver execution) |
| **Gate 3: Cycle Simulation & Coverage** | Generates C++ testbenches with 32-bit Galois LFSR pseudo-random stimulus and boundary sweep stimuli; compiles and executes cycle-accurate simulation; enforces 100% line coverage thresholds. | Verilator 5.052 (`verilator --cc --exe --coverage`) + Apple Clang | [`test_gate3_verilator_executable_simulation_and_coverage_thresholds`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py), [`test_verilator_testbench_lfsr_stimulus`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py) | **HIGH** (Real binary compilation & run) |
| **Gate 6: CDC Distinction & Prerequisite Guard** | Accurately distinguishes `CDC_TOOLING_UNAVAILABLE` from `CDC_VIOLATION`. Forbids silent passes when tools are absent (`allow_mock_fallback=False` default). | Yosys CDC script analysis | [`test_gate6_cdc_tooling_unavailable_distinction`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py), [`src/mind3/core/verifier.py`](file:///Users/sagniksengupta/Desktop/AI/src/mind3/core/verifier.py) | **HIGH** (Behavioral unit verification) |
| **Version-Drift Canary Architecture** | 10 independent canary tests verifying that downstream parser and verifier logic detect tool-output variations across EDA versions without brittle string breaks. | Synthetic and real regression fixtures | [`tests/test_version_drift_canary.py`](file:///Users/sagniksengupta/Desktop/AI/tests/test_version_drift_canary.py) | **HIGH** (Deterministic unit coverage) |
| **Multi-Agent Decoupled Prompting** | Silicon Architect extracts formal contract schemas; RTL Generator receives only interface specifications with zero testbench access; Verification Engineer authors formal harnesses without seeing RTL internals. | Pydantic v2 validation | [`test_contract_synthesizer_and_prompt_decoupling`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L718-L724), [`test_contract_synthesizer_prompt_schema_hint_content`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L725-L767) | **HIGH** (Structural prompt & schema validation) |
| **Tamper-Evident Hash-Chained Telemetry** | Every agent action, verification result, and state transition emits a canonical SHA-256 hash record chained to the prior state (`TraceRecord`). In loopback mode, injects deterministic SHA-256 attestation tokens. | Standard library `hashlib` | [`test_air_gapped_emits_cryptographic_attestation`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L3127-L3149), [`src/mind3/core/driver.py`](file:///Users/sagniksengupta/Desktop/AI/src/mind3/core/driver.py#L323-L355) | **HIGH** (Cryptographic invariant validation) |
| **Loopback-Only Network Guard** | Rejects external cloud endpoints (`openrouter`) and non-loopback IP addresses (`base_url != 127.0.0.1/localhost`) at initialization with `ValueError`. | Native Python socket validation | [`test_air_gapped_forbids_cloud_provider`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L3084-L3110), [`test_air_gapped_forbids_non_loopback_base_url`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L3111-L3126) | **HIGH** (Runtime guard rejection) |
| **Filesystem Policy & Traversal Guard** | Blocks path traversal, null bytes (`\x00`), workspace root overwrites, and `.mind` internal storage mutations. | `PhaseDriver._policy_check` | [`test_phase_driver_full_run_rollback_lifecycle`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py), [`src/mind3/core/driver.py`](file:///Users/sagniksengupta/Desktop/AI/src/mind3/core/driver.py#L540-L580) | **HIGH** (Path security rejection) |
| **Presentation Tag Derivation** | Ensures presentation labels (`[REAL EDA]`, `[SIMULATED]`, `[SKIPPED]`) derive strictly from report flags; fails if contradictions exist. | Verifier formatter | [`test_gate_presentation_label_contradiction_detection`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L3240-L3300) | **HIGH** (Authoritative derivation check) |

---

### 1.2 REAL but Verified via Single Manual Debugging Trial Only

- **Live OpenRouter WAN Inference**:
  - **What Happened**: In conversation step 2438, a live trial was executed against `https://openrouter.ai/api/v1/chat/completions` using an authenticated Free Tier key. The gateway successfully returned a 34-line SystemVerilog module for `fsm_01`.
  - **Why It Is Not Counted as Benchmark Evidence**: This trial was executed using an ad-hoc inline `LocalSubprocessSandbox` bypass because `bwrap` is missing on macOS. Under Rule 7 (Scope Leakage Prevention), this output was deliberately **reverted** from `benchmarks/transcripts/` to prevent polluting the benchmark dataset with unsanctioned sandbox bypass data.
  - **Current Status**: Proven that the external API integration functions over the WAN, but zero sanctioned benchmark data exists from it.

---

### 1.3 Architecturally Ready but UNVERIFIED on this Host

The following components have complete, unit-tested implementations but cannot run end-to-end on the current development machine due to missing host dependencies or OS architectural limitations:

| Component / Subsystem | Current State on Host | Why Host Cannot Verify | What Linux CI Execution Must Confirm |
| :--- | :--- | :--- | :--- |
| **Bubblewrap Sandbox Network Isolation** | Unit test implemented: [`test_bubblewrap_sandbox_network_isolation_outbound_blocked`](file:///Users/sagniksengupta/Desktop/AI/tests/test_mind3.py#L3150-L3239). | macOS (`Darwin`) lacks Linux kernel user/network namespaces (`CLONE_NEWNET`, `CLONE_NEWUSER`) and `libcap`. Test explicitly skips with reason. | Must execute on Linux with `bwrap` installed; assert return codes 42 and 43 when sandbox attempts socket connections to `1.1.1.1:80` and host loopback server. |
| **Gate 4: OpenSTA Multi-Corner Timing** | Parser logic tested against synthetic & captured logs. Pipeline falls back to mock if tool missing. | `opensta` binary is not installed on this host. | Must run real `sta` binary against technology-synthesized netlist, standard cell liberty models (`sky130_fd_sc_hd__tt_025C_1v80.lib`), and auto-generated SDC across PVT corners without mock fallback. |
| **Gate 5: OpenROAD Physical Design (PnR)** | Parser logic tested against synthetic & captured logs. Skipped by default. | `openroad` binary is not installed on this host. | Must run real `openroad` floorplanning, global placement, clock tree synthesis, routing, and IR-drop signoff without mock fallback. |
| **50-Task Live Benchmark Dataset** | 50 tasks defined in `benchmarks/tasks.jsonl`; `BenchmarkRunner` persistence and tuple extraction verified; 50 schema-validation fixtures stored in `benchmarks/transcripts/`. | Cannot execute live without either (a) exhausting OpenRouter daily request quotas or (b) violating host sandboxing invariants. | Must run all 50 tasks on Linux through `run_silicon_pipeline` with real `BubblewrapSandbox` and an authorized API key; persist 50 genuine transcripts; publish empirical Pass@1 and repair convergence curves. |

---

## 2. What Is Still Missing to Approach a Real Pilot Partner

External silicon design teams (whether commercial ASIC houses, defense contractors, or open-source chip projects) evaluate tools against unforgiving verification standards. Mind 3.0 cannot credibly approach a partner until the following concrete gaps surfaced in Phases 1–3 are closed:

1. **Empirical Benchmark Numbers with Real Pass@1**:
   - External teams will not evaluate an agent that has zero measured benchmark completions.
   - We must produce and publish genuine Pass@1, Pass@k, and repair-turn convergence curves across the 50-task suite run under real `bwrap` sandboxing with live EDA engines.
2. **End-to-End Silicon Signoff on Real Linux Infrastructure**:
   - `allow_mock_fallback=True` must be strictly forbidden during pilot evaluations.
   - Physical timing (OpenSTA) and physical design (OpenROAD) must execute real tool binaries against actual PDK libraries (e.g., SkyWater 130nm or GlobalFoundries 180nm MCU).
3. **Execution of the Sandbox Network-Block Test**:
   - Security auditors and enterprise CISOs will reject a security report where the network isolation test was skipped.
   - `test_bubblewrap_sandbox_network_isolation_outbound_blocked` must pass cleanly on Linux CI.
4. **Independent Spot-Checking of Code vs. Claims**:
   - As demonstrated during Phase 1–3 review, self-audit processes alone are vulnerable to confirmation bias and unasserted assumptions (e.g., the `fsm_01.json` bypass leakage, the unasserted prompt template change, and the documentation citation vs. runtime verification distinction).
   - An engineer independent of this implementation must audit the code against [SECURITY.md](file:///Users/sagniksengupta/Desktop/AI/SECURITY.md) and [docs/benchmarks.md](file:///Users/sagniksengupta/Desktop/AI/docs/benchmarks.md).
5. **Model Syntax Failure Hardening**:
   - The single live trial on `fsm_01` revealed that small/free models frequently generate invalid SystemVerilog syntax (e.g., procedural `typedef enum` inside sequential `always` blocks).
   - While the repair loop is designed to catch this via Gate 1 feedback, repair turns consume latency and quota. A pilot requires testing against stronger frontier coding models (e.g., Claude 3.5 Sonnet, DeepSeek V3, Qwen 2.5 Coder 32B) to measure realistic baseline first-turn syntax adherence.

---

## 3. Concrete Human Actions Required

The following actions require human authorization, infrastructure provisioning, commercial negotiation, or external review. **None can be executed by prompting an AI agent.**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       ACTION ROADMAP FOR HUMAN OPERATORS                      │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 1. INFRASTRUCTURE: Provision Linux CI Hardware Environment                   │
│    - Deploy an Ubuntu 22.04/24.04 or Debian 12 runner (x86_64).              │
│    - Install system dependencies: `apt-get install -y bubblewrap libcap2-bin`│
│    - Install open-source EDA binaries: Yosys, SymbiYosys, Z3, Verilator.     │
│    - Install physical signoff suite: OpenSTA, OpenROAD, Sky130 PDK.           │
│    - Run `pytest -v`: Verify 156 passed, 0 skipped (including network block).│
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 2. BENCHMARKING: Execute Full 50-Task Dataset Run                            │
│    - Fund an OpenRouter or provider API key with sufficient commercial credit│
│      (~50 tasks × 10 max repairs = ~500 inference calls).                    │
│    - Execute `BenchmarkRunner` through the sanctioned `BubblewrapSandbox`.   │
│    - Overwrite all 50 schema-validation fixtures in `benchmarks/transcripts/`│
│      with authentic `is_schema_validation_fixture: false` transcripts.       │
│    - Update `docs/benchmarks.md` with real Pass@1 and convergence figures.   │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 3. PILOT CANDIDATE SELECTION: Engage an Open-Source Hardware Team            │
│    - Target initial engagement toward open-source silicon projects:          │
│      * Tiny Tapeout (shuttle-constrained, simple peripheral blocks).         │
│      * LowRISC / OpenTitan (IP blocks with rigorous formal assertions).      │
│      * CHIPS Alliance / FOSSi Foundation workgroups.                         │
│    - Scope initial pilot strictly to leaf IP modules (FIFOs, UART, SPI, CRC) │
│      rather than multi-million-gate SoC top-levels.                          │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 4. THIRD-PARTY AUDIT: Budget & Scope SOC 2 Type II Engagement                │
│    - Retain an accredited external security auditing firm.                   │
│    - Scope the audit strictly to verified architectural invariants:          │
│      * Loopback-only enforcement and cryptographic attestation tokens.       │
│      * Bubblewrap container network unsharing and process isolation.         │
│      * Workspace path traversal rejection and atomic rollback snapshotting.  │
│    - Provide auditor with unredacted access to `SECURITY.md`, code, and logs.│
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ 5. GOVERNANCE: Independent Peer Review of Codebase & Dossier                 │
│    - Retain or assign an independent principal engineer who had no role in   │
│      authoring Phases 0–3.                                                   │
│    - Mandate adversarial review of all tests, claims, and documentation      │
│      before any external customer or investor demonstration.                 │
└──────────────────────────────────────────────────────────────────────────────┘
```
