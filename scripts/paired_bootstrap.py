#!/usr/bin/env python3
"""Paired bootstrap comparison of two benchmark transcript directories (R2).

Task = unit of resampling; repeats are averaged within task. Reports the
contender-minus-baseline effect with a 95% bootstrap CI and flags the
pre-declared minimum detectable effect (default: dev-20 MDE 0.25).

Usage:
    python3 scripts/paired_bootstrap.py --baseline-dir A --contender-dir B \
        [--metric full_verified] [--resamples 10000] [--seed 42] [--mde 0.25] \
        [--out result.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mind3.benchmarks.paired import MDE_DEV20, compare_dirs, format_human


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task-level paired bootstrap comparison.")
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--contender-dir", type=Path, required=True)
    parser.add_argument("--metric", choices=("full_verified", "passed"), default="full_verified")
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mde", type=float, default=MDE_DEV20)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        result = compare_dirs(
            args.baseline_dir,
            args.contender_dir,
            metric=args.metric,
            resamples=args.resamples,
            seed=args.seed,
            mde=args.mde,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"PAIRED_COMPARISON_ERROR: {exc}", file=sys.stderr)
        return 2
    print(format_human(result))
    if args.out is not None:
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
