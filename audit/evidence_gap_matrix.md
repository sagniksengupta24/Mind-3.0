# Evidence Gap Matrix (closure pass, 2026-10-03)

Model/provider frozen: `ollama / qwen2.5-coder:7b`, strict parser default.
No source, gate, parser, or benchmark-methodology changes were made in this pass.

| Gap | Current status | What would constitute proof | Can this environment prove it? | Action |
| --- | -------------- | --------------------------- | ------------------------------ | ------ |
| Linux CI actual execution | Partially closed | `eda_live.yml` green on ubuntu-24.04 | No (this host is Darwin; container spot-checks only) | `[PENDING-HUMAN]` CI run |
| OSS CAD Suite Linux CDC | **Closed (verified absent)** | `yosys -p "help cdc"` on pinned build | Yes — done: Yosys 0.69+156, `No such command or cell type: cdc`; Gate 6 fails closed | None; documented |
| OpenROAD execution | Still pending | `openroad -version` + minimal PnR workload | No binary in pinned suite or container; full image is GB-scale | `[PENDING-HUMAN]` provision Linux OpenROAD image |
| OpenSTA on Linux | Still pending | `sta -version` + Liberty workload | No binary in pinned suite or container | `[PENDING-HUMAN]` |
| Linux Bubblewrap egress | **Closed** | Real outbound attempt blocked with sandbox-caused denial | Yes — done: repo test PASSED in Linux container (bubblewrap 0.12.0, host baseline connected) | None; documented |
| macOS Seatbelt egress | **Closed** | Real socket attempt denied, `errno=1` | Yes — re-ran: 5/5 sandbox tests pass | None; documented |
| Unbounded formal | Not proven | Induction/`prove` mode in backend | No such mode (fixed BMC depth 25) | `NOT CURRENTLY PROVEN` |
| Heldout cleanliness | `UNVERIFIED` | Recoverable tuning history disjoint from heldout | No (history squashed; dev⊆heldout executed live) | Keep `UNVERIFIED` |
| License | Missing | Owner-chosen `LICENSE` + pyproject declaration | No (must not invent terms) | `REQUIRES HUMAN DECISION` |
| ≥100-task heldout run | Diagnostic (20/42) | ≥100 real heldout transcripts, same config | Runnable but ~2h; not executed this pass | `[PENDING-HUMAN]` full run |
| Release eligibility | Not established | ≥100 tasks + Stage 2b thresholds | No new evidence this pass | Keep diagnostic |

Closed this pass: Linux CDC absence (corroborated), Linux bwrap egress (re-verified),
macOS Seatbelt egress (re-verified). Everything else keeps its prior label.
