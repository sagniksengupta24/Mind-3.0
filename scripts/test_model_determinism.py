#!/usr/bin/env python3
"""
scripts/test_model_determinism.py: Runs 2 identical inference trials under identical parameters
to empirically measure whether the local Ollama model generation is bitwise reproducible.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import time
from pathlib import Path
import httpx

WORKSPACE_ROOT = Path(os.environ.get("MIND3_ROOT", Path(__file__).resolve().parents[1])).resolve()
AUDIT_DIR = WORKSPACE_ROOT / "artifacts/audit"
TASKS_DIR = WORKSPACE_ROOT / "benchmarks/mind_baseline/tasks"

OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
MODEL_NAME = "qwen2.5-coder:30b"

SYSTEM_PROMPT = (
    "You are an expert digital ASIC designer specializing in synthesizable SystemVerilog. "
    "Write correct, standard-compliant, synthesizable SystemVerilog RTL matching the exact port declarations. "
    "Do not infer latches. Ensure all branches are completely specified. "
    "Output ONLY synthesizable code enclosed in ```systemverilog ... ```."
)


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_trial(prompt: str) -> dict:
    t0 = time.time()
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "options": {
            "temperature": 0.0,
            "num_predict": 2048,
            "seed": 42
        },
        "stream": False
    }
    resp = httpx.post(f"{OLLAMA_ENDPOINT}/api/chat", json=payload, timeout=90.0)
    t1 = time.time()
    if resp.status_code != 200:
        raise RuntimeError(f"Ollama error {resp.status_code}: {resp.text}")
    content = resp.json().get("message", {}).get("content", "")
    return {
        "content": content,
        "sha256": compute_sha256(content),
        "latency_seconds": round(t1 - t0, 3)
    }


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    task_json = json.loads((TASKS_DIR / "priority_encoder.json").read_text(encoding="utf-8"))
    prompt = task_json["generation_prompt"]

    print("=================================================================")
    print("Testing Model Determinism across 2 Identical Trials (temp=0.0, seed=42)")
    print("=================================================================")

    print("Running Trial 1...")
    trial1 = run_trial(prompt)
    print(f"Trial 1 Hash: {trial1['sha256']} (Latency: {trial1['latency_seconds']}s)")

    print("Running Trial 2...")
    trial2 = run_trial(prompt)
    print(f"Trial 2 Hash: {trial2['sha256']} (Latency: {trial2['latency_seconds']}s)")

    is_bitwise_identical = (trial1["sha256"] == trial2["sha256"])
    status = "bitwise reproducible" if is_bitwise_identical else "NOT bitwise reproducible"

    result = {
        "test": "Model Generation Determinism Trial",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": MODEL_NAME,
        "provider": "Ollama (local 127.0.0.1:11434)",
        "parameters": {
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 42,
            "num_predict": 2048
        },
        "task_id": "priority_encoder",
        "trial_1": {
            "sha256": trial1["sha256"],
            "latency_seconds": trial1["latency_seconds"]
        },
        "trial_2": {
            "sha256": trial2["sha256"],
            "latency_seconds": trial2["latency_seconds"]
        },
        "is_bitwise_identical": is_bitwise_identical,
        "determinism_classification": status,
        "conclusion": "Model generation is bitwise reproducible under greedy temperature=0.0 with pinned seed on local Ollama." if is_bitwise_identical else "Model generation exhibited non-deterministic output drift across identical prompt parameters."
    }

    out_file = AUDIT_DIR / "determinism_test.json"
    out_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nResult: {status.upper()}")
    print(f"Report saved to {out_file}")


if __name__ == "__main__":
    main()
