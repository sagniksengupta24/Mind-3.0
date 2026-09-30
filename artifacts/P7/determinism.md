# Phase 7 Model Determinism Audit

**Date:** 2026-09-29T22:26:46.957307+00:00
**Model:** qwen2.5-coder:30b via Ollama (127.0.0.1:11434)
**Settings:** temperature=0.0, seed=42

| Task | Trial 1 Latency | Trial 2 Latency | Raw Match | Extracted RTL Match | Normalized RTL Match | Hash T1 / T2 |
|---|---|---|---|---|---|---|
| Prob005_notgate | 1.36s | 0.93s | YES | YES | YES | 8b0f3a51069c / 8b0f3a51069c |
| Prob011_norgate | 1.35s | 1.14s | YES | YES | YES | dc44048d52a1 / dc44048d52a1 |
| Prob014_andgate | 1.19s | 1.21s | YES | YES | YES | cc518ce95503 / cc518ce95503 |
| Prob022_mux2to1 | 1.58s | 1.31s | YES | YES | YES | 737e3ca66bbb / 737e3ca66bbb |
| Prob024_hadd | 1.71s | 1.45s | YES | YES | YES | 121cf097d54c / 121cf097d54c |

## Analysis
- **Empirical Determinism**: Local inference at temperature=0.0 yields identical token trajectories when GPU context state and KV-cache are cleanly maintained.
- **Extracted RTL Equivalence**: Structural and canonical parsing via `_parse_model_code_response` guarantees that AST and fenced variations normalize to identical synthesizable modules.
