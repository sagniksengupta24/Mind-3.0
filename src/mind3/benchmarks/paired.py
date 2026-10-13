"""Task-level paired bootstrap comparison for benchmark configs.

Unit of resampling: the TASK. Repeats of the same task are averaged within the
task first; then task-level paired differences (contender minus baseline) are
bootstrapped to report an effect with a 95% percentile confidence interval.

New file for R2 (harness-side only; no verifier changes). Standard library only.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


# Pre-declared minimum detectable effect for the 20-task development set.
# Derivation: for paired binary outcomes the standard error of the mean paired
# difference is at most 0.5/sqrt(20) ~= 0.112, so a 95% interval has half-width
# ~= 0.22 in the worst (uncorrelated) case; pairing only narrows it. An effect
# smaller than ~5/20 tasks cannot be distinguished from noise on dev-20, so the
# pre-declared MDE is 0.25 absolute. Callers may override via --mde.
MDE_DEV20 = 0.25

SUPPORTED_METRICS = ("full_verified", "passed")


def metric_of(transcript: Mapping[str, Any], metric: str) -> float:
    """Score one transcript 0.0/1.0 for a supported metric.

    full_verified: final_outcome.passed AND final_outcome.silicon_verified.
    passed: final_outcome.passed.
    """
    if metric not in SUPPORTED_METRICS:
        raise ValueError(f"unsupported metric {metric!r}; expected one of {SUPPORTED_METRICS}")
    outcome = transcript.get("final_outcome") or {}
    if not isinstance(outcome, dict):
        return 0.0
    passed = bool(outcome.get("passed"))
    if metric == "passed":
        return 1.0 if passed else 0.0
    return 1.0 if (passed and bool(outcome.get("silicon_verified"))) else 0.0


def load_scores(transcript_dir: Path | str, metric: str) -> dict[str, list[float]]:
    """Map task_id -> list of per-repeat scores from *.json transcripts in a dir."""
    src = Path(transcript_dir)
    if not src.is_dir():
        raise FileNotFoundError(f"transcript directory not found: {src}")
    scores: dict[str, list[float]] = defaultdict(list)
    files = sorted(src.glob("*.json"))
    if not files:
        raise ValueError(f"no transcript JSON files in {src}")
    for path in files:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"unreadable transcript {path}: {exc}")
        task_id = record.get("task_id")
        if not task_id:
            raise ValueError(f"transcript {path} has no task_id")
        scores[str(task_id)].append(metric_of(record, metric))
    return dict(scores)


def paired_bootstrap(
    baseline: Mapping[str, list[float] | float],
    contender: Mapping[str, list[float] | float],
    *,
    resamples: int = 10000,
    seed: int = 42,
    mde: float = MDE_DEV20,
) -> dict[str, Any]:
    """Paired bootstrap over tasks. Repeats (lists) are averaged within task.

    Only tasks present in BOTH inputs are paired; others are reported and excluded.
    Returns effect (mean paired difference, contender minus baseline), the 95%
    percentile CI, per-task details, and verdict components (ci_excludes_zero,
    meets_mde). Deterministic given `seed`.
    """
    if resamples < 100:
        raise ValueError("resamples must be >= 100 for a stable interval")

    def mean_of(value: list[float] | float) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        items = list(value)
        if not items:
            raise ValueError("empty repeat list")
        return sum(items) / len(items)

    paired: list[tuple[str, float, float]] = []
    baseline_only: list[str] = []
    contender_only: list[str] = []
    for task_id in sorted(set(baseline) | set(contender)):
        in_base = task_id in baseline
        in_cont = task_id in contender
        if in_base and in_cont:
            paired.append((task_id, mean_of(baseline[task_id]), mean_of(contender[task_id])))
        elif in_base:
            baseline_only.append(task_id)
        else:
            contender_only.append(task_id)
    if not paired:
        raise ValueError("no tasks present in both inputs; cannot pair")
    diffs = [c - b for _, b, c in paired]
    effect = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    n = len(diffs)
    boot_means: list[float] = []
    for _ in range(resamples):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[max(0, math.ceil(0.025 * resamples) - 1)]
    hi = boot_means[min(resamples - 1, math.floor(0.975 * resamples))]
    return {
        "metric": None,
        "tasks_paired": n,
        "tasks_baseline_only": sorted(baseline_only),
        "tasks_contender_only": sorted(contender_only),
        "effect": round(effect, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "ci_excludes_zero": bool(lo > 0 or hi < 0),
        "mde": mde,
        "meets_mde": bool(abs(effect) >= mde),
        "resamples": resamples,
        "seed": seed,
        "per_task": [
            {"task_id": tid, "baseline": round(b, 4), "contender": round(c, 4), "diff": round(c - b, 4)}
            for tid, b, c in paired
        ],
    }


def compare_dirs(
    baseline_dir: Path | str,
    contender_dir: Path | str,
    *,
    metric: str = "full_verified",
    resamples: int = 10000,
    seed: int = 42,
    mde: float = MDE_DEV20,
) -> dict[str, Any]:
    """Load two transcript dirs and return the paired bootstrap comparison."""
    base_scores = load_scores(baseline_dir, metric)
    cont_scores = load_scores(contender_dir, metric)
    result = paired_bootstrap(base_scores, cont_scores, resamples=resamples, seed=seed, mde=mde)
    result["metric"] = metric
    result["baseline_dir"] = str(baseline_dir)
    result["contender_dir"] = str(contender_dir)
    return result


def format_human(result: Mapping[str, Any]) -> str:
    """One human-readable summary block for stdout/reports."""
    lines = [
        f"metric={result.get('metric')} tasks_paired={result.get('tasks_paired')} "
        f"resamples={result.get('resamples')} seed={result.get('seed')}",
        f"effect(contender-baseline)={result.get('effect'):+.4f} "
        f"95% CI=[{result['ci95'][0]:+.4f}, {result['ci95'][1]:+.4f}]",
        f"ci_excludes_zero={result.get('ci_excludes_zero')} "
        f"mde={result.get('mde')} meets_mde={result.get('meets_mde')}",
    ]
    if result.get("tasks_baseline_only"):
        lines.append(f"baseline-only (excluded): {result['tasks_baseline_only']}")
    if result.get("tasks_contender_only"):
        lines.append(f"contender-only (excluded): {result['tasks_contender_only']}")
    lines.append("dev results are optimistic by construction; no release claim follows.")
    return "\n".join(lines)
