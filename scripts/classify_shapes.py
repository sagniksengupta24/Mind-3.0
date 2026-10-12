"""C3 analysis: classify raw model-output shapes + funnel from transcripts.

Usage:
  python3 scripts/classify_shapes.py <transcripts_dir> [--out <report_md>]

Reads BenchmarkTranscript JSON files (C2 fields: raw_initial_responses,
decode block, gate_failure_category, repair_attempts) and reports:
  - shape histogram of the FIRST raw response per task
  - funnel: stage0 contract -> strict parse (pass@1 / with-retry) ->
    sim entry -> full verified, each with Wilson 95% CI
  - truncation / prompt-overflow flag rates
  - failure-category histogram

Classification is heuristic and labeled as such; ambiguous raws land in
"other" with a preview for human review.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from mind3.core.driver import _FENCE_REGEX, _MODULE_REGEX


def wilson(n_ok: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = n_ok / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def classify_shape(raw: str | None, decode: dict) -> str:
    if not raw or not raw.strip():
        return "empty"
    text = raw.strip()
    # JSON shapes first: a JSON object without endmodule is a format
    # mismatch (json-other-shape), not a truncation.
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except Exception:
            return "other-json-broken"
        if isinstance(obj, dict) and obj.get("action") == "write_file" and "content" in obj:
            return "json-writefileaction"
        return "json-other-shape"
    truncated_flag = bool(decode.get("any_output_truncated"))
    has_end = "endmodule" in text
    if not has_end:
        return "truncated-or-incomplete" if truncated_flag else "incomplete-no-endmodule"
    if _FENCE_REGEX.search(text):
        n_fences = len(re.findall(r"```", text)) // 2
        prose_outside = bool(re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip())
        if n_fences > 1:
            return "multi-fence"
        return "prose-single-fence" if prose_outside else "fenced"
    if _MODULE_REGEX.fullmatch(text):
        return "raw-module"
    if _MODULE_REGEX.search(text):
        return "prose-bare-module"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcripts_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    files = sorted(args.transcripts_dir.glob("*.json"))
    rows = []
    for path in files:
        try:
            t = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if t.get("is_schema_validation_fixture") or t.get("provider") == "mock":
            continue
        rows.append(t)

    lines: list[str] = [f"# Shape + funnel report: {args.transcripts_dir}", "", f"Real transcripts: {len(rows)}", ""]
    if not rows:
        lines.append("No real transcripts found.")
    else:
        shapes: dict[str, int] = {}
        previews: dict[str, str] = {}
        n_parse1 = n_parse_retry = n_sim = n_full = n_stage0 = 0
        trunc = over = 0
        failcats: dict[str, int] = {}
        for t in rows:
            raws = t.get("raw_initial_responses") or ([t["raw_initial_response"]] if t.get("raw_initial_response") else [])
            decode = t.get("decode", {}) or {}
            repair_raws = [(r.get("raw_repair_response") or "") for r in t.get("repair_attempts", []) or []]
            if not raws and any(repair_raws):
                shape = "empty-initial-transport-failure"
            elif not raws:
                shape = "empty-no-model-call"
            else:
                shape = classify_shape(raws[0], decode)
            shapes[shape] = shapes.get(shape, 0) + 1
            if shape in ("other", "other-json-broken", "incomplete-no-endmodule") and shape not in previews:
                previews[shape] = (raws[0][:300] if raws else "") .replace("\n", "\\n")
            if t.get("contract"):
                n_stage0 += 1
            parsed = bool(t.get("generated_rtl"))
            if parsed:
                n_parse_retry += 1
                if len(raws) <= 1:
                    n_parse1 += 1
            if decode.get("any_output_truncated"):
                trunc += 1
            if decode.get("any_prompt_overflow"):
                over += 1
            reached_sim = False
            for rep in t.get("repair_attempts", []) or []:
                for g in rep.get("gate_reports", []) or []:
                    if isinstance(g, dict) and str(g.get("gate", "")).startswith("Gate 3:"):
                        reached_sim = True
            if reached_sim:
                n_sim += 1
            if (t.get("final_outcome") or {}).get("passed"):
                n_full += 1
            fc = t.get("gate_failure_category") or "NONE_RECORDED"
            failcats[fc] = failcats.get(fc, 0) + 1

        n = len(rows)
        lines.append("## Shape histogram (first raw response)")
        for shape, count in sorted(shapes.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {shape}: {count}/{n}")
        lines.append("")
        for shape, preview in previews.items():
            lines.append(f"Preview [{shape}]: {preview}")
        if previews:
            lines.append("")
        lines.append("## Funnel (transcript-derived, heuristic gate-entry)")
        for name, count in [
            ("stage0 contract present", n_stage0),
            ("strict parse pass@1 (single raw attempt)", n_parse1),
            ("strict parse with-retry (eventual generated_rtl)", n_parse_retry),
            ("sim entry (Gate 3 report observed)", n_sim),
            ("full verified (final_outcome.passed)", n_full),
        ]:
            lo, hi = wilson(count, n)
            lines.append(f"- {name}: {count}/{n} ({count / n:.1%}, Wilson95 [{lo:.1%}, {hi:.1%}])")
        lines.append("")
        lines.append(f"Output-truncated tasks: {trunc}/{n}; prompt-overflow tasks: {over}/{n}")
        lines.append("")
        lines.append("## Failure-category histogram (initial)")
        for cat, count in sorted(failcats.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {cat}: {count}")

    report = "\n".join(lines) + "\n"
    print(report)
    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
