# Mind 3.0: Deterministic AI Engineering Agent Framework

Mind 3.0 is a fail-closed, deterministic AI engineering agent architecture tailored for high-assurance engineering, hardware synthesis (SystemVerilog / RTL), formal property verification, static timing signoff, and structured technical reporting.

## Key Architecture & Guarantees

- **11-Phase Deterministic Execution Engine**:
  `INTAKE` → `ROUTE` → `SNAPSHOT` → `MODEL_CALL` → `PARSE` → `POLICY_CHECK` → `EXECUTE` → `OBSERVE` → `VERIFY` → `REPAIR_OR_FINISH` → `TRACE`
- **4-Gate Silicon Signoff Oracle**:
  - **Gate 1: Yosys Elaboration & Latch Trap**: Catches unapproved inferred latches in combinational logic.
  - **Gate 2: SymbiYosys (SBY) Formal BMC**: Bounded model checking (depth 25) with counterexample trace isolation.
  - **Gate 3: Verilator 5.x Coverage**: Line, branch, and toggle coverage thresholds.
  - **Gate 4: OpenSTA Multi-Corner Timing Signoff**: Worst Negative Slack ($WNS \ge 0$ ps) verification against cell libraries.
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
│       │   ├── contracts.py
│       │   ├── driver.py
│       │   ├── types.py
│       │   └── verifier.py
│       ├── sandbox/
│       │   ├── bwrap.py
│       │   └── remote_eda.py
│       └── skills/
│           ├── models.py
│           ├── registry.py
│           └── router.py
└── tests/
    └── test_mind3.py
```

## Running Tests

```bash
pytest -v
```
