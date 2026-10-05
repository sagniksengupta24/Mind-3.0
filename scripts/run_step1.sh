#!/usr/bin/env bash
# scripts/run_step1.sh: Execute all 10 tasks in Step 1 Baseline Benchmark
set -eo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="${MIND3_PYTHON:-$REPO_ROOT/.venv/bin/python}"

echo "=========================================================="
echo "Starting Mind 3.0 Step 1 Empirical Baseline Benchmark"
echo "Model: qwen2.5-coder:30b via local Ollama"
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "=========================================================="

${PYTHON} "$REPO_ROOT/scripts/execute_task_engine.py" --task all

echo "Collecting and verifying Step 1 results..."
${PYTHON} "$REPO_ROOT/scripts/collect_step1_results.py"

echo "Validating audit report consistency..."
${PYTHON} "$REPO_ROOT/scripts/validate_audit_report.py"

echo "Step 1 Baseline Benchmark execution complete."
