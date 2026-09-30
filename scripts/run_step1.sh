#!/usr/bin/env bash
# scripts/run_step1.sh: Execute all 10 tasks in Step 1 Baseline Benchmark
set -eo pipefail

export PATH=/home/mind/oss-cad-suite/bin:/home/mind/openroad-env/bin:$PATH
PYTHON="/home/mind/Desktop/AI/Mind-3.0/.venv/bin/python"

echo "=========================================================="
echo "Starting Mind 3.0 Step 1 Empirical Baseline Benchmark"
echo "Model: qwen2.5-coder:30b via local Ollama"
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "=========================================================="

${PYTHON} /home/mind/Desktop/AI/Mind-3.0/scripts/execute_task_engine.py --task all

echo "Collecting and verifying Step 1 results..."
${PYTHON} /home/mind/Desktop/AI/Mind-3.0/scripts/collect_step1_results.py

echo "Validating audit report consistency..."
${PYTHON} /home/mind/Desktop/AI/Mind-3.0/scripts/validate_audit_report.py

echo "Step 1 Baseline Benchmark execution complete."
