# Gate 2 — Formal Verification Strength (Stage 4b)

Gate 2 (`_run_gate2_formal_sby` in `src/mind3/core/verifier.py`) checks
typed bounded-property templates (a supported subset of SVA) with
SymbiYosys (`smtbmc z3`, BMC depth 25). Contracts select templates;
Mind-3.0 owns the SystemVerilog rendering (`compile_formal_property`).
Legacy free-form SVA is accepted only when the bounded classifier
(`classify_legacy_property`) maps it without changing its meaning;
otherwise the property fails closed with `UNSUPPORTED_FORMAL_PROPERTY`.

## Supported temporal subset (all live-tested with real SBY)

| Construct | Supported? | Real SBY tested? | Behavior |
| --------- | ---------- | ---------------- | -------- |
| `\|->` (same-cycle) | Yes | Yes (broken RTL caught) | `if (ant) assert (cons)` |
| `\|=>` (next-cycle) | Yes | Yes (broken caught, correct passes exercised) | `if ($past(ant)) assert (cons)` |
| `##1` (bare delay) | No | N/A (fail-closed test) | `UNSUPPORTED_FORMAL_PROPERTY` |
| `a \|=> ##1 b` | No | N/A (fail-closed test) | Means `a \|-> ##2 b`; rejected rather than rewritten |
| `$past(id[, 1..8])` | Yes | Yes (broken `past_equals` caught) | Bounded history in `past_equals`, `past_stable`, `past_expression` |
| `$rose` | No | N/A (fail-closed test) | `UNSUPPORTED_FORMAL_PROPERTY` |
| `$fell` | No | N/A (fail-closed test) | `UNSUPPORTED_FORMAL_PROPERTY` |
| `$stable(id)` | Yes | Yes (toggling signal caught) | Classified to `past_stable`, rendered as `sig == $past(sig, cycles)` |

Note: `$stable` is accepted by spelling but rendered in its `$past`
equivalent form. `|-> ##1` (same-cycle plus explicit delay) is likewise
unsupported: a same-cycle check cannot also wait a cycle.

## Vacuity: exercised vs unexercised passes

A passing implication whose antecedent never held proves nothing. After a
clean BMC run, Gate 2 executes one SBY `mode cover` job (same depth, 25)
over cover points that mirror each implication's evaluation condition
exactly (`compile_cover_point`; same guard, `$past(antecedent)` for
next-cycle). Each cover is attributed to its property via generation-time
source lines matched against executed witness locations.

- Antecedent(s) reached within bound → ordinary `PASS` (`vacuity.status:
  EXERCISED`, per-antecedent steps recorded).
- Antecedent(s) never reached within bound → `VACUOUS_PROPERTY`
  (`passed: False`, unexercised names listed). Never an ordinary PASS.
- No implication antecedents (boolean/onehot/reset/past properties, or a
  user-supplied harness) → `PASS` with `vacuity.status: NOT_APPLICABLE`.
  Vacuity assessment applies to implication antecedents only.
- Cover execution itself fails or its output is unattributable →
  `FORMAL_ANALYSIS_FAILED` (`passed: False`). Lack of reachability
  evidence is never treated as exercise.

This is bounded antecedent reachability, not unbounded vacuity analysis:
both depths are recorded (`bmc_depth`, `vacuity.assert_depth`,
`vacuity.cover_depth`, all 25) and nothing is claimed "proven for all
possible cycles".

## Result states

- `PASS` — BMC clean to the recorded bound; every implication antecedent
  reached, or no antecedents to assess.
- `FAIL` (`FORMAL_INVARIANT_BREACH`) — solver produced a counterexample;
  step, failing assertion, VCD witness path, and witness text are preserved.
- `VACUOUS` (`VACUOUS_PROPERTY`) — BMC clean but antecedent(s)
  unexercised; fails closed.
- `UNSUPPORTED` (`UNSUPPORTED_FORMAL_PROPERTY`) — construct outside the
  subset; fails closed before any tool runs.
- `ANALYSIS ERROR` (`FORMAL_ANALYSIS_FAILED`, `EDA_BINARY_MISSING`,
  `MISSING_VERIFICATION_ARTIFACT`, `EMPTY_FORMAL_PROPERTY_SET`) —
  the engine/harness itself could not run; fails closed.

## Current template limitation (honest scope note)

The typed next-cycle template guards on the current cycle only
(`!init && reset-inactive`). A solver-chosen reset-deassertion edge can
therefore fail a property whose antecedent held only during reset. Live
temporal tests use reset-free, free-running fixtures so that only genuine
timing mismatches can fail; reset-adjacent vacuity semantics are unchanged
(the guard is mirrored exactly by the cover). Reworking reset gating is
explicitly out of scope for this stage.
