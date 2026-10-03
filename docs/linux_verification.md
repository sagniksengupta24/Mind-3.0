# Linux Verification & Platform Evidence Separation (Stage 5)

A result on one platform is never a result on another. Every
environment-dependent record carries a `platform` field (`darwin` or
`linux`), produced by `src/mind3/sandbox/linux_toolchain.py`, and claims
below are labeled accordingly.

## Verified on macOS (this session, real execution)

| Item | Evidence |
| ---- | -------- |
| Python/Yosys/SBY/Z3/Verilator/OpenSTA versions | `probe_tool` records from executed `--version`/`-V` output (darwin) |
| Homebrew Yosys lacks `cdc` | Executed `yosys -p "help cdc"` → `No such command or cell type: cdc`; `probe_yosys_cdc` reports `cdc_available: False` |
| Gate 6 without `cdc` fails closed | `test_gate6_cdc_fixture_environment_behavior` on `cdc_violation.sv` → `CDC_TOOLING_UNAVAILABLE`, never PASS |
| OpenSTA executes | `test_opensta_smoke_version_and_workload`: `sta -version` rc=0 plus a legal `read_liberty`/`read_verilog`/`link_design`/`report_checks` workload rc=0 (availability proof, not timing signoff) |
| Seatbelt blocks egress | `test_macos_seatbelt_egress_blocked_by_real_socket_attempt`: live loopback listener accepts outside the sandbox; the identical in-sandbox connect is denied with `errno=1 Operation not permitted` |
| Bubblewrap egress | Not verifiable on macOS (no `bwrap` binary): test skips with reason |
| OpenROAD | Not verifiable on macOS (binary absent): test skips with reason |

## Linux container execution (this session, real execution)

A privileged `ubuntu:22.04` (aarch64, kernel `7.0.12-linuxkit`) container on
this machine provided, all from executed binaries: Python 3.10.12 (repo tests
ran under deadsnakes Python 3.11.17), bubblewrap 0.6.1, Yosys 0.69+156,
SBY v0.69, Z3 4.15.5, Verilator 5.053 (all OSS CAD Suite `linux-arm64`,
pinned tag `2026-09-29`, added as an explicit `--arch` installer option; CI
default `x64` unchanged).

Executed Linux results: `yosys -p "help cdc"` → `No such command or cell
type: cdc` (the pinned suite has no CDC plugin — only unrelated Python
`cdc.py` library files); real Gate 6 on `tests/negative_controls/cdc_violation.sv`
→ `passed: False`, `CDC_TOOLING_UNAVAILABLE`, `simulated: False`;
bwrap egress test → PASSED (host baseline connected, sandbox attempts
blocked); Gate 2 temporal live tests → PASSED; full container suite →
287 passed, 15 skipped, 0 failed.

No OpenSTA or OpenROAD binary exists in the pinned suite or the container,
so Linux OpenSTA/OpenROAD execution remains `[PENDING-HUMAN]` (CI). The
`sta`/`openroad` smoke tests skip honestly when absent.

## Pending CI/Linux execution

`[PENDING-HUMAN]` — requires CI/Linux execution:

- Full `eda_live.yml` run on `ubuntu-24.04` (unit + `eda` + negative
  controls `--require-live` + evidence artifacts).
- OpenROAD smoke execution (binary presence in the Linux image
  unconfirmed; the smoke test skips honestly when absent).
- Any claim of the form "verified on Linux" beyond the container results
  captured in-session.

## Claims that stay as-is

- The README statement attributing the Yosys `cdc` command to the OSS CAD
  Suite Linux distribution remains `[UNVERIFIED]` until a Linux OSS CAD
  Suite environment demonstrates it in CI. Writing `.github/workflows/eda_live.yml`
  or `Dockerfile.eda` is preparation, not verification.
- `which <tool>` output is availability hint only; only executed version
  queries and workloads count as evidence (see `linux_toolchain.py`).
