# Mind 3.0 — Linux Fix Session 2026-10-04

Workdir: `/home/mind/Desktop/Mind-3.0-main` (no `.git`; Git commands unavailable, nothing initialized/committed/pushed).
Venv: existing `.venv`, `source .venv/bin/activate`, `PATH=$HOME/.local/bin:$PATH`, `PYTHONPATH=src`.
Labels: `[VERIFIED]` executed output, `[UNVERIFIED]` not demonstrated, `[PENDING-HUMAN]` needs human/CI asset, `[AGENT-SUPPLIED]` note.

## Baseline (before fixes this session)

```text
python --version => Python 3.12.3
pytest --version => 9.1.1 (venv) / 8.4.2 also observed earlier after reinstall
sby --version => SBY v0.69
bwrap --version => bubblewrap 0.9.0
yosys -V => Yosys 0.33 (git sha1 2584903a060)
verilator --version => Verilator 5.020
openroad -version => f12e2f474102bfb875eeee57fb610d7d7de17770 (exit 0)
sta -version => 2.3.1 (exit 0)
z3 --version => Z3 version 4.8.12 - 64 bit
python -m pytest -ra => 7 failed, 307 passed, 6 skipped in ~29s
  FAILED test_claim_hygiene::test_banned_marketing_terms_enforced
  FAILED test_fixtures_canary::test_environment_eda_tool_availability_honesty
  FAILED test_gate2_mandatory::test_3_seq_pass
  FAILED test_gate2_temporal_live::test_temporal_next_cycle_correct_passes_exercised_live
  FAILED test_linux_toolchain::test_opensta_smoke_version_and_workload
  FAILED test_negative_controls::test_affected_negative_control_reaches_intended_gate_live[timing_violation]
  FAILED test_p5_coverage::test_p5_valid_fixture_pass
```

- `[VERIFIED]` Baseline numbers are exact `pytest -ra` output at session start.

## Source change 1 — Bubblewrap probe usrmerge binds

File: `src/mind3/sandbox/bwrap.py`, `probe_bubblewrap_namespace_capability()`.

Reason: evidence showed `/bin->usr/bin`, `/lib->usr/lib`, `/lib64->usr/lib64`; `bwrap` with only `--ro-bind /usr /usr --ro-bind /bin /bin` fails with `execvp /bin/true: No such file`, while adding `--ro-bind /lib /lib --ro-bind /lib64 /lib64` succeeds (exit 0). The real `BubblewrapSandbox.run()` already binds `/lib` and `/lib64` (lines 105-111); the probe did not, so it tested a different, broken root from the real sandbox. Fix mirrors the real sandbox binds, preserves `--unshare-all --die-with-parent --new-session --proc /proc --dev /dev --tmpfs /tmp`, real `/bin/true`, failure-closed semantics, no isolation disabled.

Diff:
```python
# before: probe_cmd ended with --ro-bind /usr /usr --ro-bind /bin /bin -- /bin/true
# after:
probe_cmd = [..., "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
             "--ro-bind", "/lib", "/lib"]
if Path("/lib64").exists():
    probe_cmd.extend(["--ro-bind", "/lib64", "/lib64"])
probe_cmd.extend(["--", "/bin/true"])
```

Before: `(False, 'bwrap namespace creation unavailable (exit 1): bwrap: execvp /bin/true: No such file or directory')`.
After:
```text
$ python -c "from mind3.sandbox.bwrap import probe_bubblewrap_namespace_capability as p; print(p())"
(True, 'bwrap created namespaces and executed the probe payload')
```
- `[VERIFIED]` Probe now correctly recognizes this Linux host. No hardcoded True; failure modes (missing binary/timeout/OSError/nonzero) still return False.

## Source change 2 — Verilator coverage.dat `page` parsing

File: `src/mind3/core/verifier.py`, `parse_coverage_dat_file()`.

Reason: `test_p5_valid_fixture_pass` reported `branch=0.0% toggle=0.0%` while `coverage.dat` demonstrably contained 7 `v_toggle`, 2 `v_line`, 2 `v_branch` hits. Raw bytes show `\x01page\x02v_toggle/...`; parser only looked for `\x01t\x02(\w+)`, so it returned `{'toggle':None,'branch':None,'line':None}` and Gate 3 failed closed to 0.0%. Fix additionally parses the `page` field and strips the `v_` prefix (`v_toggle`→`toggle`, etc.). Thresholds still enforced; no gate weakened.

Before: `parsed: {'toggle': None, 'branch': None, 'line': None}`, Gate 3 `COVERAGE_DEFICIT 0.0%`.
After: `passed=True Coverage signoff criteria satisfied: branch=100.0%, toggle=100.0%`, `pytest tests/test_p5_coverage.py => 1 passed`.
- `[VERIFIED]` Underlying coverage execution was working; only the parser was wrong.

## Source change 3 — SBY cover step-order parsing

File: `src/mind3/core/verifier.py`, `parse_sby_cover()`.

Reason: `test_3_seq_pass` and `test_temporal_next_cycle_correct_passes_exercised_live` failed with `cover output unattributable for: reset_val / req_next_gnt`. Captured SBY 0.69 output is `Reached cover statement at seq_reg_cover.sv:15.15-15.30 (...) in step 2.` (step after location); parser only accepted `Reached ... in step N at <loc>` (step before). Fix accepts both orders; `Unreached` handling unchanged; no property semantics changed.

Before: both tests FAILED with `COVER_ERROR ... unattributable`.
After: `tests/test_gate2_mandatory.py tests/test_gate2_temporal_live.py => 20 passed`.
- `[VERIFIED]` BMC proof found no counterexample in both cases; only antecedent-attribution was broken.

## sandbox capability

- `[VERIFIED]` `probe_bubblewrap_namespace_capability()` now `(True, ...)`.
- `[VERIFIED]` `tests/test_mind3.py tests/test_sandbox_capability.py tests/test_macos_sandbox.py => 130 passed, 1 skipped` (only macOS Seatbelt skip remains; prior `test_mind3.py:3419` bwrap skip is gone).

## network isolation (repository path)

```text
PROBE capable=True
BubblewrapSandbox(ws).run(["/bin/echo","BWRAP_REPO_SANDBOX_OK"]) => rc=0 stdout='BWRAP_REPO_SANDBOX_OK'
PID check => `PID=2` (new PID namespace; host PIDs are large)
HOST_NET=SUCCESS (1.1.1.1:80 reachable)
SANDBOX_NET via BubblewrapSandbox ws-bound netprobe.py + /usr/bin/python3 => `SANDBOX_NET=FAIL:[Errno 101] Network is unreachable` rc=0
LocalBwrapRunner(ws, sandbox=sb) => mode=local_bwrap available=True sandboxed=True; run echo => rc=0
```
- `[VERIFIED]` Normal execution, namespace isolation (PID 2), and egress block all proven through `BubblewrapSandbox`/`LocalBwrapRunner`, no fallback (`sandbox is not None`, `allow_unsandboxed=False` in probe).

## OpenSTA status

- `[VERIFIED]` `sta -version => 2.3.1 exit 0`, but workload `test_opensta_smoke_version_and_workload` still FAILS: `Library ... is missing one or more thresholds` plus missing `rise/fall_transition` warnings, `sta -exit smoke.tcl rc=1`.
- Diagnosis: (B) deliberately minimal 201-line/4.8 KiB single fixture incompatible with OpenSTA 2.3.1 strictness + (C) missing real PDK assets. Invocation (D) is correct; implementation (A) is not buggy.
- No Liberty invented, no test weakened. Classified `[PENDING-HUMAN] full Sky130/OpenSTA evidence`.

## OpenROAD status

- `[VERIFIED]` `openroad -version` executes (hash output, exit 0). No PnR workload executed; `test_openroad_smoke_version` only asserts version output. Genuine PnR remains `[PENDING-HUMAN]` / `[UNVERIFIED]`. Binary execution is not conflated with PnR verification.

## CDC status

```text
$ yosys -p "help cdc" => No such command or cell type: cdc (0.33)
$ /home/mind/oss-cad-suite/bin/yosys -p "help cdc" => No such command or cell type: cdc (0.69+77)
```
- `[VERIFIED]` CDC still unavailable in both builds. `cdc_violation` remains SKIP / `CDC_TOOLING_UNAVAILABLE`. No fake CDC pass created.

## Gate 2 status

- `[VERIFIED]` After cover-parser fix: `test_gate2_mandatory.py + test_gate2_temporal_live.py => 20 passed`, including the two previously failing `test_3_seq_pass` and `test_temporal_next_cycle_correct_passes_exercised_live`. No property semantics changed.

## negative-control status

Default host layout (HOME tools not bound; `MIND3_EDA_READONLY_PATHS` unset):
```text
4 PASS (fifo_overflow, fifo_underflow, sim_behavioral_failure, coverage_deficit),
10 FAIL (latch/comb => SYNTAX_ERROR via verilator fallback because sandboxed iverilog missing;
         8x formal => EDA_BINARY_MISSING because sandboxed sby missing),
2 SKIP (cdc_violation CDC_TOOLING_UNAVAILABLE; timing_violation no PDK),
Verdict: FAILURE, but all sandboxed=True, simulated=False (fail-closed, honest).
```

Sandbox-configured (`export MIND3_EDA_READONLY_PATHS="/home/mind/.local:/home/mind/openroad-env:/home/mind/oss-cad-suite"`):
```text
14 PASS, 2 SKIP (cdc_violation, timing_violation), Verdict: SUCCESS
sandboxed=true: 15, simulated=false: 15 (SKIPPED_NO_PDK has nulls)
execution_mode=local_bwrap where diagnostics record it (Gate 1/3); formal Gate 2 reports sandboxed=True via runner
```
- `[VERIFIED]` Probe fix exposes a real deployment requirement: HOME-installed EDA (`~/.local/bin/iverilog`, `sby`; `~/openroad-env/bin/sta`) is invisible inside the secure sandbox unless explicitly bound via `MIND3_EDA_READONLY_PATHS` (CI uses `/opt/oss-cad-suite`). No home path was baked into source; configuration, not code, resolves it. Final `artifacts/negative_controls_report.json` left in SUCCESS (configured) state; both modes documented.

## complete pytest status (after legitimate fixes, default env)

```text
$ python -m pytest -ra
4 failed, 311 passed, 5 skipped in ~29s
FAILED test_claim_hygiene::test_banned_marketing_terms_enforced (git ls-tree exit 128: not a git repository)
FAILED test_fixtures_canary::test_environment_eda_tool_availability_honesty (openroad hash lacks name)
FAILED test_linux_toolchain::test_opensta_smoke_version_and_workload (Liberty thresholds)
FAILED test_negative_controls::test_affected_negative_control_reaches_intended_gate_live[timing_violation] (TIMING_REPORT_UNPARSEABLE)
SKIPPED macOS Seatbelt, cdc_violation (no cdc), 3x PDK canaries
0 xfailed, 0 errors
```
- `[VERIFIED]` Improved 7F→4F without weakening gates. The 4 remaining are honest blockers (see below), not fixed by editing expectations.

## remaining blockers (evidence-backed only)

1. `[VERIFIED]` CDC unavailable on both Yosys builds — Gate 6 pending.
2. `[VERIFIED]` Bundled Liberty insufficient for OpenSTA 2.3.1 — timing evidence pending full PDK (`[PENDING-HUMAN]`).
3. `[VERIFIED]` HOME-tool sandbox visibility requires `MIND3_EDA_READONLY_PATHS`; default run fails closed sandboxed (not a source bug).
4. `[VERIFIED]` `test_claim_hygiene` needs `.git` (`git ls-tree` exit 128); workdir has no `.git` — environment mismatch, test untouched per no-skip rule.
5. `[VERIFIED]` `test_environment_eda_tool_availability_honesty` over-strict for hash-only `openroad -version`; left failing rather than editing expectations.
6. `[PENDING-HUMAN]` Full PDK, CDC-capable Yosys, OpenROAD PnR, release ≥100-task heldout, license choice.

## commands run (abridged)

`python --version; pytest --version; sby --version; bwrap --version; yosys -V; verilator --version; openroad -version; sta -version; z3 --version; python -m pytest -ra; sed bwrap.py; probe direct; BubblewrapSandbox direct (echo/pid/net/runner); pytest sandbox trio; run_negative_controls (default + configured); OpenSTA manual tcl; timing sv/sdc inspect; claim/fixture pytest -vv; p5 single + parser debug; gate2 -vv; yosys help cdc x2; final pytest -ra; final negative controls (configured).`

---

# Append 2026-10-04 Phase 2 — claim hygiene + OpenROAD canary (no PDK fabrication)

## Phase 1 reproduce
```text
python -m pytest -q tests/test_claim_hygiene.py tests/test_fixtures_canary.py tests/test_linux_toolchain.py tests/test_negative_controls.py
4 failed, 39 passed, 1 skipped
FAILED test_banned_marketing_terms_enforced (git ls-tree exit 128)
FAILED test_environment_eda_tool_availability_honesty (openroad hash)
FAILED test_opensta_smoke_version_and_workload (thresholds)
FAILED test_affected_negative_control_reaches_intended_gate_live[timing_violation] (TIMING_REPORT_UNPARSEABLE)
```
`[VERIFIED]` Exact reproduction of the 4 stated failures.

## Phase 2 claim hygiene — legitimate archive fallback
File: `tests/test_claim_hygiene.py`.
Root cause: test used `git ls-tree -r --name-only HEAD` as sole file source; ZIP download has no `.git`, so `CalledProcessError exit 128` before any banned-term check. Contract intent is banned-term detection, not git presence.
Fix: try git; on `CalledProcessError/FileNotFoundError` fall back to filesystem `rglob` with same suffix/skip semantics, excluding `.git/.venv/.pytest_cache/egg-info/__pycache__/*.pyc` (build artifacts, not repo content). Detection logic, banned list, allowlist unchanged.
Evidence:
```text
python -m pytest -q tests/test_claim_hygiene.py::test_banned_marketing_terms_enforced => 1 passed
Inject TEMP_BANNED_CHECK.md with 'tapeout ready' => 1 failed with violation line (detection intact); removed => 1 passed
```
`[VERIFIED]` Fix preserves strictness; no skip, no weakening, no git init.

## Phase 3 OpenROAD canary — hash compatibility
File: `tests/test_fixtures_canary.py::test_environment_eda_tool_availability_honesty`.
Root cause: test required version string to contain tool name (except `sta`); real `openroad -version => f12e2f474102bfb875eeee57fb610d7d7de17770 rc=0`, `openroad -help` shows genuine `Usage: openroad [-help] [-version]...` — hash-only version is genuine, not broken.
Fix: accept for `openroad` only a hex commit id `\b[0-9a-f]{7,40}\b` as version evidence, in addition to name/allowlist. No hardcoded hash, not `assert exists`, garbage (`hello world`, empty) still rejected (verified by regex check).
Evidence: `pytest -q ...test_environment_eda_tool_availability_honesty => 1 passed`.
`[VERIFIED]` Genuine execution recognized without accepting arbitrary text.

## Phase 4 OpenSTA root cause — honest blocker
```text
find . -name '*.lib|*.lef|*.sdc' -not -path './.venv/*' =>
  ./src/mind3/pdata/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib
  ./tests/negative_controls/timing_violation.sdc
wc -l lib => 201
Exact workload (read_liberty <abs lib>; read_verilog; link_design; read_sdc; report_checks) =>
  rc=1, Error: Library ... is missing one or more thresholds + missing rise/fall_transition warnings
```
`[VERIFIED]` Implementation correct, fixture insufficient, no other legitimate fixture exists. No Liberty fabricated, test unchanged. `[PENDING-HUMAN] full OpenSTA/Sky130 timing evidence`.

## Phase 5 timing control — downstream, no classifier change
Manual `run_control_case(timing_violation, liberty=[bundled lib])` => `observed=TIMING_REPORT_UNPARSEABLE rc=1`, stdout tail is the same Liberty threshold error; no WNS produced so parser correctly reports unparseable. Not an independent parser bug. Classifier untouched; missing evidence not transformed into `TIMING_SLACK_VIOLATION`.
`[VERIFIED]` Downstream of Phase 4 blocker.

## Phase 6 full test
```text
python -m pytest -ra => 2 failed, 313 passed, 5 skipped
FAILED test_opensta_smoke_version_and_workload
FAILED test_affected_negative_control_reaches_intended_gate_live[timing_violation]
SKIPPED macOS Seatbelt, cdc_violation (no cdc), 3x PDK canaries
python scripts/run_negative_controls.py --require-live (MIND3_EDA_READONLY_PATHS=/home/mind/.local:/home/mind/openroad-env:/home/mind/oss-cad-suite)
  => 14 PASS, 2 SKIP (cdc, timing), Verdict SUCCESS, sandboxed=true:15 simulated=false:15
probe => (True, 'bwrap created namespaces and executed the probe payload')
yosys -p "help cdc" (both builds) => No such command or cell type: cdc
```
`[VERIFIED]` 4F→2F via the two legitimate test-compat fixes above plus prior session fixes intact.

## Phase 7 weakening check
- Gate thresholds `min_branch 95.0 / min_toggle 90.0` unchanged; coverage fix only parses correctly.
- Benchmark/model/provider/dataset unchanged; formal semantics unchanged (cover step-order only).
- Sandbox `bwrap.py` unchanged this phase (prior usrmerge fix intact, still `--unshare-all`).
- No mocks introduced; no failure→skip conversions (claim test still fails on injected term; OpenROAD still rejects garbage; OpenSTA/timing left failing honestly).
- Changed files this phase: `tests/test_claim_hygiene.py`, `tests/test_fixtures_canary.py` (+ prior `src/mind3/sandbox/bwrap.py`, `src/mind3/core/verifier.py`).

## Remaining
`[VERIFIED]` OpenSTA workload FAIL (thresholds), timing control UNPARSEABLE (downstream), CDC unavailable both builds, OpenROAD PnR not executed, full PDK absent. `[PENDING-HUMAN]` full timing/PDK/CDC/PnR.

---

# Append 2026-10-04 Phase 3 — Real SKY130 timing via environment-supplied Liberty (no fixture fabrication)

## PHASE 1 — Real PDK discovery

```text
$ ciel ls --pdk-family sky130 => 1e3554706ddbb2529193bdabbc7128296f3cb44a (exit 0)
$ find "$HOME/.ciel" -name "*.lib" | wc -l => 0
$ find "$HOME/.ciel" ... | grep sky130_fd_sc_hd => (no .lib; only 4 .lef for ef/fd io_core)
$ ls <ciel-sky130A>/libs.tech/librelane/sky130_fd_sc_hd/ => config.tcl, *_map.v, tracks.info (9 files, no .lib)
```

- `[VERIFIED]` The Ciel-installed PDK contains device/SPICE tech data and librelane
  synthesis maps but **no standard-cell timing Liberty** (`sky130_fd_sc_hd`
  `lib/*.lib` absent). The task premise "Real SKY130 PDK is being installed
  with Ciel" is not borne out for timing purposes on this host.
- `[VERIFIED]` A complete pre-existing real PDK was found outside Ciel at
  `/home/mind/pdk/sky130A/sky130A` (dated Aug 2023, not created this session):

```text
$ ls -lh .../libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib => 13M (12841859 bytes), 173163 lines
$ sha256sum => 8725d472becbb2d016ee59cdc0207e1102f24a5c6f5fb4ed194cecc278372575
$ grep -c "cell (" => 452 cells; thresholds present (input_threshold_pct_*, slew_*_threshold_pct_*)
$ ls .../libs.ref/sky130_fd_sc_hd/{lef,techlef}/ => sky130_fd_sc_hd.lef, sky130_fd_sc_hd__nom.tlef present
```

- `[VERIFIED]` The repository's packaged fixture
  `src/mind3/pdata/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib` is untouched
  (still 201 lines / 4.8 KiB). No Liberty was generated or fabricated.
- `[VERIFIED]` Exact real Liberty selected for the timing flow:
  `/home/mind/pdk/sky130A/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib`
  (TT 025C 1v80 corner, matching the fixture's nominal corner name).

## PHASE 2 — Independent OpenSTA proof against the real library

Workload (in `/tmp/opencode/sta_real`, **not** the repo fixture):

```tcl
read_liberty /home/mind/pdk/sky130A/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
read_verilog smoke_real.v
link_design smoke
read_sdc smoke_real.sdc
report_checks
```

```text
$ sta -exit smoke_real.tcl => RC=0
stdout: "OpenSTA 2.3.1 ..." + "No paths found." (expected: combinational passthrough, no clocked paths)
```

- `[VERIFIED]` `read_liberty` succeeds (no threshold errors), `read_verilog`,
  `link_design`, `read_sdc`, `report_checks` all succeed, return code 0.
  `sta -version => 2.3.1`. This is an availability proof, not timing signoff.
- `[VERIFIED]` A clocked flop pipeline against the same library yields real
  numbers (see Phase 5): `slack (VIOLATED)`, `wns -0.38`.

## PHASE 3 — Timing library resolution architecture

Existing mechanisms found (no new config invented beyond unifying them):

- `MIND3_SKY130_ROOT` — full PDK root (`tests/test_pdk_gates_canary.py`,
  derives `libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib`).
- `MIND3_NEGATIVE_CONTROL_LIBERTY` — colon-separated liberty list
  (`scripts/run_negative_controls.py`, docs/benchmarks.md).
- `MIND3_LIBERTY_PATH` — single liberty path (`scripts/run_redteam.py`,
  `scripts/prove_four_cases.py`).

New minimal helper `src/mind3/eda/timing_liberty.py::resolve_timing_liberty()`
(precedence: `MIND3_NEGATIVE_CONTROL_LIBERTY` > `MIND3_LIBERTY_PATH` >
`MIND3_SKY130_ROOT`-derived > packaged fixture; env entries selected only
when they are real non-empty files; returns `(None, "missing")` otherwise —
never generates content).

## PHASE 4 — Environment-aware OpenSTA smoke test (legitimate)

File: `tests/test_linux_toolchain.py::test_opensta_smoke_version_and_workload`.

- Uses `resolve_timing_liberty()`; packaged fixture stays as fallback/reference.
- Still proves actual execution (`sta -version` rc=0, workload rc=0,
  `"OpenSTA"` in output). Assertion strength unchanged (rc==0 required).
- Fails closed when no Liberty exists at all (verified: with all three env
  vars unset the test FAILs on the minimal fixture's threshold error — no
  skip conversion).

New regression coverage: `tests/test_timing_liberty_resolution.py` (5 tests:
fixture fallback, env precedence, missing-entry fall-through, SKY130_ROOT
derivation, empty-file rejection).

## PHASE 5 — Timing negative control through real evidence only

Root cause (evidence-backed, not a classifier bug):

- `tests/negative_controls/timing_violation.sv` instantiated
  `sky130_fd_sc_hd__dfxtp_1` with **lowercase** pins (`.clk/.d/.q`), matching
  the minimal fixture but **not** the real PDK, whose cell pins and Verilog
  model are **uppercase** (`CLK/D/Q`, confirmed in
  `libs.ref/.../lib` cell `"sky130_fd_sc_hd__dfxtp_1"` and
  `verilog/sky130_fd_sc_hd.v:33146`).
- Against the real library the raw fixture produced 96x
  `port ... not found` warnings, `No paths found.`, `wns 0.00` =>
  `passed=True, observed=None` (no violation to detect). Parser output
  `{'setup_wns': 0.0, ...}` was correct for that output; classifier untouched.

Minimal fixture correction (test data only — Liberty fixture, thresholds,
classifier, and SDC all untouched):

- `tests/negative_controls/timing_violation.sv`: `.clk(` -> `.CLK(` (32x),
  `.d(` -> `.D(` (32x), `.q(` -> `.Q(` (32x). Top-level port declarations
  (`input wire clk`) unchanged. `timing_violation.sdc` unchanged.

Real evidence after the fix (direct `sta`, then live Gate 4):

```text
$ sta -exit tv_fixed.tcl => RC=0, 0x "port not found"
Startpoint: f_s0_b0 (rising edge-triggered flip-flop clocked by clk)
Endpoint:   f_s1_b0 (rising edge-triggered flip-flop clocked by clk)
  0.27 data arrival time / -0.11 data required time => -0.38 slack (VIOLATED)
wns -0.38
```

```text
$ parser => {'setup_wns': -0.38, 'setup_tns': None, 'hold_wns': None} (no parser change needed)
$ SiliconSignoffVerifier._run_gate4_timing(...) =>
  passed=False, error_category=TIMING_SLACK_VIOLATION,
  details="Setup timing violation: WNS = -0.380 ns (-380.000 ps; target >= 0.000 ps)."
```

- `[VERIFIED]` `TIMING_SLACK_VIOLATION` arises only from genuine negative slack
  plus the pre-existing classifier path. `parse_opensta_timing`,
  `parse_opensta_mcmm`, and `classify_failure` are unmodified.
- File `tests/test_negative_controls.py` now resolves Liberty via
  `resolve_timing_liberty()` (env first, packaged fixture fallback) instead
  of hardcoding the fixture path.

## PHASE 6 — Regression verification (with real-Liberty env)

```bash
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH=src
export MIND3_EDA_READONLY_PATHS="$HOME/.local:$HOME/openroad-env:/home/mind/oss-cad-suite:/home/mind/pdk"
export MIND3_NEGATIVE_CONTROL_LIBERTY="/home/mind/pdk/sky130A/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
export MIND3_SKY130_ROOT="/home/mind/pdk/sky130A/sky130A"
export MIND3_LIBERTY_PATH="$MIND3_NEGATIVE_CONTROL_LIBERTY"
```

Note: `:/home/mind/pdk` is appended to `MIND3_EDA_READONLY_PATHS` because the
sandboxed Gate 4 run can only `read_liberty` what is bound into the Bubblewrap
root (same pre-existing deployment requirement as the EDA binaries; with the
task's literal three-entry value the sandboxed script run reports
`TIMING_REPORT_UNPARSEABLE` while the unsandboxed pytest live test passes —
both honest, neither mocked).

```text
$ python -m pytest -q tests/test_timing_liberty_resolution.py => 5 passed
$ python -m pytest -q test_opensta_smoke_version_and_workload + test_affected_negative_control_reaches_intended_gate_live --maxfail=1
  => 8 passed, 1 skipped (cdc_violation: host Yosys lacks CDC command)
$ python scripts/run_negative_controls.py --require-live
  => 15 PASS, 1 SKIP (cdc_violation CDC_TOOLING_UNAVAILABLE), Verdict SUCCESS,
     timing_violation -> expected=TIMING_SLACK_VIOLATION, observed=TIMING_SLACK_VIOLATION
$ python -m pytest -v tests/test_pdk_gates_canary.py
  => 3 passed (Gate 4 live SKY130, Gate 5 OpenROAD PnR live SKY130, Gate 4 violation detection)
$ python -m pytest -ra => 323 passed, 2 skipped in ~32s (0 failed)
  SKIPPED: macOS Seatbelt (Darwin-only), cdc_violation (no cdc command)
```

- `[VERIFIED]` Skips are environment-honest (CDC genuinely absent, Seatbelt
  Darwin-only), not passes.
- `[VERIFIED]` Without any PDK env vars, both the smoke test and the timing
  live test FAIL closed (threshold error / unparseable) — no failure hidden
  as a skip.

## PHASE 7 — No-weakening checklist

- `[VERIFIED]` Timing/coverage thresholds unchanged:
  `min_branch_coverage=95.0, min_toggle_coverage=90.0, max_wns_ps=0.0,
  min_hold_slack_ps=0.0` (`src/mind3/core/verifier.py:884-887`).
- `[VERIFIED]` Model/provider, benchmark datasets (`benchmarks/*.jsonl`
  mtimes Oct 3), and release thresholds untouched.
- `[VERIFIED]` Gate 1–6 semantics, formal assertions, and the timing
  classifier/parser (`parse_opensta_timing`, `parse_opensta_mcmm`,
  `TIMING_SLACK_VIOLATION` path) unmodified — `src/mind3/core/verifier.py`
  and `src/mind3/core/failure_taxonomy.py` not edited this phase.
- `[VERIFIED]` Packaged Liberty fixture untouched (201 lines); no fake timing
  output, no fake PDK, no mock execution (`simulated=False` throughout live
  runs).
- `[VERIFIED]` CDC still honestly unavailable:
  `yosys -p "help cdc" => No such command or cell type: cdc` on both
  `/usr/bin/yosys` (0.33) and `~/oss-cad-suite/bin/yosys`; `cdc_violation`
  remains SKIP / `CDC_TOOLING_UNAVAILABLE`.
- `[VERIFIED]` Sandbox still fail-closed (`--unshare-all`,
  `--die-with-parent` intact in `src/mind3/sandbox/bwrap.py`).
- `[VERIFIED]` Changed files this phase only:
  `src/mind3/eda/timing_liberty.py` (new),
  `tests/test_linux_toolchain.py`, `tests/test_negative_controls.py`,
  `tests/negative_controls/timing_violation.sv`,
  `tests/test_timing_liberty_resolution.py` (new),
  plus regenerated `artifacts/negative_controls_report.json` (now SUCCESS:
  15 PASS / 1 SKIP) and this audit append.

## Remaining blockers (evidence-backed only)

1. `[VERIFIED]` CDC tooling absent on both Yosys builds — Gate 6 pending.
2. `[VERIFIED]` Full-suite green (323 passed) currently requires the
   environment-supplied real SKY130 library (`MIND3_NEGATIVE_CONTROL_LIBERTY`
   / `MIND3_SKY130_ROOT`) plus sandbox binding of the PDK path; the default
   no-PDK layout fails closed on the two timing tests (honest, not hidden).
3. `[VERIFIED]` OpenROAD binary executes (`openroad -version =>
   f12e2f474102bfb875eeee57fb610d7d7de17770`, rc=0) and the live SKY130 PnR
   canary now passes in-Bubblewrap; broader PnR / tapeout claims remain
   out of scope for this change.
4. `[PENDING-HUMAN]` CDC-capable Yosys, release ≥100-task heldout evidence,
   license choice.

---

# Append 2026-10-05 — CDC root-cause closure + held-out benchmark evidence (no source changes)

## PHASE 1 — CDC root cause

```text
$ yosys -V => Yosys 0.33 (git sha1 2584903a060)
$ yosys -p "help cdc" => "No such command or cell type: cdc"
$ /home/mind/oss-cad-suite/bin/yosys -V => Yosys 0.69+77 (git sha1 9ff27d29c-dirty, Release, Clang /usr/bin/clang++ 21.1.8)
$ /home/mind/oss-cad-suite/bin/yosys -p "help cdc" => "No such command or cell type: cdc"
```

- `[VERIFIED]` Full `yosys -p "help"` pass list contains no `cdc`/crossing
  entry in either build. OSS CAD Suite plugins dir holds only
  `eqy_combine.so, eqy_partition.so, eqy_recode.so, ghdl.so, slang.so` — no
  CDC plugin. Machine-wide search finds no CDC binary, plugin, or alternate
  CDC tool (verible/slang/surelog/questa all absent; only kernel USB `cdc`
  headers and terminfo noise match).
- `[VERIFIED]` Repository expectation is exactly one thing: a real Yosys
  `cdc` pass invoked as
  `yosys -p "read_verilog -sv <src>; hierarchy -check -top <top>; proc; cdc -verbose"`
  (`src/mind3/core/verifier.py:2660-2665`), parsed by `parse_yosys_cdc`,
  fail-closed `CDC_TOOLING_UNAVAILABLE` when absent. No alternate tool, no
  bundled plugin, no repo-provided integration exists.
- `[VERIFIED]` Checked-in `tests/fixtures/eda_outputs*/yosys_cdc_*.log` are
  labeled synthetic parser placeholders, never real captures. Parser was
  never calibrated against genuine output.

## PHASE 2 — Toolchain search result

- `[VERIFIED]` No legitimate CDC-capable tool is present on this machine.
  Building one locally is not practical: upstream Yosys ships no `cdc` pass
  source to compile, and no CDC plugin source is vendored. CDC capability is
  an environment dependency requiring human procurement
  (`[PENDING-HUMAN]`), not a repository defect. No fake `cdc` created.

## PHASE 3 — Live Gate 6 evidence

```text
$ SiliconSignoffVerifier(top_module="cdc_violation", allow_mock_fallback=False, require_cdc=True)
    ._run_gate6_cdc_analysis(...) on tests/negative_controls/cdc_violation.sv
  CMD: yosys -p "read_verilog -sv cdc_violation.sv; hierarchy -check -top cdc_violation; proc; cdc -verbose"
  passed=False exit_code=1 error_category=CDC_TOOLING_UNAVAILABLE simulated=False cdc_violations=[]
```

- `[VERIFIED]` Real Yosys elaboration (frontend/hierarchy/proc traces in
  stdout) executes, then fails closed at the missing `cdc` command. Nothing
  substituted (no syntax/simulation/formal evidence presented as CDC).

## PHASES 4–5 — No integration fix; Gate 6 stays honest

- `[VERIFIED]` No repository defect found, so no source modified. Forbidden
  outcomes (relabeling `CDC_ANALYSIS_FAILED`/`CDC_TOOLING_UNAVAILABLE` as
  `CDC_VIOLATION`, skip conversion, Gate 6 bypass) all rejected.
  `cdc_violation` remains `expected=CDC_VIOLATION / observed=CDC_TOOLING_UNAVAILABLE`,
  honestly SKIP. `[PENDING-HUMAN] CDC-capable EDA toolchain`.

## PHASES 6–9 — Held-out benchmark (frozen pipeline, real model)

Dataset integrity (before/after identical):

```text
bae56a8d...dd2c24  benchmarks/heldout/tasks.jsonl (120 tasks)
539e79af...59c8c8  benchmarks/development-20/tasks.jsonl (20 tasks)
9d137519...f58e7c4  benchmarks/tasks.jsonl (50 tasks)
```

- `[VERIFIED]` Command (unchanged model/provider, strict default, real Liberty):
  `python -m mind3.benchmarks.runner --tasks benchmarks/heldout/tasks.jsonl
  --model qwen2.5-coder:7b --provider ollama --max-repairs 3
  --liberty /home/mind/pdk/sky130A/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
  --report-dir artifacts/stage8_heldout_120 --transcripts artifacts/stage8_heldout_120/transcripts`
- `[VERIFIED]` 120/120 real non-mock transcripts (`live_provenance=true`,
  `fixture_count=0`, all `model=qwen2.5-coder:7b provider=ollama`).
  First attempt halted at 50/120 by host/session restart (environment event);
  remaining 70 resumed with identical parameters (4 parallel shards, disjoint
  workspaces, one transcript dir); evaluation via `--evaluate-existing` over
  all 120. One operational note: an early smoke without `--transcripts`
  wrote 2 live files into `benchmarks/transcripts/`; both removed, 50/50
  checked-in fixtures intact.
- `[VERIFIED]` Outcome: `initial 0 / functional 0 / full-verified 0 /
  repair 0`; taxonomy `RESPONSE_PARSE_FAILURE=119, SPECIFICATION_ERROR=1`
  (`arbiter_02` contract-consistency failure, same dataset quirk as prior
  Stage 6 evidence). Mean transcript duration 77.8s.
- `[VERIFIED]` Parse-failure root cause (executable probes, both modes):
  driver forces `"format": "json"` on Ollama while the generation prompt
  demands raw module code; pinned model emits a lossy AST dict
  (`inputs/outputs/sequential/always/if/assign`, e.g. `"rhs": 80` where
  `8'hFF`-class constants belong) rejected by strict AND lenient parsers.
  Without the JSON constraint the same model returns strict-parseable fenced
  Verilog. No harness/parser change made: tuning model interaction for score
  is outside verification closure, and AST→RTL reconstruction of lossy novel
  shapes would risk verifying misinterpreted RTL. The 0% is honest
  model+pipeline evidence, consistent with prior Stage 6 findings.
- `[AGENT-SUPPLIED]` The summary's mechanical `evidence_tier:
  "release-eligible"` reflects only the 120≥100 count threshold; with 0/120
  passing no performance claim of any kind is supported.

## PHASES 10–11 — Regression and no-weakening

```text
$ python -m pytest -ra => 323 passed, 2 skipped (macOS Seatbelt; cdc_violation, no cdc)
$ python scripts/run_negative_controls.py --require-live => 15 PASS, 1 SKIP (cdc), SUCCESS
$ probe_bubblewrap_namespace_capability() => (True, 'bwrap created namespaces and executed the probe payload')
```

- `[VERIFIED]` Zero source files modified this session (no new files under
  `src/ tests/ scripts/ docs` since 2026-10-04 22:00 except this audit
  append); thresholds (95.0/90.0/0.0/0.0), Gate 1–6 semantics, formal
  properties, sandbox flags, model/provider, datasets all unchanged; no
  mocks; no tests deleted; no `.git` created; nothing committed or pushed.

---

# Append 2026-10-05 — Driver/model response-format integration fix (no parser change)

## Root cause (executed evidence)

- `PhaseDriver._query_ollama` unconditionally sent `"format": "json"`
  (`src/mind3/core/driver.py`, single site), while `RTLGenerator.build_prompt`
  instructs "Respond ONLY with the complete synthesizable module code" with no
  JSON schema mentioned.
- Direct probe with the driver's exact messages for held-out `counter_01`:
  with `"format": "json"`, `qwen2.5-coder:7b` emits a structural AST dict
  (`module/inputs/outputs/sequential/always/if/assign`, lossy e.g.
  `"rhs": 80` for `8'hFF`-class constants) rejected by strict AND lenient
  parsers; without the constraint the same model returns a strict-parseable
  fenced SystemVerilog module (proven prior session).
- `[VERIFIED]` The 0/120 parse block was dominated by this artificial
  request/representation mismatch, not proven model incapability.

## Fix (localized, parser untouched)

`src/mind3/core/driver.py` only:
- `_query_ollama(..., *, response_format="json")`: includes `"format": "json"`
  solely when `response_format == "json"`.
- `_query_model(..., *, response_format="json")` passthrough; the default
  `"json"` path preserves the exact legacy call shape
  (`self._query_ollama(messages)`) so unrelated callers are unaffected.
- Only the two RTL-text call sites use `response_format="text"`: initial
  generation and the repair query (same strict parser, same contract).
  Contract synthesis, the agent action loop, and baselines keep JSON.
- No AST-to-Verilog reconstruction, no heuristic recovery, no new accepted
  shapes, no parser-bypass. Strict parser codepaths byte-identical.

`tests/test_mind3.py`: 6 mock `_query_ollama` signatures accept the new
optional kwarg (assertions identical — interface alignment, not weakening).
New `tests/test_rtl_response_format.py` (4 tests): text path omits the JSON
constraint, default keeps it, fenced SV parses strict, AST dict stays
rejected strict.

## Live diagnostic (unchanged ollama/qwen2.5-coder:7b, strict, real Liberty)

- 2-task check: `counter_01/02` went from `RESPONSE_PARSE_FAILURE` to parsed
  RTL reaching Gate 1 (`TYPE_WIDTH_ERROR`: model emits 2-bit ports — genuine
  model errors), 3 genuine repairs each (turns reached Gate 3 coverage build,
  latch trap, width/syntax errors).
- 6-task sample (`artifacts/stage9_diag_sample/`, diagnostic only, not
  benchmark evidence): 5/6 parsed to real Gate 1 `TYPE_WIDTH_ERROR` with 3
  repairs each (turns show `COVERAGE_BUILD_FAILURE`, `LATCH_INFERRED`,
  `TYPE_WIDTH_ERROR`, `SYNTAX_ERROR`, `REPAIR_PATCH_TOO_LARGE` enforcement);
  1/6 residual `RESPONSE_PARSE_FAILURE`. 0/6 passed — model quality remains
  poor, but the pipeline now genuinely executes instead of failing at parse.

## Regression

```text
pytest: 327 passed, 2 skipped (macOS Seatbelt; cdc_violation, no cdc)
negative controls: 15 PASS, 1 SKIP (cdc), SUCCESS (real Liberty + sandbox binds)
sandbox probe: (True, namespaces executed)
CDC: "No such command" on both Yosys builds — CDC_TOOLING_UNAVAILABLE preserved
```

## Scope (Phase 10)

- `[VERIFIED]` Provider/model/dataset (`bae56a8d…dd2c24`)/thresholds
  (95.0/90.0/0.0/0.0)/Gate 1–6/formal/timing/coverage semantics unchanged;
  sandbox fail-closed; no mocks added; no tests deleted; CDC untouched; PDK
  untouched; changed files only `src/mind3/core/driver.py`,
  `tests/test_mind3.py` (mock signatures), `tests/test_rtl_response_format.py`.

## 120-task benchmark

`NOT RERUN YET` — rerun is a separate controlled measurement after this
integration fix; frozen 120-transcript evidence left intact.

---

# Append 2026-10-05 — Exact-header prompt fix + stale-netlist repair fix (parser/validator untouched)

## Root cause (controlled evidence, not assumption)

- Forensics over `artifacts/stage9_diag_sample/` (6 tasks): every 1-bit port
  generated as `[1:0]`; widths >1 correct (`[7:0]`, `[3:0]`). The model maps
  pinout prose `"[1 bits]"` to range msb=1 — a prompt-representation failure.
- Controlled probe (same ollama/qwen2.5-coder:7b, `counter_04`+`counter_06`):
  A/current → 1-bit widths wrong; B/immutable-prose → scalars fixed BUT wide
  ports broken (`q` dropped, `div_val` → `[8:0]`); C/exact SV header → all
  widths correct on both tasks. C adopted; B rejected as harmful.
- Repair-loop defect found in stage9 evidence: after any Gate-1-passing run,
  `<top>_netlist.v` (Gate 1 synthesis output) remained while repair rewrote
  `<top>.sv`; re-verify compiled both → `'counter_01' has already been
  declared`, failing every subsequent repair spuriously (also risked stale
  Gate 4 timing). Genuine harness bug, exposed once parsing started working.

## Changes (minimal, verifier stays authoritative)

`src/mind3/core/contracts.py`:
- New `module_signature_block(contract)` (single source): scalars for 1-bit,
  `[N-1:0]` otherwise. Used by `RTLGenerator.build_prompt` ("The module
  header must be exactly:") and `VerificationRepairer.build_prompt` ("must
  still be exactly:"). No auto-correction, no RTL rewriting, no validator
  change, repair budget 3 unchanged, interface immutability rules unchanged.
`src/mind3/core/verifier.py`:
- `verify()` source discovery and Gate 1 `synthesis_sources` both exclude
  `*_netlist.v` (derived artifacts; Gate 1 regenerates them each run, Gate 4
  selects them explicitly). Nothing else in Gate semantics changed.
`tests/test_mind3.py`: 6 mock signatures accept the prior session's
`response_format` kwarg (assertions identical).
New: `tests/test_generation_prompt_contract.py` (7: header present,
scalar/vector rendering, immutability wording, validator rejects
`input [1:0]` for 1-bit as `TYPE_WIDTH_ERROR`, accepts exact header),
`tests/test_gate1_netlist_exclusion.py` (compile argv excludes netlists).

## Diagnostic comparison (10 held-out tasks, strict, repairs 3, real Liberty)

BEFORE (stage10_generation_diag, signature fix only):
parse 10/10, Gate 1 10/10, initial `COVERAGE_BUILD_FAILURE`×9 +
`SYNTHESIS_ELABORATION_ERROR`×1; all post-Gate-1 repairs died on the stale
netlist duplicate-declaration `SYNTAX_ERROR`. 0 verified.
AFTER (stage10b_postfix_diag, + netlist exclusion):
parse 10/10, Gate 1 width errors 0/10; initial `COVERAGE_BUILD_FAILURE`×7,
`SYNTAX_ERROR`×2 (genuine model syntax), `SYNTHESIS_ELABORATION_ERROR`×1;
repairs exercise real gates (coverage builds, `LATCH_INFERRED` trap,
elaboration) with zero spurious duplicate declarations. 0 verified —
model quality (coverage deficits, syntax), honestly recorded.

## Regression / integrity

```text
pytest: 335 passed, 2 skipped (macOS Seatbelt; cdc_violation, no cdc)
negative controls: 15 PASS, 1 SKIP (cdc), SUCCESS
sandbox probe: (True, namespaces executed)
CDC: "No such command" both builds — CDC_TOOLING_UNAVAILABLE preserved
datasets: bae56a8d… / 539e79af… / 9d137519… identical; fixtures 50/50; no .git
```

## 120-task benchmark

`NOT RERUN` — frozen 120-transcript evidence (119 parse-fail + 1 spec-error
under the old JSON-forced integration) left untouched per instructions.

---

# Append 2026-10-05 (pm) — Width wall to functional gates: prompt example + newline hygiene

## Forensics (stage10b, 10 tasks; headers correct in all 10)

| task | initial | first real defect | repairs | final |
|---|---|---|---|---|
| counter_01 | COVERAGE_BUILD_FAILURE | saturating logic plausible; build died on EOFNEWLINE (harness) | 3× EOFNEWLINE | ROLLED_BACK |
| counter_02 | COVERAGE_BUILD_FAILURE | wrong Gray algorithm (shift instead of Gray step) | 3× EOFNEWLINE | ROLLED_BACK |
| counter_03 | COVERAGE_BUILD_FAILURE | BCD tens stale-read + no wrap at 99 | 3× EOFNEWLINE | ROLLED_BACK |
| counter_04 | COVERAGE_BUILD_FAILURE | rotate instead of twisted-ring (`~msb` missing) | 2× EOFNEWLINE → LATCH_INFERRED | ROLLED_BACK |
| counter_05 | SYNTAX_ERROR | `output fault` wire driven in `always` (multi-driver/l-value) | 3× SYNTAX_ERROR | SYNTAX_ERROR |
| counter_06 | COVERAGE_BUILD_FAILURE | divider edge cases (`div_val-1` underflow at 0) | 3× EOFNEWLINE | ROLLED_BACK |
| counter_07 | COVERAGE_BUILD_FAILURE | rolls at 255, spec says MAX-1 (spec thin; SVA authoritative) | 3× EOFNEWLINE | ROLLED_BACK |
| counter_08 | SYNTAX_ERROR | malformed conditional (`8'd-128`-class literal misuse) | 3× SYNTAX_ERROR | SYNTAX_ERROR |
| counter_09 | COVERAGE_BUILD_FAILURE | `reg` declared inside `always`; 8-bit feedback misused | 3× EOFNEWLINE | ROLLED_BACK |
| counter_10 | SYNTHESIS_ELABORATION_ERROR | `$changed(strobe)` unsynthesizable | 3× ELABORATION_ERROR | ROLLED_BACK |

- `[VERIFIED]` Dominant real mode: model reasoning/coding limitation (wrong
  algorithms, wire l-values, malformed expressions, unsynthesizable
  constructs). Plus one harness triviality: 7+ tasks' coverage builds died
  solely on `%Warning-EOFNEWLINE` (no trailing newline), burning all repairs.
- `[VERIFIED]` A/B/C probe (counter_02/05/10, same model/pipeline): A fails
  Gate 1 on all 3; B (checklist) and C (binary-counter style example, no
  task logic) both reach Gate 1 on all 3. C adopted (single-element,
  no invented behavior); B rejected as redundant (duplicates system
  invariants; newline item obsolete).

## Changes

- `src/mind3/core/contracts.py`: canonical style example appended to the
  generation prompt (discipline, not logic); repair prompt unchanged in
  structure (already had exact header from prior fix).
- `src/mind3/core/driver.py::_execute_action`: POSIX-terminate written files
  (append one `\n` only when missing). Zero Verilog semantic effect; avoids
  weakening Gate 3 `-Wall` strictness. Documented inline.
- `tests/test_mind3.py`: one assertion updated to the documented contract
  (`body verbatim + "\n"`); 6 mock signatures from prior fix kept.
- New tests: header/example presence, newline preserve/terminate behavior
  (in `test_generation_prompt_contract.py`).

## Stage 12 (same 10 tasks, `artifacts/stage12_postfix_diag/`)

parse 10/10; Gate-1 width errors 0; initial `COVERAGE_DEFICIT`×3,
`FORMAL_INVARIANT_BREACH`×4, `SYNTAX_ERROR`×2,
`SYNTHESIS_ELABORATION_ERROR`×1. Repairs traverse real gates
(e.g. `SYNTAX_ERROR→COVERAGE_DEFICIT`, `ELABORATION_ERROR→COVERAGE_DEFICIT`,
`COVERAGE_DEFICIT→LATCH_INFERRED`). 0 verified — tasks now die on genuine
functional/formal/coverage grounds: the pipeline demonstrably executes
Gates 1→3→2 on model RTL; the model cannot yet satisfy them.

## Regression / integrity

```text
pytest: 338 passed, 2 skipped (macOS Seatbelt; cdc_violation)
negative controls: 15 PASS, 1 SKIP (cdc), SUCCESS
sandbox probe: (True, namespaces executed); CDC: "No such command" both builds
datasets: bae56a8d… / 539e79af… / 9d137519… identical; fixtures 50/50; no .git
```

## 120-task benchmark

`NOT RERUN` — frozen Stage 8 evidence untouched.

---

# Append 2026-10-05 (evening) — SBY-copy repair contamination fix + Stage 14 validation

## Forensics + root cause (executed, not assumed)

- `[VERIFIED]` Stage 12 repairs on counter_06/08/09 failed with
  `'counter_0X' has already been declared` pointing at
  `counter_0X/src/counter_0X.sv`. Only SymbiYosys creates `<top>/` workdirs
  (trace evidence `counter_08/engine_0/trace.vcd`); SBY copies inputs to
  `<top>/src/`. The signoff `verify()` used recursive `rglob` while every
  other lookup in the file (SDC/TCL/netlists) is top-level `glob` — the
  recursive scan recompiled SBY's copies on every re-verify.
- `[VERIFIED]` Fix: new `discover_rtl_sources()` (top-level only, netlist +
  checker exclusions preserved) used by `verify()`; direct-call paths that
  pass explicit source lists are untouched. No Gate semantics changed.
- `[VERIFIED]` A/B/C result stands (B and C reach Gate 1 3/3; C adopted as
  the single-element intervention). The experiment's own coverage-build
  failures were its artifact (direct `write_text`, bypassing the production
  newline hygiene) — prompt effects on Gate 1 are unconfounded.

## Stage 14 (`artifacts/stage14_validation/`, same 10 tasks)

parse 10/10; init `COVERAGE_DEFICIT`×4, `LATCH_INFERRED`×3,
`FORMAL_INVARIANT_BREACH`×1, `COVERAGE_BUILD_FAILURE`×1,
`SYNTHESIS_ELABORATION_ERROR`×1. Zero spurious duplicate declarations.
Repair transitions (all genuine): `FORMAL_INVARIANT_BREACH→COVERAGE_DEFICIT`×3
(counter_05: repair fixed the formal breach), `ELABORATION_ERROR→COVERAGE_DEFICIT`,
`LATCH_INFERRED→COVERAGE_DEFICIT`. 0 verified — candidates fail on real
functional/formal/coverage grounds (wrong Gray/Johnson/BCD/signed/divider
logic, latch inference, coverage shortfalls).

## Central question (measured answer)

- `[VERIFIED]` `qwen2.5-coder:7b` now reliably emits interface-correct,
  compiling RTL (parse 10/10, Gate-1 width errors 0/10 across two samples),
  and the pipeline executes Gates 1→3→2 plus evidence-driven repairs on it.
  The model cannot yet produce functionally/formally correct RTL nor repair
  to green within budget 3. That is a measured model-quality ceiling, not a
  harness wall — every remaining failure is a genuine verifier verdict.

## Regression / integrity

```text
pytest: 340 passed, 2 skipped (macOS Seatbelt; cdc_violation)
negative controls: 15 PASS, 0 FAIL, 1 SKIP (cdc), SUCCESS
sandbox probe: (True, namespaces executed)
CDC: "No such command or cell type: cdc" both builds — honestly skipped
datasets: bae56a8d… identical; fixtures 50/50; frozen Stage 8 untouched; no .git
```

## 120-task benchmark

`NOT RERUN` — frozen Stage 8 evidence untouched.

---

# Append 2026-10-06 — Stage 15: latch-trap false positive + behavioral ceiling

## Forensics artifact

- `[VERIFIED]` `artifacts/stage15_semantic_forensics.json`: per-task primary
  root causes — wrong algorithm ×3, incorrect arithmetic ×2,
  coverage-unreachable ×1, wrong state sequence ×1, spec ambiguity ×1,
  incorrect signedness ×1, invalid SV construct ×1.

## Latch-trap false positive (genuine verifier defect, fixed with proof)

- `[VERIFIED]` Stage 14 `LATCH_INFERRED` on counter_02/06/09 came from the
  log-regex fallback matching Yosys `ff.cc` optimizer internals
  ("Setting constant 0-bit ... ($dlatch)" for transient cells), while the
  final structured AST contained zero latch cells. The regex overruled the
  clean authoritative check.
- `[VERIFIED]` Fix (`verifier.py` Gate 1 only): latch verdict now comes from
  the structured AST exclusively; log-regex runs solely when no AST exists.
  Additionally the trap previously missed REAL latches two ways — lexical
  check ignored the `always @(*)` parenthesized form, and the AST comparison
  was case-sensitive so `$_DLATCH_P_` never matched. Both corrected
  (executed both directions: counter_02 RTL now passes; a true combinational
  latch still fails `LATCH_INFERRED`).
- `[VERIFIED]` Regression: `tests/test_latch_trap_accuracy.py` (chatter is
  not a latch; real latch fails closed).
- `[UNVERIFIED]` `$dffsr`/`$sr` remain in the latch cell list; no current
  case distinguishes them. Left unchanged, flagged for human review.

## Behavioral prompt experiment (counter_02/04/05 × A/B/C, real pipeline)

- `[VERIFIED]` A/B/C all 0/9 verified. One B-instance reached Gate 1 where A
  latched; C did not repeat it. No repeatable improvement; model
  nondeterminism dominates. Confounded note: the script wrote files directly,
  bypassing production newline hygiene, so 7/9 died on EOFNEWLINE —
  prompt effects on Gate 1 (the measured claim) are unconfounded.
- `[VERIFIED]` Repair A/B (added explicit expected-behavior sentence; current
  prompt already carries spec/header/RTL/diagnostics): all 4 parsed, all 4
  Gate-1 clean — no discrimination. Current repair context is adequate.

## Production decision

`No production change justified by controlled evidence` for prompts. Sole
production change this stage: the latch-trap accuracy fix above, justified
by bidirectional executed proof.

## Regression / integrity

```text
pytest: 342 passed, 2 skipped (macOS Seatbelt; cdc_violation)
negative controls: 15 PASS, 0 FAIL, 1 SKIP (cdc), SUCCESS
sandbox probe: (True, namespaces executed)
CDC: "No such command or cell type: cdc" both builds — honestly skipped
datasets: bae56a8d… / 539e79af… / 9d137519… identical; fixtures 50/50; no .git
```

## 120-task benchmark

`NOT RERUN` — frozen Stage 8 evidence untouched.

---

# Append 2026-10-07 — Stage 16: repair-strategy ceiling (no production change)

## Baseline (`artifacts/stage16_baseline.json`)

- counter_04 (state/sequence): plain rotate, missing `~fb`, reset off-cycle.
- counter_03 (arithmetic): decade logic right; wrap path never stimulated.
- counter_05 (temporal/control): no window logic at all; formal breach genuine.

## Repair A/B/C (same RTL start, evidence, model, sandbox, budget; 1 turn each)

| Task | A (production) | B (+structured) | C (+trace/structured) |
|---|---|---|---|
| counter_04 | same COVERAGE_DEFICIT, RTL byte-identical rewrite | same, identical | same, identical |
| counter_03 | same COVERAGE_DEFICIT, RTL unchanged | same, unchanged | same, unchanged |
| counter_05 | FORMAL_BREACH → COVERAGE_DEFICIT (fault held constant — dodges property, no window logic) | same as A | stays FORMAL_BREACH |

- `[VERIFIED]` 0/9 verified across variants. Repairs repeat the same mistake
  (04/03 byte-identical), game the property instead of implementing behavior
  (05: `fault <= fault`), or regress (C stays breached where A/B move).
  No variant demonstrates improvement; C is weakly worse.
- `[VERIFIED]` Repair successes: 1 category of forward motion
  (breach→coverage on counter_05 A/B) that is property-dodging, not correct
  behavior. Genuine improvements: 0. Regressions: 0 (C non-motion counts as
  no-progress, not regression of the candidate). Fully verified: 0/9.

## Production decision

`No production repair-prompt change justified by controlled evidence.`

## Regression / integrity

```text
pytest: 342 passed, 2 skipped (macOS Seatbelt; cdc_violation)
latch accuracy: 2 passed (chatter clean, true latch fails)
negative controls: 15 PASS, 0 FAIL, 1 SKIP (cdc), SUCCESS
sandbox probe: (True, namespaces executed)
CDC: "No such command or cell type: cdc" both builds — honestly skipped
datasets: bae56a8db36a / 539e79afaf6f / 9d137519b913 identical; fixtures 50/50; no .git
```

## 120-task benchmark

`NOT RERUN` — frozen Stage 8 evidence untouched.
