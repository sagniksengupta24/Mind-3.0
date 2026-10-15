# Mind-3.0 Verified-RTL Improvement Plan v2

Research-justified revision of the original plan, prepared 15 October 2026. The invariants of v1 stay in force. v2 changes priorities, adds controls, and corrects what the experiments would otherwise measure. Evidence references [E1]–[E16] are listed in section 9.

## 1. Verdict on v1 and what changes

Three independent reviews scored v1 at 7.0, 7.4 and 7.5 out of 10. They agree on the shape of the problem: verification integrity is outstanding (about 9 to 10 out of 10), but uplift for a small model is only about 5.5 to 6 out of 10. The reasons are that the highest-leverage levers for a 7B model (the weights, sampling filtered by a sound verifier, a structured specification) are absent or deferred; that several planned experiments would measure oracle conditions or noise; and that the formal properties that define VERIFIED are never themselves audited.

| # | Change from v1 | Why | Evidence |
|---|---|---|---|
| 1 | Model bake-off becomes Phase 2 (dev suite only) | Same-size, Verilog-specialised 7B models score far above a general coder 7B on public benchmarks | E1, E2 |
| 2 | Best-of-n sampling with the verifier as selector comes before repair | The verifier is a sound oracle; sampling coverage is large; repair is weak at 7B | E1, E4, E6, E7, E10 |
| 3 | Contracts are evaluated twice: hand-written (upper bound) and auto-extracted (deployable) | Structure lifts even an untrained 7B, but only when it is produced well | E3 |
| 4 | Verifier-trust hardening becomes Phase 1 | Passing proofs can be vacuous or incomplete; every later number depends on them | E9, E11, E12, E13 |
| 5 | Repair gets deterministic localisation, two repair modes and a matched-budget control | Feedback quality is the bottleneck; conditioning on its own failed attempt can hurt small models | E5, E6, E7, E8 |
| 6 | Paired statistics, repeated seeds and a larger dev suite are mandatory | A 20-task suite resolves only very large effects; run-to-run noise is 1 to 2 points even on 156 tasks | E14, E15 |
| 7 | Every report splits system results from model-generated results | Templates raise the system rate without raising model capability | design |
| 8 | Templates are built from the observed failure distribution | Templates only help the patterns they cover | design |

Review claims that could not be verified during this research (VERI-SURE, BiMem-RAG, a 50-task study of 1B to 8B models, ReasoningV base-model figures, a 7% specification-inconsistency figure for VerilogCoder) are not used as justification anywhere in this plan.

## 2. Invariants (unchanged from v1)

- The model proposes RTL. Deterministic tools derive, verify and decide. VERIFIED requires every required gate to genuinely pass on the exact final artifact.
- Gate order and meaning are frozen. The verifier stays independent of the generator, repairer, templates, retrieval and candidate selection.
- Timeouts, inconclusive proofs, tool errors and environment limits are never passes. A known environment limit (for example the CDC gate lacking a cdc command on stock Yosys) is reported as ENVIRONMENT_FAILURE: never a pass, never an RTL defect.
- No weakening of assertions, constraints or specifications to raise numbers. The held-out suite is never used for debugging, prompt tuning, template development or model selection.
- No invented results. Every number traces to a run ID and an artifact bundle.
- Terminal states stay explicit, using the repository's existing names: VERIFIED, UNVERIFIED, FAILED, AMBIGUOUS_SPECIFICATION, ENVIRONMENT_FAILURE.
- Work proceeds in small checkpoints: one phase at a time, each ending in an evidence bundle that is reviewed before the next begins. No phase may claim a gain that its own run IDs do not show.

## 3. What the research supports, and where it stops

Weights are the biggest lever. On VerilogEval v2 spec-to-RTL, Qwen2.5-Coder-7B-Instruct scores 31.3% pass@1, while CodeV-R1-7B, trained with reinforcement learning against automatically generated testbenches, scores 68.8% [E1]. ReasoningV reached 57.8% on VerilogEval-Human from a Qwen2.5-Coder-7B base using about 5,000 functionally verified training examples [E2]. Caveats: these are simulation benchmarks, not a formal-gated pipeline; reasoning models emit long outputs, so latency on a 16 GB Mac is the price; licences and training-data overlap need checking.

Sampling coverage is large, and a sound verifier can harvest it. The same base 7B reaches 31.3% pass@1, 49.3% pass@5 and 54.6% pass@10 [E1]. Execution-based ranking of candidates added about 10 points of pass@1 on average and helped with as few as 5 samples [E10]. MAGE's jump from 72.4% to 93.6% used 20 candidates at temperature 0.85 plus checkpoint debugging, but with a frontier generator, so its magnitudes do not transfer [E4].

Structure in the prompt helps untrained small models. Giving Qwen2.5-Coder-7B a structured expression of the design (interface, core functions, key considerations) lifted VerilogEval v2 spec-to-RTL from 23.0% to 35.9% at temperature 0, and to 37.8% when combined with the original text [E3]. Caveats: that structure was produced by a purpose-trained model; on RTLLM v2 pass@1 it did not help (36.1% to 33.9%) although pass@5 and pass@10 improved. Extraction quality decides the outcome.

Repair is weak at small scale; diagnosis is the lever. A cost-aware study found self-repair often no better than drawing more samples at equal budget, with feedback quality the bottleneck [E6]. A 2026 preprint on 1.5B to 7B code models (Python, MBPP+) found blind resampling matched or beat repair at 2.5 to 5.5 times fewer tokens, and attributed the penalty to anchoring on the model's own failed attempt [E7]; another preprint reports modest small-model gains [E8]. The closest published relative of the Mind-3.0 loop (LLM plus SymbiYosys counterexamples) repaired one of six benchmark designs reliably [E9]. The counterweight is structured localisation: VerilogCoder's AST-based waveform tracing and MAGE's state-checkpoint debugging both feed the model precise failure evidence [E4, E5]. Conclusion: invest in deterministic localisation, and prove repair beats resampling before keeping it.

A passing check is not proof of a correct check. Generated assertions can be syntactically valid and provable yet trivial or vacuous [E12]. Mutation coverage exposed gaps in a formal proof that checked only some of the required properties [E13]. In an audit of 50 examples that failed a formal self-consistency check, 66% had a faulty question rather than a faulty design [E11]. Real specifications also contain bugs and ambiguities [E16]. Audit specifications and properties before blaming the model.

Evaluation noise is larger than most gains. Pass rates varied by 1 to 2 points across identical runs even on a 156-problem benchmark [E15]. Paired per-question analysis and clustered standard errors are the recommended fix; clustered errors on popular evals can exceed naive ones by more than three times [E14].

### Calibrated expectations (priors, not predictions)

| Lever | Literature signal | Transfer risk | Prior for Mind-3.0 |
|---|---|---|---|
| Verilog-specialised 7B | +20 to +37 points on public simulation benchmarks | Pipeline differences, latency, contamination | Possibly the largest single lever; must be tested |
| Best-of-n with verifier | Base 7B pass@5 is about 18 points above pass@1 | Failure diversity, cost | Large and cheap to size (Phase 0 measures the ceiling) |
| Structured contracts | +12 to +15 points with good structure | Extraction quality | Medium; deployable value uncertain |
| Deterministic templates | Pattern-bounded | Coverage | Near-certain on covered families, zero elsewhere |
| Evidence-driven repair | Small or negative at small scale | Anchoring, feedback quality | Small; keep only where it beats resampling |
| Verified-example retrieval | About +4 points, observational, one system [E15] | Weak evidence | Small; test, do not assume |
| Fine-tuning | Large with 5K to 10K verified examples [E2, E11] | Compute, leakage | Gated by Phase 2 results |

These numbers come from published work on other benchmarks and generators. They are priors to be replaced by measurements.

## 4. Target architecture

Specification → Contract (validated, with provenance and an ambiguity registry) → Router (SUPPORTED_TEMPLATE, MODEL_REQUIRED, AMBIGUOUS, UNSUPPORTED_PATTERN) → Candidate generation (template and/or n model samples) → Gate pipeline per candidate (compile, simulation, formal, remaining sign-off gates, in the repository's existing order) → Selection (the first candidate that passes every gate; clustering may order work to save budget but never accepts a candidate) → if none passes: Localised failure evidence → Focused repair (patch or regenerate) → complete re-verification → terminal state.

Every stage has an input, an output, a status and an audit record. A later stage can never manufacture a pass for an earlier one.

## 5. Phases

### Phase 0: Baseline, ceiling and specification audit

Do

1. Record commit, worktree state, model identifier, quantisation, decoding parameters, prompt versions, tool versions and explicit dev and held-out suite selection.
2. Run the unmodified baseline. Store per task: specification, generated RTL, raw model output, logs, exit codes, timing, first failing gate, repair history and classification using the existing taxonomy (SPECIFICATION_ERROR, INTERFACE_ERROR, SYNTAX_ERROR, TYPE_WIDTH_ERROR, CLOCK_RESET_ERROR, SIMULATION_FAILURE, FORMAL_FAILURE, REPAIR_FAILURE, ENVIRONMENT_FAILURE, OTHER).
3. Reconcile historical success figures: task sets, denominators, snapshots and gate definitions must be documented before any two numbers are compared.
4. New: measure the ceiling. Run at least 10 samples per dev task at several temperatures through the full pipeline without repair. Report pass@1, pass@5 and pass@10, plus the first-failing-gate distribution. This sizes the headroom for Phases 3 and 7.
5. New: audit before blaming. For every failing dev task, check that the specification, reference or testbench, and formal properties agree [E11, E16].
6. Freeze the baseline manifest. Separate RTL defects from tool, timeout, orchestration and specification faults.

Exit: an independent reviewer can reproduce the baseline and explain each task outcome; the ceiling table exists.

### Phase 1: Verifier-trust hardening

Do

1. Every formal property must trace to the contract, the specification, or an explicitly authorised assumption. Properties are never taken from the generator or repairer model.
2. Vacuity checks: each property has a reachable cover witness, so a pass cannot come from an unreachable antecedent [E12].
3. Mutation coverage with the Yosys-based mutation tool on reference designs, with formal filtering of irrelevant mutations, to find behaviour changes that the properties and testbenches miss [E13]. Budget real setup effort; if it is not feasible for every task, cover each template family and a representative sample first.
4. Build a negative-control suite of known-bad candidates (off-by-one saturation bound, wrong reset polarity, truncated width, wrong divider terminal count, deleted assertion). All must be rejected, permanently, as a regression suite.

Exit: every dev task has audited properties with documented vacuity and mutation results; negative controls are rejected 100%; a false accept anywhere is a release blocker.

### Phase 2: Model bake-off

Do

1. Compare the current generator with one or two Verilog-specialised 7B checkpoints (for example CodeV-R1-7B and ReasoningV-7B), on the dev suite only, with identical gates, prompts rendered to each model's required format, and decoding settings recorded.
2. Record tokens and wall-clock per task and per verified task. Reasoning-style models can be slow; one published variant reports up to 75% fewer reasoning tokens [E2].
3. Check licences and training-data overlap with your task families. Public benchmark scores are not your scores [E1, E2].
4. Fix the adoption rule before running: paired verified-rate difference with its confidence interval, a cost ceiling per verified task, and a change in the first-failing-gate distribution.

Exit: a documented decision on the generator, with paired results and costs. Keep the existing model only if it is measured to be as good.

### Phase 3: Sampling with verifier selection

Do

1. Sweep n (for example 1, 5, 10, 20) and temperature on the dev suite to find the knee of the cost curve [E4, E10].
2. Run cheap gates first on all candidates; use simulation-output clustering only to order which survivors go to expensive formal runs [E10]. Acceptance is decided by the gates alone.
3. Report oracle coverage (any candidate passes every gate) against the selected result, and cost per verified task.

Exit: a chosen n and temperature, with measured gain over n=1 at matched wall-clock, and zero false accepts on the negative controls.

### Phase 4: Structured contracts

Do

1. Reuse any existing specification representation; add only the missing structure: top module and interface, ports with direction, width and signedness, parameters and legal values, clocks, reset polarity and synchrony, state and transitions, arithmetic limits and overflow behaviour, latency and handshake, environmental assumptions, unresolved items, and provenance linking each requirement to the source text.
2. Render the contract into the prompt in three parts: interface, core functions, key considerations [E3].
3. Two conditions, always reported separately: (a) hand-written and human-validated contracts (an upper bound), and (b) contracts extracted by the deployable system. Optionally (c) extracted by a larger offline model, allowed only for building datasets, never counted as the deployable result.
4. Validate structure (schema, widths, representable values, port directions, clock and reset consistency) and, separately, meaning: audit each critical field against the source text. A contract can be well-formed and wrong.
5. Ambiguity handling: an unresolved requirement is either resolved by an explicit, numbered, human-authorised assumption with rationale, or it blocks generation with AMBIGUOUS_SPECIFICATION. No silent defaults.
6. Derive formal properties from the contract deterministically wherever possible (feeds Phase 1).

Exit: every critical requirement used by a generator or verifier traces to the specification or an authorised assumption; the gap between conditions (a) and (b) is measured.

### Phase 5: Deterministic templates, driven by the failure distribution

Do

1. Build a template family only when Phase 0 shows it covers a meaningful share of observed failures. Start with saturation and boundary arithmetic, then counters, then clock dividers, as in v1.
2. Derive bounds with arbitrary-precision host arithmetic and the contract's widths and signedness; emit explicit sizing and signedness; reject missing or contradictory bounds.
3. Counters: only the combinations the contract requests (direction, reset type and polarity, clear, load, enable, wrap or saturate). Dividers: derive terminal count and toggle behaviour from the frequency relationship; check divisibility, duty cycle and odd ratios; there is no universal formula.
4. Router outputs SUPPORTED_TEMPLATE, MODEL_REQUIRED, AMBIGUOUS or UNSUPPORTED_PATTERN. Unsupported combinations go to the model; they are never forced into a template.
5. Quarantine rule: template-routed results are always reported separately from model-generated results.

Exit per family: host-language unit tests, positive and negative contract tests, boundary tests, compile, simulation and formal passes on the generated RTL, deliberately wrong variants rejected, and no bypass of any gate.

### Phase 6: Compiler-feedback adapter

Do

1. Wrap the existing syntax, elaboration and synthesis checks: record tool and version, command, exit status, classification, source location, relevant diagnostic text and the stage at which failure occurred.
2. Use syntax-aware tooling for structural analysis and patch validation, not broad regular expressions. Validate a patch before it costs a model call or a gate run: it applies, targets existing modules and signals, preserves the interface, does not delete assertions or touch verification configuration, and respects size and retry limits.
3. Set an explicit, documented policy for which warnings are fatal.

Exit: compile and elaboration failures become structured, reproducible diagnoses; invalid patches are rejected cheaply.

### Phase 7: Localised, evidence-driven repair

Do

1. Deterministic localisation before any model call [E4, E5]. For simulation failures: earliest mismatching cycle, mismatching outputs, a short window of inputs, resets and state before it, and the source logic in the failing signal's input cone. For formal failures: failed property, the first violating step of the counterexample, relevant signal values, assumptions used in that run, and whether the result is a definitive counterexample, a bounded result, an inconclusive result or a tool failure. Never present a timeout as a functional defect.
2. Route by deterministic rules (syntax, width or sign, interface, reset or clock, simulation mismatch, formal counterexample, ambiguity, environment) exactly as in v1; ambiguity and environment failures stop the loop.
3. Three modes, compared per failure class: R0 blind resampling with the same call budget; R1 minimal patch of the failing code; R2 fresh regeneration from the contract plus a diagnostic hint, without showing the failing code, as an anti-anchoring variant [E7].
4. Provide the model only the relevant contract items, the failed gate, the smallest source excerpt, the compact evidence, the behaviour to fix, what must stay unchanged, and a strict output format. The repairer may not alter expected behaviour or verification configuration.
5. Every applied patch or regeneration is a new candidate and must pass every gate. Budget attempts, model calls and wall-clock.
6. Keep repair enabled only for classes where it measurably beats R0 [E6, E7].

Exit: repair demonstrably fixes reproducible failures beyond what resampling achieves, or it is switched off for that class and the finding is recorded.

### Phase 8: Verified-example memory (gated)

Start only if Phases 2 to 7 leave failures that look pattern-recurring. Store verified examples, failed candidates, inconclusive cases and superseded examples in separate categories; never treat a failed repair as a pattern. Retrieve by transparent matching on design type, widths, arithmetic, reset semantics and failure class; adapt, do not copy, and verify independently. Keep only if paired results improve and no previously passing task regresses. The only published signal found (about +4 points, observational) is weak [E15].

### Phase 9: Fine-tuning (gated)

Proceed only if Phase 2 shows that weights matter on your workload or the remaining failures are consistently pattern-learnable. Published recipes reached strong 7B results with roughly 5,000 to 10,000 functionally or formally verified examples [E2, E11, E1]. Requirements: examples carry specification, validated contract, verified RTL and evidence that all gates passed; failed attempts keep their failure labels; train, validation and evaluation splits are separated by design family; training compute must be checked for feasibility because it likely exceeds the local inference machine. Retain the tuned model only if the frozen comparison and the held-out suite show a measured end-to-end gain.

## 6. Experiment program and statistics

Add one capability at a time; keep tasks, gates, budgets and (where possible) prompts fixed per comparison.

| Run | Configuration | Question | Control |
|---|---|---|---|
| A | Existing baseline | What is the current performance and ceiling? | none |
| A2 | Specialised 7B generator | Do better weights help here? | A |
| B | Best generator + best-of-n | Does verifier-selected sampling help? | n=1 at matched wall-clock |
| C | B + hand-written contracts | What is the upper bound for structure? | B |
| C2 | B + auto-extracted contracts | What does structure give in deployment? | B, C |
| D | + templates | Do arithmetic failures disappear? | report split |
| E | + compiler-feedback adapter | Are failures cheaper to fix? | D |
| F | + localised repair | Does evidence beat resampling? | R0, R1, R2 |
| G | + verified-example retrieval | Does past knowledge help? | F |
| H | + fine-tuned model | Do weights add value beyond A2? | best unmodified |
| Final | Freeze, then run the held-out suite once | What is the real result? | none |

### Statistical rules

1. The unit of analysis is the task. For stochastic generation use at least 5 seeds per task and a per-task pass fraction. Compare configurations on the same tasks and seeds with paired differences; report mean difference, clustered standard error, 95% confidence interval, discordant-task counts and correlation [E14].
2. Suite size: rough McNemar arithmetic says that detecting a 10-point gain with about 20% discordant tasks needs on the order of 150 tasks, and a 20-task suite resolves only very large effects. Run the power calculation with your own discordance rates. In response: (a) grow the dev suite with parameterised variants (widths, signedness, reset styles, terminal counts) whose properties derive from contracts, keeping each family entirely in dev or entirely in held-out; (b) judge small components by per-failure-class counts and mechanism evidence rather than aggregate rates; (c) never claim an aggregate gain from one or two tasks.
3. Compare at matched budgets (model calls, tokens, wall-clock), not matched attempts.
4. The held-out suite is evaluated once after freeze. If it ever informs a change, it becomes dev data and a fresh suite is required.
5. Public benchmarks (VerilogEval, RTLLM) are a secondary, simulation-only sanity check of the generator; record versions. They never replace the full-pipeline evaluation.

Required report per run: raw counts and rates; two headline metrics (system verified rate, and model-generated verified rate excluding template-routed tasks); first-attempt and final rates; pass@1, pass@5 and pass@10; per-gate pass counts; first-failing-gate distribution; failures by root cause; calls, tokens and time per verified task (median and total); environment failures; inconclusive proofs; regressions; negative-control results; and the false-accept count, which must be zero.

Retention rule: keep a component only if it improves paired verified rate with an interval that excludes zero, or reduces cost per verified task at no loss, or fixes a named failure class with mechanism evidence. Otherwise remove it and record why.

## 7. Risk register

| Risk | Mitigation |
|---|---|
| Contract is well-formed but wrong | Provenance, meaning audit, two-condition evaluation, ambiguity registry |
| Properties are vacuous or incomplete | Phase 1: cover witnesses, mutation coverage, negative controls |
| Specification or testbench is itself faulty | Phase 0 audit before any model blame [E11, E16] |
| Specialised model has seen similar data | Dev-only bake-off, overlap check, never reuse held-out |
| Reasoning-model latency on local hardware | Track tokens and time per verified task; consider adaptive-reasoning variants [E2] |
| Template overreach | Reject unsupported combinations; negative variants for every family |
| Repair anchoring or churn | R0 control; R2 regeneration mode; per-class enablement [E7] |
| Dev-suite overfitting | Parameterised variant families, frozen held-out, retention rule |
| Environment limits mistaken for failures or passes | ENVIRONMENT_FAILURE state; never counted either way |
| Measurement noise mistaken for progress | Seeds, paired analysis, power calculation [E14, E15] |

## 8. Definition of done

- The baseline and its ceiling are reproducible, and each task outcome is explained.
- Formal properties are audited; negative controls are rejected; false accepts are zero.
- The generator choice is justified by a paired bake-off.
- Sampling, contracts, templates, compiler feedback and repair are each justified by a controlled run against a stated control, or removed.
- System and model-generated results are reported separately.
- Unsupported and ambiguous cases end in explicit terminal states with evidence.
- All required gates keep their original meaning, and every verified artifact traces to its specification, generation path, patches and logs.
- The final numbers come from one run of a frozen configuration on an untouched suite.

The goal is not a smarter-looking agent. It is more verified RTL from a small local model, at a known cost, with an honest explanation whenever correctness cannot be established.

## 9. Evidence

- E1. Zhu et al., CodeV-R1: Reasoning-Enhanced Verilog Generation, arXiv 2505.24183.
- E2. Qin et al., ReasoningV: Efficient Verilog Code Generation with Adaptive Hybrid Reasoning Model, arXiv 2504.14560.
- E3. Huang et al., QiMeng-CRUX: Narrowing the Gap Between Natural Language and Verilog via Core Refined Understanding eXpression, arXiv 2511.20099 (AAAI 2026).
- E4. Zhao et al., MAGE: A Multi-Agent Engine for Automated RTL Code Generation, arXiv 2412.07822.
- E5. Ho, Ren, Khailany, VerilogCoder: Autonomous Verilog Coding Agents with Graph-based Planning and AST-based Waveform Tracing Tool, arXiv 2408.08927 (AAAI 2025).
- E6. Olausson et al., Is Self-Repair a Silver Bullet for Code Generation?, ICLR 2024, arXiv 2306.09896.
- E7. Try Again, Don't Look Back: Blind Resampling Outperforms Self-Repair in Small Code Models, arXiv 2607.26117 (preprint; Python benchmark).
- E8. How Many Tries Does It Take? Iterative Self-Repair in LLM Code Generation, arXiv 2604.10508 (preprint).
- E9. Tran, Open-Source LLM-Driven Formal Verification: A Multi-Agent Pipeline for RTL Repair, arXiv 2607.28877 (preprint, independent researcher; six-benchmark study).
- E10. VRank: Enhancing Verilog Code Generation from LLMs via Self-Consistency, arXiv 2502.00028.
- E11. Yubeaton et al., VeriThoughts: Enabling Automated Verilog Code Generation using Reasoning and Formal Verification, arXiv 2505.20302.
- E12. AssertLLM2: A Comprehensive LLM Benchmark for Assertion Generation from Design Specifications, arXiv 2605.27472.
- E13. Mutation Cover with Yosys (MCY) documentation, https://mcy.readthedocs.io/ ; ZipCPU, Formally verifying register handling, https://zipcpu.com/blog/2020/12/19/axil-register-checking.html
- E14. Miller, Adding Error Bars to Evals, arXiv 2411.00640; summary at https://anthropic.com/research/statistical-approach-to-model-evals
- E15. ChipCraftBrain: Validation-First RTL Generation via Multi-Agent Orchestration, arXiv 2604.19856.
- E16. Pinckney et al., Revisiting VerilogEval: A Year of Improvements in LLMs for Hardware Code Generation, arXiv 2408.11053.

Limits of this evidence: most numbers come from simulation benchmarks (VerilogEval, RTLLM), several 2026 sources are preprints, E7 is on Python, and E3 and E15 use generators or structure producers different from the Mind-3.0 stack. Treat every figure as a prior to be replaced by Mind-3.0's own measurements.
