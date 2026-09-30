#!/usr/bin/env bash
# Mind 3.0 Verification Readiness Checker
# Computes PRODUCTION-READY, PARTIALLY-VALIDATED, or NOT-READY verdict.

set -o pipefail

REPO_ROOT="/home/mind/Desktop/AI/Mind-3.0"
cd "$REPO_ROOT"
export PATH="/home/mind/oss-cad-suite/bin:/home/mind/.local/bin:$PATH"
export PYTHONPATH="src:$PYTHONPATH"

TOTAL_CHECKS=0
FAILED_CHECKS=0

run_check() {
    local label="$1"
    local command="$2"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    printf "[%2d] %-65s ... " "$TOTAL_CHECKS" "$label"
    if eval "$command" > /tmp/readiness_step.log 2>&1; then
        echo "PASS"
    else
        echo "FAIL"
        echo "     Error details:"
        tail -n 8 /tmp/readiness_step.log | sed 's/^/     > /'
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
}

echo "=========================================================================="
echo "Mind 3.0 Autonomous Readiness Verification Suite"
echo "=========================================================================="

# ── Static Security & Integrity Invariants ──
run_check "Static: No allow_mock_fallback=True in benchmark runners" \
    "! grep -rn 'allow_mock_fallback=True' /home/mind/Desktop/AI/benchmark_scratch/run_benchmarks.py scripts/run_clean_30_tasks.py"

run_check "Static: Formal and coverage gates enabled by default" \
    "python3 -c \"from mind3.core.verifier import SiliconSignoffVerifier; v = SiliconSignoffVerifier('top'); assert v.require_formal is True and v.require_coverage is True\""

run_check "Static: Unsupported formal properties fail closed (never PASS)" \
    "pytest -q tests/test_gate2_mandatory.py -k test_7_unsupported_property_never_pass"

run_check "Static: Zero tautological fallback properties (assert 1'b1)" \
    "! grep -rn \"assert(1'b1)\" src/"

# ── Behavioral Formal Verification Invariants (Gate 2) ──
run_check "Behavioral: Clean combinational DUT -> Formal PASS" \
    "pytest -q tests/test_gate2_mandatory.py -k test_1_comb_pass"

run_check "Behavioral: Buggy combinational DUT -> Formal FAIL" \
    "pytest -q tests/test_gate2_mandatory.py -k test_2_comb_fail"

run_check "Behavioral: Clean sequential DUT -> Formal PASS" \
    "pytest -q tests/test_gate2_mandatory.py -k test_3_seq_pass"

run_check "Behavioral: Buggy sequential DUT -> Formal FAIL" \
    "pytest -q tests/test_gate2_mandatory.py -k test_4_seq_fail"

# ── Behavioral Coverage Verification Invariants (Gate 3) ──
run_check "Behavioral: Valid coverage fixture -> Gate 3 PASS" \
    "pytest -q tests/test_p5_coverage.py -k test_p5_valid_fixture_pass"

run_check "Behavioral: Broken fixture -> Gate 3 FAIL" \
    "pytest -q tests/test_p5_coverage.py -k test_p5_broken_fixture_fail"

run_check "Behavioral: Below-threshold coverage -> Gate 3 FAIL" \
    "pytest -q tests/test_p5_coverage.py -k test_p5_below_threshold_fail"

# ── Regression & Benchmark Suite Integrity ──
run_check "Suite: Full unit and integration test suite passes" \
    "pytest -q"

run_check "Benchmark: results.csv contains exactly 30 classified rows" \
    "python3 -c \"import csv; rows = list(csv.DictReader(open('artifacts/P6/results.csv'))); assert len(rows) == 30, f'Expected 30 rows, found {len(rows)}'\""

run_check "Benchmark: Every passing signoff row has an authentic log" \
    "python3 -c \"import csv, os; rows = list(csv.DictReader(open('artifacts/P6/results.csv'))); assert all(os.path.exists(r['log_path']) for r in rows if r['mind3_signoff'] == 'PASS')\""

echo "=========================================================================="
echo "Readiness Results: $TOTAL_CHECKS checks executed ($((TOTAL_CHECKS - FAILED_CHECKS)) passed, $FAILED_CHECKS failed)"

if [ "$FAILED_CHECKS" -eq 0 ]; then
    echo "VERDICT: PRODUCTION-READY"
    exit 0
elif [ "$FAILED_CHECKS" -le 2 ]; then
    echo "VERDICT: PARTIALLY-VALIDATED"
    exit 1
else
    echo "VERDICT: NOT-READY"
    exit 2
fi
