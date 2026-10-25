"""Best-of-k sampling with verifier selection (Phase 3 measurement, no repair).

For each task draw k independent samples at fixed temperature through the
full fail-closed pipeline WITHOUT repair; select the first fully-verified
candidate. The verifier decides acceptance; sampling only supplies diversity.
Every sample transcript is persisted for audit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def sample_task(
    runner,
    task,
    *,
    k: int,
    temperature: float,
    seed_base: int,
    model: str,
    provider: str,
    liberty: str | None,
    transcripts_dir: Path,
    work_root: Path,
    generation_format: str = "text",
    existing: dict[int, Path] | None = None,
) -> dict:
    """Draw k samples for one task; return selection record (JSON-safe).

    ``existing`` maps sample index -> previously persisted transcript. Those
    samples are reused verbatim instead of being redrawn, so an interrupted
    sweep resumes without spending model calls or altering recorded samples.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    samples: list[dict] = []
    selected_index: int | None = None
    reused = 0
    for i in range(k):
        prior = (existing or {}).get(i)
        if prior is not None:
            payload = json.loads(prior.read_text(encoding="utf-8"))
            if payload.get("task_id") not in (None, task.task_id):
                raise ValueError(f"resume transcript {prior} belongs to {payload.get('task_id')!r}, not {task.task_id!r}")
            passed = bool(payload.get("final_outcome", {}).get("passed"))
            samples.append({"index": i, "seed": seed_base + i, "passed": passed, "path": str(prior)})
            reused += 1
            if passed and selected_index is None:
                selected_index = i
            continue
        transcript = runner.run_live_task(
            task,
            model=model,
            provider=provider,
            max_repairs=0,
            liberty_path=liberty,
            workspace_root=work_root / f"{task.task_id}_s{i}",
            parser_mode="strict",
            decode_temperature=temperature,
            decode_seed=seed_base + i,
            generation_format=generation_format,
        )
        payload = json.loads(transcript.model_dump_json())
        out_path = transcripts_dir / f"{task.task_id}_s{i}.json"
        out_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        passed = bool(payload.get("final_outcome", {}).get("passed"))
        samples.append({"index": i, "seed": seed_base + i, "passed": passed, "path": str(out_path)})
        if passed and selected_index is None:
            selected_index = i
    return {
        "task_id": task.task_id,
        "k": k,
        "temperature": temperature,
        "seed_base": seed_base,
        "samples": samples,
        "selected_index": selected_index,
        "verified": selected_index is not None,
        "reused": reused,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Best-of-k verifier-selected sampling (no repair).")
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--seed-base", type=int, default=100)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--liberty", default=None)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--generation-format", default="text")
    parser.add_argument("--resume", action="store_true", help="Reuse sample transcripts already persisted in --out-dir")
    args = parser.parse_args(argv)

    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from mind3.benchmarks.runner import BenchmarkRunner

    runner = BenchmarkRunner(tasks_file=args.tasks)
    tasks = runner.load_tasks()
    out_dir: Path = args.out_dir
    transcripts_dir = out_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    work_root = out_dir / "run_workspaces"
    work_root.mkdir(parents=True, exist_ok=True)
    selections = []
    for index, task in enumerate(tasks, 1):
        print(f"[{index}/{len(tasks)}] {task.task_id}", flush=True)
        existing: dict[int, Path] = {}
        if args.resume:
            for i in range(args.k):
                candidate_path = transcripts_dir / f"{task.task_id}_s{i}.json"
                if candidate_path.is_file():
                    existing[i] = candidate_path
        selections.append(
            sample_task(
                runner,
                task,
                k=args.k,
                temperature=args.temperature,
                seed_base=args.seed_base,
                model=args.model,
                provider=args.provider,
                liberty=args.liberty,
                transcripts_dir=transcripts_dir,
                work_root=work_root,
                generation_format=args.generation_format,
                existing=existing,
            )
        )
    verified = sum(1 for s in selections for _ in [0] if s["verified"])
    reused = sum(int(s.get("reused") or 0) for s in selections)
    summary = {
        "k": args.k,
        "temperature": args.temperature,
        "seed_base": args.seed_base,
        "model": args.model,
        "tasks": len(selections),
        "verified": verified,
        "reused_samples": reused,
        "selections": selections,
    }
    (out_dir / "selection.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"best-of-{args.k} @ temp {args.temperature}: {verified}/{len(selections)} verified (reused {reused} samples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
