#!/usr/bin/env bash
# scripts/run_task.sh: Execute a single Mind 3.0 benchmark task
set -eo pipefail

TASK_ID="$1"
if [ -z "$TASK_ID" ]; then
    echo "Usage: $0 <task_id>"
    exit 1
fi

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="${MIND3_PYTHON:-$REPO_ROOT/.venv/bin/python}"

echo "Executing benchmark task: ${TASK_ID}"
${PYTHON} "$REPO_ROOT/scripts/execute_task_engine.py" --task "${TASK_ID}"
