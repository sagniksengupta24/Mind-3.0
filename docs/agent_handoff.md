# Agent handoff — convert 11/20 to 20/20 with a stronger model

Date: 2026-10-08. Current headline: **11/20** (`artifacts/exp_c10_rerun_s43/`,
seed 43, `qwen2.5-coder:7b` via Ollama, `generation-format text`,
`max-repairs 3`, diagnostic). All harness fixes below are already applied;
the 9 remaining failures are model-RTL quality, not pipeline bugs.

## How to rerun

```bash
cd /path/to/Mind-3.0
export PYTHONPATH=src
python3 -m mind3.benchmarks.runner \
  --tasks benchmarks/development-20/tasks.jsonl \
  --transcripts artifacts/exp_<name>/transcripts \
  --report-dir artifacts/exp_<name>/report \
  --diagnostic --min-tasks 20 \
  --model <BETTER_MODEL> --provider ollama --max-repairs 3 \
  --generation-format text --decode-seed 43 \
  --liberty /path/to/sky130_fd_sc_hd__tt_025C_1v80.lib   # real PDK lib (~13MB); repo stub breaks Yosys ABC
```

Swap `--model` for the stronger model (keep `--provider ollama` or switch to
`openrouter` with `OPENROUTER_API_KEY`). Do NOT lower gates, thresholds, or
`--min-tasks`; do NOT edit tests to make things pass.

## The 9 failing tasks (all evidence under `artifacts/exp_c10_rerun_s43/`)

| task | gate signal (root cause in generated RTL) | what good looks like |
|---|---|---|
| `arbiter_02` | `FORMAL_INVARIANT_BREACH` — fixed-priority grant logic wrong | `req[0] → gnt[0]`, `$onehot0(gnt)` hold under BMC |
| `arbiter_03` | `FORMAL_INVARIANT_BREACH` — handshake race mishandled | grants clear exactly when `req` drops at the edge |
| `counter_04` | `COVERAGE_DEFICIT` (toggle 11% vs 90%) — wrong Johnson rotate `{count[6],count[5:0],count[7]}` | true Johnson feedback `{!count[0],count[7:1]}` so all bits toggle |
| `fifo_01` | `TYPE_WIDTH_ERROR` — `full`/`empty` driven both procedurally and by `assign` | single driver (combinational assigns only) |
| `fifo_03` | `COVERAGE_BUILD_FAILURE` — 5-bit ptrs on 16-deep mem, 8-bit data into 16-bit mem (`WIDTHTRUNC`/`WIDTHEXPAND`) | `[7:0] mem[0:15]`, 4-bit ptrs, width-exact assigns |
| `fifo_04` | `SYNTAX_ERROR` line 53 — output truncated mid-`assign` | complete dual-clock gray-FIFO; raise `num_predict` if truncated |
| `fsm_heldout_04` | `COVERAGE_BUILD_FAILURE`→deficit — 3-bit `count` vs `5'b11111` never true, `stuffed` dead | counter width matches compare constant; `stuffed` reachable |
| `reg_if_01` | `SYNTAX_ERROR`/`COVERAGE_BUILD_FAILURE` — undeclared `write_addr`, 256-bit `reg_file <= 32'd0` | declared addresses, width-exact reset values |
| `spi_02` | `COVERAGE_BUILD_FAILURE` — 3-bit `bit_count == 2'b11`, 1-bit→8-bit assign, unused `rx_buffer` | `3'b111`, zero-extended assigns, no dead signals |

Per-task ground truth: each `transcripts/<task>.json` holds
`final_outcome.gate_reports[]` (tool, exit code, stderr) and
`repair_attempts[]`. Width discipline wins most of these: N-bit ports
declared `[N-1:0]`, compare literals sized to the signal, one driver per net.

## Already fixed — do not re-fix

- SBY workdir double-include (`_select_signoff_sources`, `verifier.py`)
- `arbiter_02` dev-20 ports; `heldout-v2/` versioned suite (parent `heldout/` SHA `bae56a8d` untouched)
- Multi-clock structural rule (`contracts.py`): dual-clock contracts require an edge block per clock
- Architect 1 bounded retry; repair-loop 3-strikes cap on dead model endpoints
- Gate 6 crux backend (wired, probed; installs where network allows)
- Intent gate + `ask()` fast path; chat router (`mind-chat/server.py`)

## Success criteria

- `benchmark_summary.json`: `full_verified_pass_count` ≥ 18/20, zero
  `SPECIFICATION_ERROR` / `RESPONSE_PARSE_FAILURE`, zero false PASS on the
  negative controls (`./bin/mind3 negative-controls --require-live`).
- `pytest -q -m 'not eda'` stays green (currently 363 passed).
- Every PASS row has a real tool log path in `results.csv`/transcript.
