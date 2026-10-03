#!/usr/bin/env python3
"""Export a release evidence bundle only after human approval."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mind3.core.release import load_release_approval, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "artifacts" / "benchmark_report")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "release_bundle")
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--min-tasks", type=int, default=100)
    parser.add_argument("--min-functional", type=float, default=0.70)
    parser.add_argument("--min-verified", type=float, default=0.40)
    args = parser.parse_args()

    source = args.source.resolve()
    summary_path = source / "benchmark_summary.json"
    if not summary_path.is_file():
        raise SystemExit(f"RELEASE_BLOCKED: missing {summary_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    tier = summary.get("evidence_tier", "diagnostic")
    if tier != "release-eligible":
        raise SystemExit(f"RELEASE_BLOCKED: evidence tier is {tier!r}, must be 'release-eligible'")
    if args.min_tasks < 100:
        raise SystemExit(f"RELEASE_BLOCKED: release threshold cannot be lowered below 100 (got {args.min_tasks})")

    real_count = int(summary.get("actual_real_transcripts", summary.get("real_transcript_count", 0)))
    functional = float(summary.get("functional_pass_rate", 0.0))
    verified = float(summary.get("full_verified_pass_rate", 0.0))
    if real_count < 100 or real_count < args.min_tasks:
        raise SystemExit(f"RELEASE_BLOCKED: real tasks {real_count} < {max(100, args.min_tasks)}")
    if functional < args.min_functional:
        raise SystemExit(f"RELEASE_BLOCKED: functional rate {functional:.1%} < {args.min_functional:.1%}")
    if verified < args.min_verified:
        raise SystemExit(f"RELEASE_BLOCKED: full verified rate {verified:.1%} < {args.min_verified:.1%}")

    approval = load_release_approval(args.approval, sha256_file(summary_path))
    out = args.output.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("benchmark_summary.json", "benchmark_report.md", "benchmark_report.html"):
        src = source / name
        if not src.is_file():
            raise SystemExit(f"RELEASE_BLOCKED: missing report artifact {src}")
        shutil.copy2(src, out / name)
    shutil.copy2(args.approval.resolve(), out / "human_approval.json")
    (out / "release_manifest.json").write_text(
        json.dumps(
            {
                "status": "HUMAN_APPROVED_EVIDENCE_BUNDLE",
                "reviewer": approval.reviewer,
                "approval_id": approval.approval_id,
                "approved_at": approval.approved_at,
                "scope": approval.scope,
                "benchmark_summary_sha256": sha256_file(out / "benchmark_summary.json"),
                "thresholds": {"min_tasks": args.min_tasks, "min_functional": args.min_functional, "min_verified": args.min_verified},
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
