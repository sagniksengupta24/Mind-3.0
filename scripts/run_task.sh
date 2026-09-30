#!/usr/bin/env bash
# scripts/run_task.sh: Execute a single Mind 3.0 benchmark task
set -eo pipefail

TASK_ID="$1"
if [ -z "$TASK_ID" ]; then
    echo "Usage: $0 <task_id>"
    exit 1
fi

export PATH=/home/mind/oss-cad-suite/bin:/home/mind/openroad-env/bin:$PATH
PYTHON="/home/mind/Desktop/AI/Mind-3.0/.venv/bin/python"

echo "Executing benchmark task: ${TASK_ID}"
${PYTHON} /home/mind/Desktop/AI/Mind-3.0/scripts/execute_task_engine.py --task "${TASK_ID}"
