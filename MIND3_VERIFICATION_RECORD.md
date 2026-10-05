# Mind-3.0 — Verification Record, Capabilities, and Roadmap

> Single-file account of what Mind-3.0 is, what has been proven with
> executed evidence on Linux, what remains blocked, and what to do next.
> Frozen benchmark evidence is historical and preserved verbatim.
> All capability claims below rest on executed tool output, never on
> green counts alone.

---

## 1. What Mind-3.0 Is

Mind-3.0 is a hierarchical RTL silicon-signoff agent. Given a natural-language
specification it generates SystemVerilog and drives it through a fail-closed,
six-gate verification pipeline with bounded repair:

| Gate | Name | Tool | Status on Linux |
|------|------|------|-----------------|
| 1 | Yosys elaboration, latch trap, structural contract check | Yosys 0.33 / OSS CAD Suite 0.69+77, Icarus, Verilator | PASS (live) |
| 1b | Logic equivalence (opt-in) | Yosys | PASS |
| 3 | Verilator simulation + coverage signoff (branch ≥95%, toggle ≥90%) | Verilator 5.020 | PASS (live) |
| 2 | SymbiYosys formal/BMC + cover attribution | SBY 0.69, Z3 4.8.12 | PASS (live) |
| 4 | OpenSTA multi-corner timing (WNS ≥ 0 ps) | OpenSTA 2.3.1 + real SKY130 Liberty | PASS (live, env-supplied PDK) |
| 5 | OpenROAD place-and-route (opt-in) | OpenROAD (hash `f12e2f4…`) | PASS (live SKY130 canary) |
| 6 | Yosys CDC static analysis | — | Honestly unavailable (see §5) |

Execution is sandboxed in Bubblewrap (`--unshare-all`, PID + network
namespaces, egress blocking), all verified live. Default model/provider:
`ollama` / `qwen2.5-coder:7b`, strict parser, repair budget 3.

---

## 2. Current Verified State (Linux)

* Full regression: **342 passed, 2 skipped, 0 failed.**
  Skips are environmental only: macOS Seatbelt test (Darwin-only) and
  `cdc_violation` (no CDC command in either Yosys build).
* Negative controls: **15 PASS / 0 FAIL / 1 SKIP** (cdc), verdict SUCCESS,
  all `simulated=false`, sandboxed.
* Sandbox: namespace probe PASS; PID isolation PASS (PID 2 in-namespace);
  egress blocking PASS (`Network is unreachable` in-sandbox, reachable outside).
* Timing: real SKY130 TT Liberty loads in OpenSTA (RC=0); timing-violation
  fixture yields genuine `TIMING_SLACK_VIOLATION` (WNS −0.38 ns).
* Formal/coverage parsing, PDK-gate canaries, claim hygiene, and fixture
  honesty checks all pass.

---

## 3. What Was Done — Commendable Work Log

Genuine defects found by evidence and fixed minimally (each with
before/after executed proof; full detail in `audit/LINUX_FIX_SESSION_2026-10-04.md`):

1. **Bubblewrap usrmerge probe** — the capability probe bound `/usr`+`/bin`
   but not `/lib`+`/lib64`, testing a broken root the real sandbox never
   uses. Mirrored the real binds; probe now reports truthfully. Isolation
   itself was never weakened.
2. **Verilator `coverage.dat` parsing** — parser ignored the `page`
   (`v_toggle`/`v_branch`/`v_line`) field, reporting 0% on 100%-covered
   designs. Fixed parsing only; thresholds untouched.
3. **SBY cover attribution** — parser accepted only step-before-location
   order; SBY 0.69 emits step-after. Both orders accepted; semantics unchanged.
4. **Ollama JSON-forcing mismatch** — driver forced `"format":"json"` while
   the prompt demanded raw Verilog; the model emitted lossy AST dicts
   (`"rhs": 80` for `8'hFF`-class constants) rejected by every parser mode.
   RTL generation/repair now request text; JSON kept where parsers consume it.
5. **Exact module-header presentation** — `"[1 bits]"` prose was misread as
   range `[1:0]` on every 1-bit port. The prompt now shows the exact
   SystemVerilog header (proven by A/B/C test; prose-only alternative proven
   harmful to wide ports and rejected).
6. **POSIX EOF-newline artifact** — missing trailing newline failed
   Verilator `-Wall` builds on otherwise valid RTL, burning all repairs.
   Write path POSIX-terminates files (zero Verilog semantics); lint strictness
   kept.
7. **Stale `_netlist.v` contamination** — repair rewrote `<top>.sv` while the
   previous netlist remained; recompile declared the module twice. Derived
   artifacts excluded from compile inputs (Gate 1 regenerates them; Gate 4
   selects them explicitly).
8. **SBY workdir copy contamination** — SymbiYosys `<top>/src/` copies were
   picked up by the recursive source scan on re-verify. Discovery is now
   top-level-only via tested `discover_rtl_sources()`, matching every other
   lookup in the pipeline.
9. **Latch-trap accuracy, both directions** — the log regex flagged Yosys
   `ff.cc` optimizer chatter (`$dlatch` tags on transient cells) while the
   clean AST was overruled (3 tasks falsely failed); meanwhile the lexical
   check missed the `always @(*)` form and the AST compare missed
   `$_DLATCH_P_` case variants (true latches passed). Verdict now comes from
   the structured AST exclusively, both forms covered, proven live both ways.
10. **Environment-aware Liberty resolution** — Ciel's PDK was proven to
    contain no timing Liberty; the real pre-existing PDK at
    `~/pdk/sky130A/sky130A` is used only via explicit
    `MIND3_NEGATIVE_CONTROL_LIBERTY` / `MIND3_SKY130_ROOT` configuration,
    never fabricated; packaged fixture preserved as fallback.
11. **Claim hygiene without git, OpenROAD hash-version acceptance** — both
    legitimate test-compatibility fixes with detection strength preserved.

Nothing was ever fixed by weakening a gate, threshold, parser, classifier,
budget, or semantic — and several tempting weakenings (prose-only widths,
AST reconstruction, lint relaxation, failure-to-skip) were explicitly
tested and rejected on evidence.

---

## 4. Proven Capabilities (What the System Can Actually Do)

* Generate interface-correct, compiling SystemVerilog from spec (parse 10/10,
  Gate-1 width errors 0/10 across independent samples).
* Elaborate, lint, simulate, cover, formally verify, time-analyze, and
  place-and-route real RTL with real EDA tools in a real sandbox.
* Detect: latch inference, combinational loops, formal breaches, simulation
  failures, coverage deficits, timing violations — each with live tool traces.
* Repair loop that consumes verifier evidence and moves candidates across
  real gates (observed `FORMAL→COVERAGE`, `ELABORATION→COVERAGE`,
  `SYNTAX→COVERAGE` transitions) within budget 3 with patch-size enforcement.
* Reject what it cannot prove: CDC absence fails closed, unparseable output
  fails closed, missing tools fail closed. No mocks in any live path.

---

## 5. Honest Limitations (Measured, Not Hidden)

1. **Model quality ceiling.** `qwen2.5-coder:7b` produces wrong algorithms
   (Gray/Johnson/BCD/signed/divider), vacuous logic, latch-prone and
   uncovered RTL, and repairs that repeat mistakes or dodge properties rather
   than implement behavior. 0 verified across Stage 12/14/16 samples with a
   fully-executing pipeline. This is a measured model ceiling, not a harness
   wall.
2. **CDC genuinely unavailable.** `help cdc` → `No such command` on both
   Yosys builds; no plugin, no alternate tool on the machine. Gate 6 stays
   `CDC_TOOLING_UNAVAILABLE` pending human-procured tooling.
3. **Frozen 120-task benchmark: 0/120 verified** (119 parse failures under the
   old JSON-forced integration + 1 spec defect). Historical; preserved.
4. **Thin specs + stimulus bounds.** One-line behavioral specs underdetermine
   algorithms; auto-generated testbenches bound achievable coverage.
5. **`$dffsr`/`$sr` latch-list membership** unreviewed (no case observed).

---

## 6. How to Reproduce the Key Evidence

```bash
cd ~/Desktop/Mind-3.0-main
source .venv/bin/activate
export PATH="$HOME/.local/bin:$PATH" PYTHONPATH=src
export MIND3_EDA_READONLY_PATHS="$HOME/.local:$HOME/openroad-env:/home/mind/oss-cad-suite:/home/mind/pdk"
export MIND3_NEGATIVE_CONTROL_LIBERTY="/home/mind/pdk/sky130A/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
export MIND3_SKY130_ROOT="/home/mind/pdk/sky130A/sky130A"

python -m pytest -ra                                   # expect 342 passed, 2 skipped
python scripts/run_negative_controls.py --require-live  # expect 15 PASS / 1 SKIP, SUCCESS
yosys -p "help cdc" 2>&1 | tail -n 3                    # expect: No such command
sha256sum benchmarks/heldout/tasks.jsonl               # expect bae56a8d…dd2c24
```

---

## 7. What To Do Next (Recommended Order)

1. **Declare the harness phase complete.** Further prompt tweaks without a
   causal hypothesis have repeatedly measured ~zero. Protect the 342-test
   suite and frozen evidence as the core assets.
2. **Make the model decision explicit.** Either re-scope around 7b as a
   drafting assistant with the verifier as the product, or authorize a
   stronger-model evaluation under a documented protocol change (all current
   evidence is pinned to 7b and would need re-measurement).
3. **Cheapest model-side experiments first, if any:** a repair-correctness
   discriminator (repairs currently dodge properties) and stimulus-rich
   coverage harnesses — both cheaper than chasing generation quality.
4. **Human-procured items:** CDC-capable toolchain; ≥100-task release
   evidence once generation merits measuring; license choice.
5. **Any future model swap must re-run — never reinterpret — the regression,
   negative controls, sandbox, PNR, timing, and benchmark evidence.**

---

## 8. Release Readiness

**NOT READY.** Infrastructure is genuinely hardened and honestly measured;
the pinned model cannot produce verified hardware. No public-beta claim is
supported by the evidence. The correct next gate is the model decision in §7.
