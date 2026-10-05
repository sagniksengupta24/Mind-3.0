# Catalog of Invalidated Claims & Retracted Metrics

**Protocol Gate:** GATE 1 — SIGNOFF INVALIDATION  
**Date:** 2026-09-28  

The following claims and artifacts from the previous execution are formally **INVALIDATED** and retracted from the authoritative record:

---

## 1. Mislabeled Model Claims
* ❌ **Invalid Claim:** "Frontier-Class Code Model Evaluation (qwen2.5-coder:30b)".
* **Correction:** The generator model is an open-weights 30-billion parameter model (`qwen2.5-coder:30b`) running locally on Ollama (`127.0.0.1:11434`). It must not be described as a frontier model or equated to commercial frontier APIs (e.g. Claude 3.5 Sonnet, GPT-4o).

---

## 2. Premature Protocol Execution Claims
* ❌ **Invalid Claim:** "Step 2 Mutation Testing Complete (77.8% Kill Rate)", "Step 3 Benchmark Comparison Complete", "Step 5 Final Audit Complete".
* **Correction:** Steps 2–5 were executed without receiving the required protocol confirmation after Step 1. All metrics from Steps 2, 3, 4, and 5 are declared **VOID** pending proper revalidation.

---

## 3. Ambiguous Formal BMC Depth Claims
* ❌ **Invalid Claim:** Mixed statements asserting BMC depth $k=20$ and depth $k=25$ in Step 1.
* **Correction:** A single, strictly configured depth `STEP1_BMC_DEPTH=25` is now programmatically bound to all SBY files, logs, and validators.

---

## 4. Distorted Repair-Count Metrics
* ❌ **Invalid Claim:** Unconverged tasks reported `-` repair turns, obscuring the fact that 3 full repair turns were attempted and failed.
* **Correction:** Unconverged tasks must explicitly record `repair_attempts: 3`, `converged_turn: null`, `final_status: FAIL (Unconverged)`.

---

## 5. Inappropriate Mutation Design Mapping
* ❌ **Invalid Claim:** 77.8% Mutation Kill Rate across Priority Encoder, Signed Multiplier, and CDC Handshake.
* **Correction:** Combinational priority encoders and multiplier blocks do not naturally possess state transitions, pointers, or multi-clock handshakes. Step 2 must be redesigned using sequential/control designs (e.g., `sync_fifo`, `spi_master`, `traffic_light_controller`) when authorized.

---

## 6. Unexecuted Public Benchmark Claims
* ❌ **Invalid Claim:** Step 3 standard benchmark validation.
* **Correction:** Step 3 only imported published literature numbers into a table without executing five live VerilogEval / RTLLM tasks.

---

## 7. False Equivalence between Trace Integrity and Model Determinism
* ❌ **Invalid Claim:** "166-record SHA-256 hash ledger proves deterministic AI agent behavior".
* **Correction:** Hash chaining proves *trace integrity* (non-repudiation and tamper-evidence of recorded logs). It does not prove that model generation is deterministic. Model determinism must be tested independently across repeated identical trials.

---

## 8. Unsupported Physical Implementation Claims
* ❌ **Invalid Claim:** Target bounds such as "<5k gates" presented without physical synthesis measurements.
* **Correction:** All unmeasured physical targets must be explicitly labeled `TARGET — NOT EMPIRICALLY VALIDATED`.
