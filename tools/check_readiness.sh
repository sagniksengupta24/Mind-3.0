#!/usr/bin/env bash
# Mind 3.0 evidence-gated readiness checker.
# This script intentionally distinguishes code/test readiness from live EDA evidence.

set -o pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="src:$PYTHONPATH"

TOTAL_CHECKS=0
FAILED_CHECKS=0
LIVE_EDA="${MIND3_RUN_LIVE_EDA:-0}"
REPORT_DIR="${MIND3_BENCHMARK_REPORT_DIR:-artifacts/benchmark_report}"
SUMMARY="$REPORT_DIR/benchmark_summary.json"

run_check() {
    local label="$1"
    local command="$2"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    printf "[%2d] %-72s ... " "$TOTAL_CHECKS" "$label"
    if eval "$command" > /tmp/readiness_step.log 2>&1; then
        echo "PASS"
    else
        echo "FAIL"
        echo "     Error details:"
        tail -n 10 /tmp/readiness_step.log | sed 's/^/     > /'
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

note_check() {
    local label="$1"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    printf "[%2d] %-72s ... %s\n" "$TOTAL_CHECKS" "$label" "NOT-RUN"
}

echo "=========================================================================="
echo "Mind 3.0 Evidence-Gated Readiness Verification"
echo "=========================================================================="

# Foundation / fail-closed invariants.
run_check "Foundation: no benchmark mock-fallback opt-in" \
    "python3 - <<'PYCODE'
import ast
from pathlib import Path
for root in (Path('scripts'), Path('src'), Path('tests/negative_controls')):
    for path in root.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == 'allow_mock_fallback' and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        raise SystemExit(f'{path}:{node.lineno}: allow_mock_fallback=True')
print('no executable benchmark mock-fallback opt-in found')
PYCODE"

run_check "Foundation: formal, coverage, and CDC are strict defaults" \
    "python3 -c \"from mind3.core.verifier import SiliconSignoffVerifier; v=SiliconSignoffVerifier('top'); assert v.require_formal and v.require_coverage and v.require_cdc and not v.allow_mock_fallback\""

run_check "Foundation: unsupported formal properties fail closed" \
    "pytest -q tests/test_gate2_mandatory.py -k test_7_unsupported_property_never_pass"

run_check "Foundation: deterministic formal compiler has no tautological fallback" \
    "! grep -Rns \"assert(1'b1)\" src/"

run_check "Foundation: Python source compiles" \
    "python3 -m compileall -q src scripts tools tests"

# Unit suite deliberately excludes live EDA markers on hosts without tools.
run_check "Regression: non-EDA unit/integration suite passes" \
    "pytest -q -m 'not eda'"

run_check "Benchmark: 50-task corpus loads and remains uniquely identified" \
    "python3 -c \"from mind3.benchmarks.runner import BenchmarkRunner; r=BenchmarkRunner(); t=r.load_tasks(); assert len(t)==50 and len({x.task_id for x in t})==50\""

run_check "Benchmark: persisted transcripts are truthfully marked as fixtures" \
    "pytest -q tests/test_benchmarks.py -k test_benchmark_transcripts_fixtures_integrity_and_labeling"

run_check "Benchmark: evaluator excludes mock fixtures from performance metrics" \
    "pytest -q tests/test_benchmarks.py -k 'evaluate or fixtures_integrity'"

run_check "Benchmark: dry-run reports live prerequisites without bypassing safety" \
    "python3 -m mind3.benchmarks.runner --dry-run"

if [ "$LIVE_EDA" = "1" ]; then
    LIVE_MISSING="$(PYTHONPATH=src python3 - <<'PYCODE'
import shutil
print(" ".join(name for name in ("bwrap", "yosys", "sby", "verilator", "sta") if shutil.which(name) is None))
PYCODE
)"
    if [ -n "$LIVE_MISSING" ]; then
        run_check "Live EDA: Bubblewrap + Yosys + SBY + Verilator + STA are available" \
            "false"
        note_check "Live EDA: intentionally broken designs are rejected by real gates (blocked by prerequisites)"
        note_check "Live EDA: EDA-marked test suite passes (blocked by prerequisites)"
        echo "LIVE EDA BLOCKED: missing prerequisites: $LIVE_MISSING"
    else
        run_check "Live EDA: Bubblewrap + Yosys + SBY + Verilator + STA are available" \
            "python3 -m mind3.benchmarks.runner --dry-run --require-live"
        run_check "Live EDA: intentionally broken designs are rejected by real gates" \
            "python3 scripts/run_negative_controls.py --require-live"
        run_check "Live EDA: mandatory EDA test suite passes" \
            "pytest -q -m eda"
    fi
else
    note_check "Live EDA: prerequisite probe (set MIND3_RUN_LIVE_EDA=1 to execute)"
    note_check "Live EDA: negative-control suite (set MIND3_RUN_LIVE_EDA=1 to execute)"
    note_check "Live EDA: EDA-marked test suite (set MIND3_RUN_LIVE_EDA=1 to execute)"
fi

echo "=========================================================================="
echo "Checks: $TOTAL_CHECKS | Passed: $((TOTAL_CHECKS - FAILED_CHECKS)) | Failed: $FAILED_CHECKS"

REAL_TASKS=0
FUNCTIONAL_RATE=0
VERIFIED_RATE=0
FIXTURE_COUNT=0
if [ -f "$SUMMARY" ]; then
    read -r REAL_TASKS FUNCTIONAL_RATE VERIFIED_RATE FIXTURE_COUNT <<EOF2
$(python3 - <<'PY'
import json
from pathlib import Path
p = Path("artifacts/benchmark_report/benchmark_summary.json")
if not p.exists():
    print("0 0 0 0")
else:
    d = json.loads(p.read_text())
    print(d.get("real_transcript_count", 0), d.get("functional_pass_rate", 0), d.get("full_verified_pass_rate", 0), d.get("fixture_count", 0))
PY
)
EOF2
fi

printf "Evidence summary: real=%s, fixtures=%s, functional=%s, full_verified=%s\n" \
    "$REAL_TASKS" "$FIXTURE_COUNT" "$FUNCTIONAL_RATE" "$VERIFIED_RATE"

if [ "$FAILED_CHECKS" -ne 0 ]; then
    if [ "$LIVE_EDA" = "1" ] && [ -n "${LIVE_MISSING:-}" ]; then
        echo "VERDICT: EXPERIMENTAL — requested live EDA but prerequisites are missing"
        exit 1
    fi
    echo "VERDICT: NOT-READY (regression or integrity failure)"
    exit 2
fi

if [ "$LIVE_EDA" != "1" ]; then
    echo "VERDICT: EXPERIMENTAL — code-ready, live EDA not executed on this host"
    exit 1
fi

if [ "$REAL_TASKS" -lt 100 ]; then
    echo "VERDICT: EXPERIMENTAL — insufficient real holdout evidence (<100 tasks)"
    exit 1
fi

python3 - "$FUNCTIONAL_RATE" "$VERIFIED_RATE" <<'PY'
import sys
functional = float(sys.argv[1])
verified = float(sys.argv[2])
if functional >= 0.85 and verified >= 0.70:
    print("VERDICT: MEETS-9-OF-10-EVIDENCE-THRESHOLD")
elif functional >= 0.80 and verified >= 0.60:
    print("VERDICT: STRONG-SPECIALIST-TOOL")
elif functional >= 0.70 and verified >= 0.40:
    print("VERDICT: USEFUL-SPECIALIST-TOOL")
else:
    print("VERDICT: EXPERIMENTAL — benchmark evidence below release threshold")
sys.exit(0 if functional >= 0.70 and verified >= 0.40 else 1)
PY
