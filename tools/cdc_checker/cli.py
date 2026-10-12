"""Command-line interface for the structural CDC checker.

Exit codes: 0 = CDC PASS, 1 = CDC FAIL, 2 = CDC INCONCLUSIVE,
3 = CDC TOOL/INPUT ERROR. INCONCLUSIVE and ERROR are never PASS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .report import (
    EXIT_ERROR,
    EXIT_FAIL,
    EXIT_INCONCLUSIVE,
    EXIT_PASS,
    run_checker,
)

# Phase 18 preflight expectations: (fixture, expected_exit).
PREFLIGHT_CASES: tuple[tuple[str, int], ...] = (
    ("unsafe_direct", EXIT_FAIL),
    ("safe_2ff", EXIT_PASS),
    ("unsafe_bypass", EXIT_FAIL),
    ("same_clock", EXIT_PASS),
    ("unknown_structure", EXIT_INCONCLUSIVE),
)


def _fixture_dir() -> Path:
    return Path(__file__).resolve().parent / "tests"


def run_preflight() -> list[str]:
    """Execute the mandatory preflight matrix; return failure descriptions."""
    failures: list[str] = []
    for name, expected in PREFLIGHT_CASES:
        rtl = _fixture_dir() / f"{name}.sv"
        if not rtl.exists():
            failures.append(f"{name}: fixture missing")
            continue
        code, report = run_checker(str(rtl), name)
        if code != expected:
            failures.append(
                f"{name}: expected exit {expected}, got {code} "
                f"(status {report.get('status')})"
            )
    return failures


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (also used for ``--preflight``)."""
    parser = argparse.ArgumentParser(description="Structural CDC checker v" + __version__)
    parser.add_argument("--rtl", help="Path to the SystemVerilog design file")
    parser.add_argument("--top", help="Top module name to analyze")
    parser.add_argument("--report", help="Write the machine-readable JSON report here")
    parser.add_argument("--preflight", action="store_true",
                        help="Run the mandatory fixture matrix and exit")
    args = parser.parse_args(argv)

    if args.preflight:
        failures = run_preflight()
        for failure in failures:
            print(f"PREFLIGHT FAIL: {failure}")
        if failures:
            print(f"preflight: {len(failures)} failing case(s)")
            return EXIT_ERROR
        print(f"preflight: all {len(PREFLIGHT_CASES)} cases as expected")
        return EXIT_PASS

    if not args.rtl or not args.top:
        parser.error("--rtl and --top are required (or use --preflight)")
    code, report = run_checker(args.rtl, args.top)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    status = report.get("status")
    print(f"CDC {status} ({args.top}, structural_cdc_checker v{__version__})")
    for crossing in report.get("crossings", []):
        print(
            f"  [{crossing['classification']}] "
            f"{crossing['source']} [{crossing['source_clock']}] -> "
            f"{crossing['destination']} [{crossing['destination_clock']}]"
        )
    for note in report.get("notes", [])[:5]:
        print(f"  note: {note}")
    return code


if __name__ == "__main__":
    sys.exit(main())
