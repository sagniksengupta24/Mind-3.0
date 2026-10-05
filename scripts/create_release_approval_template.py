#!/usr/bin/env python3
"""Create a human-completion template bound to a benchmark summary hash."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mind3.core.release import write_approval_template


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=ROOT / "artifacts" / "benchmark_report" / "benchmark_summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "human_approval.json")
    parser.add_argument("--scope", default="release-evidence")
    args = parser.parse_args()
    path = write_approval_template(args.output, args.summary, args.scope)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
