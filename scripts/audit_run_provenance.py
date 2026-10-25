"""Audit provenance and parse-budget accounting of a transcript directory.

Motivation: two earlier "HEAD baseline" runs were cited as commit 66d9112 but
their transcripts prove they executed the pre-66d9112 driver (every task shows
``initial_parse_attempts=1`` with a single model call, and every failure
terminates on a spurious parse-budget exhaustion). This script makes that
class of mislabeling mechanically detectable.

Read-only. Exit code 1 when any transcript is flagged; 0 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def audit_transcript(payload: dict[str, Any]) -> dict[str, Any]:
    """Return provenance/accounting observations for one benchmark transcript."""
    decode = payload.get("decode") or {}
    environment = payload.get("environment") or {}
    provenance = environment.get("code_provenance") or {}
    calls = decode.get("calls_observed")
    parse_attempts = decode.get("parse_attempts")
    final = payload.get("final_outcome") or {}

    flags: list[str] = []
    # Pre-66d9112 driver incremented the parse counter on every model call, so
    # parse_attempts == calls_observed (even for clean first-try parses). A
    # post-fix run only counts genuine parse failures.
    if isinstance(parse_attempts, int) and isinstance(calls, int) and calls > 0:
        if parse_attempts == calls:
            flags.append("PREFIX_PARSE_ACCOUNTING")
        elif parse_attempts > calls:
            flags.append("IMPOSSIBLE_PARSE_ACCOUNTING")
    if (
        final.get("failure_category") == "RESPONSE_PARSE_FAILURE"
        and parse_attempts == 0
    ):
        flags.append("PARSE_TERMINAL_WITHOUT_PARSE_ATTEMPTS")
    if not provenance:
        flags.append("NO_CODE_PROVENANCE")

    return {
        "task_id": payload.get("task_id"),
        "git_commit": provenance.get("git_commit"),
        "git_dirty": provenance.get("git_dirty"),
        "calls_observed": calls,
        "parse_attempts": parse_attempts,
        "terminal_category": final.get("failure_category"),
        "passed": bool(final.get("passed")),
        "flags": flags,
    }


def audit_dir(transcripts_dir: Path) -> dict[str, Any]:
    rows = []
    for path in sorted(Path(transcripts_dir).glob("*.json")):
        try:
            rows.append(audit_transcript(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"task_id": path.stem, "flags": [f"UNREADABLE:{exc}"]})
    commits = sorted({str(r.get("git_commit")) for r in rows if r.get("git_commit")})
    dirty = sorted({str(r.get("git_dirty")) for r in rows if r.get("git_dirty") is not None})
    flagged = [r for r in rows if r.get("flags")]
    return {
        "transcripts": len(rows),
        "verified": sum(1 for r in rows if r.get("passed")),
        "git_commits": commits,
        "git_dirty_values": dirty,
        "flagged": flagged,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit run provenance and parse-budget accounting.")
    parser.add_argument("transcripts", type=Path)
    parser.add_argument("--json", action="store_true", help="Emit the full audit as JSON")
    args = parser.parse_args(argv)

    result = audit_dir(args.transcripts)
    if args.json:
        print(json.dumps(result, indent=1, sort_keys=True))
    else:
        print(f"transcripts={result['transcripts']} verified={result['verified']}")
        print(f"git_commits={result['git_commits'] or ['ABSENT']} dirty={result['git_dirty_values'] or ['ABSENT']}")
        for row in result["rows"]:
            mark = "!" if row.get("flags") else " "
            print(
                f"{mark} {row['task_id']}: commit={row.get('git_commit')} "
                f"calls={row.get('calls_observed')} parse_attempts={row.get('parse_attempts')} "
                f"terminal={row.get('terminal_category')} flags={row.get('flags')}"
            )
    return 1 if result["flagged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
