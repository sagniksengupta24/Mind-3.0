# Mind 3.0 — Linux Environment Evidence

Date: 2026-10-03 (executed 2026-10-04 UTC on Linux host)
Host user: `mind`
Workdir: `/home/mind/Desktop/Mind-3.0-main`

Classification legend (only these labels are used):
`[VERIFIED]` = backed by executed command output below.
`[UNVERIFIED]` = claimed in docs but not demonstrated here.
`[PENDING-HUMAN]` = requires human/CI asset outside this host.
`[AGENT-SUPPLIED]` = agent-observed note, not tool output.

No tracked source files were edited. Only this new untracked report is created.

## 1. Host

```text
$ pwd
/home/mind/Desktop/Mind-3.0-main
$ git status --short
fatal: not a git repository (or any of the parent directories): .git
$ git branch --show-current
fatal: not a git repository (or any of the parent directories): .git
$ git log -3 --oneline --decorate
fatal: not a git repository (or any of the parent directories): .git
$ uname -a
Linux mind 7.0.0-34-generic #34~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC Fri Sep  4 15:38:29 UTC 2 x86_64 x86_64 x86_64 GNU/Linux
$ uname -m
x86_64
$ cat /etc/os-release
PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
$ python3 --version
Python 3.12.3
```

- `[VERIFIED]` OS is Ubuntu 24.04.4 LTS, kernel 7.0.0-34-generic, arch x86_64.
- `[VERIFIED]` `~/Desktop/Mind-3.0-main` is NOT a Git repository (no `.git`). `git status/branch/log` unavailable. Per task rules no repo was initialized and nothing was cloned into the repo. Git-based branch/HEAD/cleanliness cannot be reported.
- `[AGENT-SUPPLIED]` Directory contains Mind-3.0 tree (artifacts, audit, benchmarks, src, tests, etc.) plus pre-existing `.venv`.

## 2. Python

```text
$ if [ -d .venv ]; then source .venv/bin/activate; else python3 -m venv .venv; source .venv/bin/activate; fi
$ which python
/home/mind/Desktop/Mind-3.0-main/.venv/bin/python
$ python --version
Python 3.12.3
$ python -m pip --version
pip 26.2.1 from /home/mind/Desktop/Mind-3.0-main/.venv/lib/python3.12/site-packages/pip (python 3.12)
$ pip show (after setup)
click 8.5.0, pydantic 2.13.5, pytest 8.4.2
$ cat pyproject.toml requires-python
>=3.11 ; dependencies: httpx>=0.27,<1, pydantic>=2.7,<3, PyYAML>=6,<7
```

- `[VERIFIED]` Existing `.venv` was reused (no `--break-system-packages` used).
- `[VERIFIED]` venv Python is 3.12.3 (system python3 is also 3.12.3).
- `[VERIFIED]` `pip install -e ".[dev]"` was executed inside the venv to satisfy test imports (pytest/pydantic/httpx/PyYAML). `pip install click` was additionally required to repair SBY execution (see §3). No system packages were modified.

## 3. EDA Toolchain

All commands run with `export PATH="$HOME/.local/bin:$PATH"`.

```text
=== YOSYS ===
$ which yosys
/usr/bin/yosys
$ yosys -V
Yosys 0.33 (git sha1 2584903a060)

=== SBY ===
$ which sby
/home/mind/.local/bin/sby
$ sby --version
SBY v0.69
NOTE: with venv active, `sby --version` initially failed:
  File "/home/mind/.local/bin/../share/yosys/python3/sby_core.py", line 19, in <module>
    import os, re, sys, signal, platform, click
  ModuleNotFoundError: No module named 'click'
Cause: venv python lacked `click` while system /usr/bin/python3 has click 8.1.6.
Fix (minimum dependency, inside venv only): `pip install click` -> click 8.5.0.
After fix: `sby --version` => `SBY v0.69` with exit 0 under venv.

=== Z3 ===
$ which z3
/usr/bin/z3
$ z3 --version
Z3 version 4.8.12 - 64 bit

=== VERILATOR ===
$ which verilator
/usr/bin/verilator
$ verilator --version
Verilator 5.020 2024-01-01 rev (Debian 5.020-1)

=== OPENROAD ===
$ which openroad
/home/mind/.local/bin/openroad -> /home/mind/openroad-env/bin/openroad
$ openroad -version
f12e2f474102bfb875eeee57fb610d7d7de17770
exit 0

=== OPENSTA ===
$ which sta
/home/mind/.local/bin/sta -> /home/mind/openroad-env/bin/sta
$ sta -version
2.3.1
exit 0

=== BWRAP ===
$ which bwrap
/usr/bin/bwrap
$ bwrap --version
bubblewrap 0.9.0

=== IVERILOG ===
$ which iverilog
/home/mind/.local/bin/iverilog
$ iverilog -V 2>&1 | head -n 8
Icarus Verilog version 12.0 (stable) ()
Copyright (c) 2000-2021 Stephen Williams (steve@icarus.com)
```

- `[VERIFIED]` All eight binaries respond to path/version queries with the exact versions above.
- `[VERIFIED]` SBY install was pre-existing (`/home/mind/.local/bin/sby`, SBY v0.69); no `pip install sby` was attempted and no SBY source clone was needed. `which sby` succeeded before any install step, so Step 2 `git clone` was correctly skipped.
- `[VERIFIED]` SBY execution was broken in the venv until `click` was installed; version query alone did not prove runnability. After `pip install click`, `sby --version` exits 0 under the venv.
- `[UNVERIFIED]` Version output alone does not prove OpenROAD/OpenSTA PnR/timing verification (see §7). No PnR was executed.

## 4. Yosys CDC

```text
$ yosys -p "help cdc"
-- Running command `help cdc' --
No such command or cell type: cdc
End of script. Logfile hash: f26c6b2d36, CPU: user 0.00s system 0.00s, MEM: 7.29 MB peak
cdc_help_exit=0 (yosys exits 0 even when the subcommand is unknown; the
discriminator is the stdout string, not the exit code)

$ find /home/mind -type f -name yosys 2>/dev/null | head -30
/home/mind/oss-cad-suite/libexec/yosys
/home/mind/oss-cad-suite/bin/yosys
$ find /opt -type f -name yosys 2>/dev/null | head -30
(empty)
$ /home/mind/oss-cad-suite/bin/yosys -V
Yosys 0.69+77 (git sha1 9ff27d29c-dirty, Release, Clang /usr/bin/clang++ 21.1.8)
$ /home/mind/oss-cad-suite/bin/yosys -p "help cdc"
-- Running command `help cdc' --
No such command or cell type: cdc
End of script. Logfile hash: f26c6b2d36, time: 0.00s, user: 0.00s, system: 0.00s, MEM: 11.32 MB peak
$ /home/mind/oss-cad-suite/libexec/yosys -V
/home/mind/oss-cad-suite/libexec/yosys: /lib/x86_64-linux-gnu/libm.so.6: version `GLIBC_2.43' not found (required by ...)
(exit 1; direct libexec invocation not runnable on this Ubuntu 24.04 glibc)
$ cat /home/mind/oss-cad-suite/VERSION
20260921
```

- `[VERIFIED]` CDC command unavailable on this Linux host. Both the system Yosys 0.33 and the OSS CAD Suite wrapper Yosys 0.69+77 report `No such command or cell type: cdc`.
- `[VERIFIED]` No Yosys was replaced or installed to manufacture `cdc`. `/usr/bin/yosys` untouched.
- `[VERIFIED]` OSS CAD Suite presence does NOT imply CDC support here; the actual OSS CAD Suite Linux installation on this host demonstrates absence.

## 5. Bubblewrap

```text
$ ls -l /bin/true
-rwxr-xr-x 1 root root 26936 Aug 25 20:39 /bin/true
$ ls -ld /bin /lib /lib64
/bin -> usr/bin ; /lib -> usr/lib ; /lib64 -> usr/lib64  (usrmerge system)

Prescribed test 1 (no bind mounts):
$ bwrap --unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup --die-with-parent /bin/true
bwrap: execvp /bin/true: No such file or directory
bwrap_namespace_exit=1

Prescribed test 2 (full binds):
$ bwrap --unshare-all --die-with-parent --new-session --proc /proc --dev /dev \
    --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
    /bin/sh -c 'echo BWRAP_EXEC_OK'
BWRAP_EXEC_OK
bwrap_exec_exit=0

Additional isolation of cause:
$ bwrap --unshare-user ... --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /lib64 /lib64 --proc /proc --dev /dev /bin/true
retry_exit=0
$ /usr/bin/bwrap --unshare-all --die-with-parent --new-session --proc /proc --dev /dev --tmpfs /tmp \
    --ro-bind /usr /usr --ro-bind /bin /bin -- /bin/true
bwrap: execvp /bin/true: No such file or directory
exit=1   (exact repo probe command; see src/mind3/sandbox/bwrap.py:211-231)
$ same + --ro-bind /lib /lib --ro-bind /lib64 /lib64 -- /bin/true
exit=0
$ python3 -c "from mind3.sandbox.bwrap import probe_bubblewrap_namespace_capability as p; print(p())"
(False, 'bwrap namespace creation unavailable (exit 1): bwrap: execvp /bin/true: No such file or directory')
```

- `[VERIFIED]` Test 1 fails with exit 1, but the reason is a missing bind mount (`execvp /bin/true: No such file`), NOT a kernel namespace denial (`No permissions to create a new namespace` was never observed).
- `[VERIFIED]` Test 2 succeeds (`BWRAP_EXEC_OK`, exit 0): the kernel permits namespace creation when the sandbox root is constructed with complete usrmerge binds (`/usr+/bin+/lib+/lib64`).
- `[VERIFIED]` The repository probe `probe_bubblewrap_namespace_capability()` reports `(False, exit 1: execvp /bin/true...)` on this host because it binds only `/usr` and `/bin` and omits `/lib`/`/lib64`, which breaks payload exec on usrmerge Ubuntu 24.04. This is why `tests/test_mind3.py:3419` skips and why `run_negative_controls.py` prints "without Bubblewrap namespaces ... not sandbox-verified runs" even though manual full-bind namespaces demonstrably work.
- `[VERIFIED]` No namespace isolation was disabled to manufacture a pass. No kernel `No permissions` failure was observed.

## 6. Network Isolation

Only tested because §5 proved namespace creation works with correct binds.

```text
Host baseline:
$ python3 - <<'PY'
import socket
s=socket.socket(); s.settimeout(5); s.connect(("1.1.1.1",80)); print("HOST_EXTERNAL_CONNECT=SUCCESS")
PY
HOST_EXTERNAL_CONNECT=SUCCESS
host_baseline_exit=0

Sandbox (network-namespace isolated, full binds):
$ bwrap --unshare-all --die-with-parent --new-session --proc /proc --dev /dev \
    --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
    --ro-bind /tmp /tmp /usr/bin/python3 /tmp/nettest.py
SANDBOX_EXTERNAL_CONNECT=FAIL:[Errno 101] Network is unreachable
sandbox_net_exit=0
```

- `[VERIFIED]` Host can reach 1.1.1.1:80.
- `[VERIFIED]` Same connection inside `bwrap --unshare-all` fails with `Network is unreachable`. Egress blocking by network-namespace isolation is demonstrated for the manually constructed sandbox invocation.
- `[UNVERIFIED]` This does NOT prove the repository's `BubblewrapSandbox.run()` path is sandbox-verified end-to-end here, because the repo probe forces the unsandboxed fallback (see §5). Negative-control runs confirm `sandboxed=false` (see §10).

## 7. OpenROAD / OpenSTA Functionality

```text
$ openroad -version
f12e2f474102bfb875eeee57fb610d7d7de17770
openroad_exit=0
$ sta -version
2.3.1
sta_exit=0

$ find tests -maxdepth 2 -type f | sort | grep -Ei 'eda|pdk|gate|timing|openroad|sta'
tests/negative_controls/timing_violation.sdc
tests/negative_controls/timing_violation.sv
tests/test_commercial_eda.py
tests/test_gate2_mandatory.py
tests/test_gate2_temporal_live.py
tests/test_p3_gate1.py
tests/test_pdk_gates_canary.py

$ find src/mind3/pdata/sky130 -maxdepth 2 -type f | sort | head -50
src/mind3/pdata/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib
```

- `[VERIFIED]` Both binaries execute for `-version` with exit 0. That proves only that the binaries run.
- `[VERIFIED]` The repo's real OpenSTA workload `test_opensta_smoke_version_and_workload` FAILS on the bundled liberty (see §8-9): `Library ... is missing one or more thresholds` + missing `fall_transition` warnings, `sta -exit smoke.tcl` returns 1. No timing signoff is demonstrated.
- `[VERIFIED]` No OpenROAD PnR workload was executed; `test_openroad_smoke_version` only asserts non-empty `-version` output. OpenROAD verification remains not demonstrated beyond binary executability.
- `[AGENT-SUPPLIED]` No existing deterministic real-tool PnR test runnable on the bundled files alone was found; no synthetic timing/PnR result was fabricated.

## 8. PDK

```text
$ find src/mind3/pdata/sky130 -type f -maxdepth 3 -print | sort | head -100
src/mind3/pdata/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib
$ ls -lh src/mind3/pdata/sky130/
4.8K sky130_fd_sc_hd__tt_025C_1v80.lib (201 lines)
$ head liberty: library(sky130_fd_sc_hd__tt_025C_1v80){ delay_model:table_lookup; ... cell(sky130_fd_sc_hd__inv_1){...} }
```

- `[VERIFIED]` Exactly one Sky130 artifact is present: a 4.8 KiB, 201-line minimal test Liberty fixture with a single `inv_1` cell.
- `[VERIFIED]` No full PDK (no `MIND3_SKY130_ROOT` tech LEF, GDS, full multi-cell Liberty, SDC tech files) is present. A Liberty file alone is not treated as complete PDK availability.
- `[VERIFIED]` The minimal fixture is insufficient for the repo's OpenSTA workload (see §7 error).

## 9. Tests

Environment for all runs: `source .venv/bin/activate; export PATH="$HOME/.local/bin:$PATH"; export PYTHONPATH=src`.

Targeted infrastructure/toolchain tests:
```text
$ python -m pytest -q tests/test_linux_toolchain.py tests/test_sandbox_capability.py tests/test_negative_controls.py
2 failed, 27 passed, 1 skipped in 16.91s (also 17.22s on first run before click fix)
FAILED tests/test_linux_toolchain.py::test_opensta_smoke_version_and_workload
  AssertionError: OpenSTA workload failed: ... Library ... is missing one or more thresholds. assert 1 == 0
FAILED tests/test_negative_controls.py::test_affected_negative_control_reaches_intended_gate_live[timing_violation]
  AssertionError: expected=TIMING_SLACK_VIOLATION observed=TIMING_REPORT_UNPARSEABLE
  details=Failed to parse Worst Negative Slack (WNS) from OpenSTA output.
SKIPPED tests/test_negative_controls.py:197: cdc_violation: host Yosys lacks CDC command
```

Full suite (after `pip install click` repair; initial pre-click run was 12 failed, 302 passed, 6 skipped in 26.98s):
```text
$ python -m pytest -ra
7 failed, 307 passed, 6 skipped in 29.14s
SKIPPED test_macos_sandbox.py:58 (requires Darwin)
SKIPPED test_mind3.py:3419 (bwrap probe exit 1 execvp /bin/true; not a verified sandbox pass)
SKIPPED test_negative_controls.py:197 (cdc_violation: host Yosys lacks CDC command)
SKIPPED test_pdk_gates_canary.py:50,81,113 (require SkyWater PDK + bwrap/yosys/OpenSTA/OpenROAD)
FAILED test_claim_hygiene.py::test_banned_marketing_terms_enforced
FAILED test_fixtures_canary.py::test_environment_eda_tool_availability_honesty
FAILED test_gate2_mandatory.py::test_3_seq_pass
FAILED test_gate2_temporal_live.py::test_temporal_next_cycle_correct_passes_exercised_live
FAILED test_linux_toolchain.py::test_opensta_smoke_version_and_workload
FAILED test_negative_controls.py::test_affected_negative_control_reaches_intended_gate_live[timing_violation]
FAILED test_p5_coverage.py::test_p5_valid_fixture_pass (Coverage deficit: branch=0.0% min 50.0%, toggle=0.0% min 50.0%)
```

- `[VERIFIED]` Targeted and full-suite numbers are exact command outputs. No tests were edited or weakened.
- `[VERIFIED]` The 5-failure delta (12→7) is attributable to the host SBY `click` repair: formal Gate 2 tests that crashed on `ModuleNotFoundError: click` before the fix now execute.
- `[VERIFIED]` Remaining failures are host-capability/fixture issues (minimal Liberty, coverage shortfall) plus claim/fixture-honesty canaries, not edits to Gates 1–6 semantics (no source was changed to make checks pass).

## 10. Negative Controls

```text
$ export PYTHONPATH=src
$ python scripts/run_negative_controls.py --require-live
Executing 16 intentional-bug negative controls:
  [PASS] latch_inference              -> expected=LATCH_INFERRED, observed=LATCH_INFERRED
  [PASS] combinational_loop           -> expected=COMBINATIONAL_LOOP, observed=COMBINATIONAL_LOOP
  [PASS] incorrect_reset_behavior     -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [PASS] reset_deassertion_problem    -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [-] cdc_violation                ... SKIP (Host Yosys lacks CDC command; requires OSS CAD Suite)
  [PASS] fifo_overflow                -> expected=SIMULATION_FAILURE, observed=SIMULATION_FAILURE
  [PASS] fifo_underflow               -> expected=SIMULATION_FAILURE, observed=SIMULATION_FAILURE
  [PASS] off_by_one_counter           -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [PASS] incorrect_handshake          -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [PASS] incorrect_fsm_transition     -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [PASS] width_truncation             -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [PASS] signed_unsigned_error        -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [-] timing_violation             ... SKIP (timing library not configured)
  [PASS] false_formal                 -> expected=FORMAL_INVARIANT_BREACH, observed=FORMAL_INVARIANT_BREACH
  [PASS] sim_behavioral_failure       -> expected=SIMULATION_FAILURE, observed=SIMULATION_FAILURE
  [PASS] coverage_deficit             -> expected=COVERAGE_DEFICIT, observed=COVERAGE_DEFICIT
Report written to: artifacts/negative_controls_report.json
NOTE: one or more controls executed with real tools but without Bubblewrap namespaces
(host kernel forbids namespace creation). Results are real tool outputs (simulated=False),
not sandbox-verified runs.
Overall Negative-Control Verdict: SUCCESS
exit 0
JSON spot-check: every executed case has "simulated": false, "sandboxed": false,
"execution_mode": "unsandboxed_local".
```

Focus categories:
- `cdc_violation`: `[VERIFIED]` SKIP, observed `CDC_TOOLING_UNAVAILABLE` (Yosys lacks `cdc`). Never converted to PASS.
- `timing_violation`: `[VERIFIED]` SKIP in runner (`timing library not configured`); live pytest variant observes `TIMING_REPORT_UNPARSEABLE` on the minimal Liberty. Never converted to PASS.
- `latch_inference`: `[VERIFIED]` real Yosys execution, `LATCH_INFERRED`, unsandboxed.
- `combinational_loop`: `[VERIFIED]` real Yosys execution, `COMBINATIONAL_LOOP`, unsandboxed.
- `fifo_overflow` / `fifo_underflow`: `[VERIFIED]` real Verilator simulation failures, unsandboxed.
- No skipped control is counted as a pass. All passes are real-tool but unsandboxed (`simulated=False`, `sandboxed=False`).

## 11. Documentation Accuracy

Searched: `grep -RniE 'CDC|OpenROAD|OpenSTA|bubblewrap|bwrap|OSS CAD Suite|live EDA' README.md docs .github | head -200`.

- `[VERIFIED]` README Gate 6 fails closed when `cdc` absent; `require_cdc` semantics; OSS CAD Suite `2026-09-29` linux-arm64 lacking `cdc` (`No such command`) — consistent with §4 on this x86_64 host (both system and OSS Suite 20260921 lack `cdc`).
- `[VERIFIED]` KNOWN_LIMITATIONS §3 correctly states OpenROAD not executed on macOS, Yosys CDC absent in tested builds with fail-closed `CDC_TOOLING_UNAVAILABLE`, Bubblewrap Linux-only, full PDK requires `MIND3_SKY130_ROOT`. Consistent with §§4,5,8.
- `[VERIFIED]` `docs/linux_verification.md` GitHub-runner namespace limitation (`No permissions...`) is a different failure mode than this host's usrmerge bind omission (`execvp /bin/true`). Both honestly report incapable probes, but the reasons differ. This host additionally proves full-bind namespaces + egress block work manually.
- `[VERIFIED]` No documentation was rewritten in this task. The stale `docs/phase4_readiness.md:7` line ("Bubblewrap, Yosys, SymbiYosys, Verilator, OpenSTA are not installed") is contradicted by §3 on THIS host (all are installed), but it describes the earlier dev host, not a claim about this Linux host; reported here rather than edited.
- `[PENDING-HUMAN]` Linux OpenSTA/OpenROAD execution, CDC-capable Yosys demonstration, and full ≥100-task heldout release eligibility remain pending per existing gap matrices; this task does not close them.

## 12. Remaining Blockers

Only evidence-backed blockers (no inference):

1. `[VERIFIED]` Yosys CDC unavailable: system Yosys 0.33 and OSS CAD Suite Yosys 0.69+77 both return `No such command or cell type: cdc`. Gate 6 cannot verify; `cdc_violation` control SKIPs.
2. `[VERIFIED]` Bundled Liberty insufficient for OpenSTA: 4.8 KiB single-cell fixture triggers `missing one or more thresholds` (exit 1) and `TIMING_REPORT_UNPARSEABLE`. `test_opensta_smoke_version_and_workload` and live `timing_violation` fail. Full SkyWater PDK absent.
3. `[VERIFIED]` Repo bwrap probe incompatible with usrmerge: binds only `/usr`+`/bin`, omits `/lib`+`/lib64`, so `probe_bubblewrap_namespace_capability()` returns False on Ubuntu 24.04 even though manual full-bind namespaces and egress blocking succeed. Consequence: live runs fall back to `unsandboxed_local` (`sandboxed=false`) and `test_mind3.py:3419` skips. Fixing the probe is a source change and was NOT made in this task.
4. `[VERIFIED]` Full suite not green: 7 failed / 307 passed / 6 skipped (after click repair). Includes OpenSTA smoke, timing live control, Gate 2 `test_3_seq_pass`, one temporal-live test, coverage `test_p5_valid_fixture_pass` (0.0% vs 50% minima), and two claim/fixture-honesty canaries. No source was altered to hide them.
5. `[VERIFIED]` SBY venv dependency gap (now repaired locally): SBY required `click` in the venv. Fixed by `pip install click` (venv-only). CI images must include it or SBY crashes.
6. `[VERIFIED]` Git metadata unavailable: workdir has no `.git`; branch/HEAD/cleanliness and commit safety cannot be attested via Git. No commit/push was performed.

Not blockers (to avoid overclaiming): kernel namespace support itself (works with correct binds), host network (works), Yosys/Verilator/Z3/STA/OpenROAD binary presence (all present).

## 13. Evidence Classification

- All toolchain paths/versions in §3: `[VERIFIED]`.
- CDC unavailability in §4: `[VERIFIED]`.
- Bwrap Test 1 failure mode (bind omission, not kernel denial) and Test 2 success: `[VERIFIED]`.
- Repo probe False with `execvp /bin/true` reason: `[VERIFIED]`.
- Host-vs-sandbox network result in §6: `[VERIFIED]` (host SUCCESS, sandbox `Network is unreachable`).
- OpenROAD/STA `-version` executability: `[VERIFIED]`; any PnR/timing signoff: not claimed (`[UNVERIFIED]`/`[PENDING-HUMAN]`).
- PDK single-fixture inventory: `[VERIFIED]`; full-PDK availability: `[VERIFIED]` absent.
- Targeted (2F/27P/1S) and full-suite (7F/307P/6S post-click; 12F/302P/6S pre-click) numbers: `[VERIFIED]`.
- Negative controls (14 real unsandboxed PASS, 2 SKIP, verdict SUCCESS, `sandboxed=false`): `[VERIFIED]`.
- Documentation comparisons: `[VERIFIED]` where quoted; release/heldout/license items: `[PENDING-HUMAN]`.
- No `[INFERRED]` label is used. No synthetic/deterministic test is presented as real EDA evidence.
