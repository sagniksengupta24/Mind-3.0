"""Command-line interface for Mind 3.0.

Provides:
- `mind3 benchmark --suite heldout-v1 --seed 42`
- `mind3 smoke-test`
- `mind3 negative-controls`
- `mind3 bundle export --approval <file>`
- `mind3 verify --workspace <path>`
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .benchmarks.reproducibility import execute_full_benchmark
from .eda.smoke_test import run_eda_smoke_test


def cmd_benchmark(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    suite_dir = repo_root / "benchmarks" / args.suite
    if not suite_dir.exists():
        # Fallback to direct path
        suite_dir = Path(args.suite).resolve()
        if not suite_dir.exists():
            print(f"Error: benchmark suite directory not found: {suite_dir}", file=sys.stderr)
            return 1

    out_dir = Path(args.output).resolve() if args.output else repo_root / "results"
    print(f"=== Mind 3.0 Benchmark Execution ===")
    print(f"Suite: {suite_dir}")
    print(f"Output: {out_dir}")
    print(f"Seed: {args.seed}")
    print(f"Model: {args.model}")
    print(f"Parser mode: {getattr(args, 'parser_mode', 'strict')}")

    try:
        out_path = execute_full_benchmark(
            suite_dir=suite_dir,
            output_dir=out_dir,
            seed=args.seed,
            model=args.model,
            provider=args.provider,
            sample_size=args.sample_size,
            api_key=args.api_key,
            base_url=args.base_url,
            liberty_path=args.liberty,
            required_min_tasks=args.min_tasks if getattr(args, "min_tasks", None) is not None else 100,
            diagnostic=getattr(args, "diagnostic", False),
            parser_mode=getattr(args, "parser_mode", "strict"),
        )
        print(f"\nBenchmark completed successfully!")
        print(f"Artifacts generated in: {out_path}")
        print(f"  - Summary:             {out_path / 'summary.json'}")
        print(f"  - HTML Report:         {out_path / 'report.html'}")
        print(f"  - Failures:            {out_path / 'failures.json'}")
        print(f"  - Manifest:            {out_path / 'benchmark_manifest.json'}")
        print(f"  - Baseline Comparison: {out_path / 'baseline_comparison.json'}")
        return 0
    except Exception as exc:
        print(f"Benchmark execution failed: {exc}", file=sys.stderr)
        return 1


def cmd_smoke_test(args: argparse.Namespace) -> int:
    report = run_eda_smoke_test(require_full_suite=args.require_full)
    print("=== Mind 3.0 EDA Toolchain Smoke Test ===")
    print(f"Platform: {report.platform} ({report.architecture})")
    print(f"Python:   {report.python_version}")
    for name, status in report.tools.items():
        sym = "✓" if status.functional_smoke_passed else ("?" if status.available else "✗")
        print(f"  [{sym}] {name:10s} : version={status.version_string:35s} | {status.details}")
    print(f"Summary: {report.summary_message}")
    if report.all_smoke_tests_passed:
        print("\nAll required EDA tools passed functional smoke verification.")
        return 0
    else:
        print("\nWarning: Some tools are missing or failed smoke checks.", file=sys.stderr)
        return 1 if args.strict else 0


def cmd_negative_controls(args: argparse.Namespace) -> int:
    import subprocess
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "run_negative_controls.py"
    cmd = [sys.executable, str(script)]
    if args.require_live:
        cmd.append("--require-live")
    return subprocess.run(cmd).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mind3",
        description="Mind 3.0 Fail-Closed RTL Agent CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # benchmark
    p_bench = subparsers.add_parser("benchmark", help="Run reproducible RTL benchmark suite")
    p_bench.add_argument("--suite", default="heldout-v1", help="Benchmark suite name or path")
    p_bench.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    p_bench.add_argument("--model", default="qwen2.5-coder:7b", help="Model identifier")
    p_bench.add_argument("--provider", choices=("ollama", "openrouter", "mock"), default="ollama", help="LLM provider; mock is evidence-blocked and never counts as benchmark performance")
    p_bench.add_argument("--api-key", default=None, help="OpenRouter API key (or environment variable)")
    p_bench.add_argument("--base-url", default=None, help="LLM provider base URL")
    p_bench.add_argument("--liberty", action="append", default=None, help="Liberty file(s) for timing")
    p_bench.add_argument("--output", type=Path, default=None, help="Output directory (default: results/)")
    p_bench.add_argument("--sample-size", type=int, default=None, help="Limit number of tasks to run")
    p_bench.add_argument("--diagnostic", action="store_true", help="Explicitly mark run as diagnostic/development mode (not release-eligible)")
    p_bench.add_argument("--min-tasks", type=int, default=None, help="Minimum tasks required for release qualification (default: 100)")
    p_bench.add_argument("--parser-mode", choices=("strict", "lenient"), default="strict", help="Model-response parser mode: strict (default) or lenient opt-in recovery for local models; recorded in traces and summaries")
    p_bench.set_defaults(func=cmd_benchmark)

    # smoke-test
    p_smoke = subparsers.add_parser("smoke-test", help="Test live EDA toolchain availability")
    p_smoke.add_argument("--require-full", action="store_true", help="Require OpenSTA and OpenROAD")
    p_smoke.add_argument("--strict", action="store_true", help="Exit 1 if any tool is missing")
    p_smoke.set_defaults(func=cmd_smoke_test)

    # negative-controls
    p_neg = subparsers.add_parser("negative-controls", help="Run intentional-bug negative-control suite")
    p_neg.add_argument("--require-live", action="store_true", help="Require live EDA tools without skips")
    p_neg.set_defaults(func=cmd_negative_controls)

    parsed = parser.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
