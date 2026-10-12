#!/bin/zsh
# Generator-recovery sweep queue: baseline (legacy/json) + Track F (text) +
# Track J (json-schema), 3 seeds each, dev-20. Sequential; Ollama serializes
# concurrent requests anyway. Each sweep gets its own dirs + log.
cd /Users/sagniksengupta/Desktop/AI/Mind-3.0 || exit 1
export PYTHONPATH=src
TASKS=benchmarks/development-20/tasks.jsonl
run_sweep() {
  local name=$1 fmt=$2 seed=$3
  local dir="artifacts/exp_${name}"
  echo "=== SWEEP ${name} fmt=${fmt} seed=${seed} started $(date) ===" | tee -a /tmp/sweeps.log
  python3 -m mind3.benchmarks.runner \
    --tasks "${TASKS}" \
    --transcripts "${dir}/transcripts" \
    --report-dir "${dir}/report" \
    --diagnostic --min-tasks 20 \
    --model qwen2.5-coder:7b --provider ollama --max-repairs 3 \
    --generation-format "${fmt}" --decode-seed "${seed}" \
    >> "/tmp/sweep_${name}.log" 2>&1
  echo "=== SWEEP ${name} exit=$? finished $(date) ===" | tee -a /tmp/sweeps.log
}
for seed in 42 43 44; do run_sweep "base${seed}" json "${seed}"; done
for seed in 42 43 44; do run_sweep "trackF${seed}" text "${seed}"; done
for seed in 42 43 44; do run_sweep "trackJ${seed}" json-schema "${seed}"; done
echo "ALL SWEEPS DONE $(date)" | tee -a /tmp/sweeps.log
