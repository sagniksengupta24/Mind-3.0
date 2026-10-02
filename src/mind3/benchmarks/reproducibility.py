"""Reproducible benchmark execution, cryptographic manifest generation, and HTML reporting.

Implements Section 9 & 10 of the Mind 3.0 specification:
Produces:
results/
├── summary.json
├── report.html
├── failures.json
├── transcripts/
├── evidence/
├── tool_versions.json
├── environment.json
├── benchmark_manifest.json
└── baseline_comparison.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..core.failure_taxonomy import FailureCategory, classify_failure
from ..eda.smoke_test import run_eda_smoke_test
from .baselines import (
    BaselineComparisonReport,
    BaselineComparisonRunner,
    BaselineType,
    _wilson_ci95,
)
from .runner import BenchmarkRunner, BenchmarkTask, sha256_file


def get_git_commit_sha(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"
    return "UNKNOWN_COMMIT"


def build_html_report(
    summary: dict[str, Any],
    baselines: dict[str, Any],
    failures: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> str:
    """Build a comprehensive, self-contained HTML report with modern CSS."""
    baseline_rows = []
    for b_name, b_data in baselines.items():
        ci = b_data.get("full_verified_ci95", [0.0, 0.0])
        baseline_rows.append(f"""
        <tr>
            <td style="font-weight: 600;">{b_name}</td>
            <td>{b_data.get('task_count', 0)}</td>
            <td>{b_data.get('compile_pass_rate', 0.0):.1%}</td>
            <td>{b_data.get('simulation_pass_rate', 0.0):.1%}</td>
            <td>{b_data.get('formal_pass_rate', 0.0):.1%}</td>
            <td style="font-weight: bold; color: #10b981;">{b_data.get('full_verified_pass_rate', 0.0):.1%} [{ci[0]:.1%}, {ci[1]:.1%}]</td>
            <td>{b_data.get('repair_success_rate', 0.0):.1%}</td>
            <td>{b_data.get('mean_repair_attempts', 0.0):.1f}</td>
            <td>${b_data.get('mean_cost_usd', 0.0):.4f}</td>
            <td>{b_data.get('mean_runtime_sec', 0.0):.2f}s</td>
        </tr>
        """)

    failure_items = []
    for cat, count in summary.get("failure_categories", {}).items():
        failure_items.append(f"""
        <div style="background: #1e293b; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: flex; justify-content: space-between;">
            <span style="font-family: monospace; color: #f87171;">{cat}</span>
            <span style="font-weight: 600; color: #f1f5f9;">{count}</span>
        </div>
        """)

    failure_block = "".join(failure_items) if failure_items else "<p style='color: #94a3b8;'>Zero failures observed across evaluated real tasks.</p>"

    task_rows = []
    for f in failures[:50]:
        task_rows.append(f"""
        <tr>
            <td style="font-family: monospace;">{f.get('task_id', '')}</td>
            <td><span style="background: #ef444420; color: #ef4444; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.85em;">{f.get('canonical_category', '')}</span></td>
            <td>{f.get('gate_name', 'Verification')}</td>
            <td style="font-size: 0.85em; color: #94a3b8;">{f.get('deterministic_evidence', '')}</td>
        </tr>
        """)

    task_table = "".join(task_rows) if task_rows else "<tr><td colspan='4' style='text-align: center; color: #94a3b8;'>No recorded failure cases</td></tr>"

    ci_verified = summary.get("full_verified_ci95", [0.0, 0.0])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mind 3.0 Real Benchmark Evaluation Report</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-hover: #334155;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 24px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        header {{
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        h1 {{ margin: 0 0 8px 0; font-size: 2rem; color: var(--primary); }}
        .badge {{
            display: inline-block;
            background: #0284c7;
            color: #fff;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 500;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .metric-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 16px;
        }}
        .metric-label {{
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .metric-value {{
            font-size: 1.75rem;
            font-weight: 700;
            margin-top: 4px;
            color: var(--text);
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        h2 {{
            margin-top: 0;
            font-size: 1.25rem;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
            color: var(--text);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: #0f172a80;
            color: var(--text-muted);
            font-weight: 600;
        }}
        pre {{
            background: #090d16;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
<div class="container">
    <header>
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <h1>Mind 3.0 RTL Benchmark Report</h1>
            <span class="badge">Suite: {manifest.get('benchmark_suite', 'heldout-v1')}</span>
        </div>
        <p style="color: var(--text-muted); margin: 4px 0 0 0;">
            Evaluated at: <strong>{summary.get('generated_at', '')}</strong> | Commit: <code>{manifest.get('git_commit_sha', 'UNKNOWN')[:8]}</code> | Seed: <code>{manifest.get('seed', 42)}</code>
        </p>
    </header>

    <h2>1. Overall Results</h2>
    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-label">Tasks Attempted / Done</div>
            <div class="metric-value">{summary.get('real_transcript_count', 0)} / {summary.get('real_transcript_count', 0)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Compile Pass Rate</div>
            <div class="metric-value" style="color: #38bdf8;">{summary.get('compile_pass_rate', 0.0):.1%}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Simulation Pass Rate</div>
            <div class="metric-value" style="color: #818cf8;">{summary.get('simulation_pass_rate', 0.0):.1%}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Formal BMC Pass Rate</div>
            <div class="metric-value" style="color: #a78bfa;">{summary.get('formal_pass_rate', 0.0):.1%}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Full Verified Pass Rate</div>
            <div class="metric-value" style="color: #10b981;">{summary.get('full_verified_pass_rate', 0.0):.1%}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">95% CI: [{ci_verified[0]:.1%}, {ci_verified[1]:.1%}]</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Repair Success Rate</div>
            <div class="metric-value" style="color: #fbbf24;">{summary.get('repair_success_rate', 0.0):.1%}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Average Runtime</div>
            <div class="metric-value">{summary.get('mean_runtime_sec', 0.0):.2f}s</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Average Cost</div>
            <div class="metric-value">${summary.get('mean_cost_usd', 0.0):.4f}</div>
        </div>
    </div>

    <div class="card">
        <h2>2. Baseline Comparison</h2>
        <table>
            <thead>
                <tr>
                    <th>Architecture</th>
                    <th>Tasks</th>
                    <th>Compile</th>
                    <th>Simulation</th>
                    <th>Formal</th>
                    <th>Full Verified (95% CI)</th>
                    <th>Repair Rate</th>
                    <th>Avg Repairs</th>
                    <th>Avg Cost</th>
                    <th>Avg Runtime</th>
                </tr>
            </thead>
            <tbody>
                {''.join(baseline_rows)}
            </tbody>
        </table>
    </div>

    <div class="card">
        <h2>3. Failure Analysis (Deterministic Taxonomy)</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px;">
            {failure_block}
        </div>
    </div>

    <div class="card">
        <h2>4. Individual Task Evidence & Diagnostics</h2>
        <table>
            <thead>
                <tr>
                    <th>Task ID</th>
                    <th>Failure Category</th>
                    <th>Failing Gate</th>
                    <th>Deterministic Tool Evidence</th>
                </tr>
            </thead>
            <tbody>
                {task_table}
            </tbody>
        </table>
    </div>

    <div class="card">
        <h2>5. Provenance & Cryptographic Manifest</h2>
        <pre><code>{json.dumps(manifest, indent=2)}</code></pre>
    </div>
</div>
</body>
</html>
"""


def execute_full_benchmark(
    suite_dir: Path | str,
    output_dir: Path | str,
    seed: int = 42,
    model: str = "gemini-1.5-pro",
    provider: str = "mock",
    sample_size: int | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    liberty_path: str | list[str] | None = None,
) -> Path:
    """Run full benchmark, baselines, and emit all required artifacts in output_dir."""
    repo_root = Path(__file__).resolve().parents[3]
    suite_path = Path(suite_dir).resolve()
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    tasks_file = suite_path / "tasks.jsonl" if (suite_path / "tasks.jsonl").is_file() else suite_path
    if not tasks_file.is_file():
        raise FileNotFoundError(f"Benchmark tasks file not found: {tasks_file}")

    # Load tasks
    tasks: list[BenchmarkTask] = []
    with tasks_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(BenchmarkTask.model_validate_json(line))

    if sample_size and sample_size < len(tasks):
        tasks = tasks[:sample_size]

    task_set_sha = sha256_file(tasks_file)
    git_sha = get_git_commit_sha(repo_root)

    # 1. Probe EDA environment
    smoke_report = run_eda_smoke_test()
    tool_versions = {k: v.version_string for k, v in smoke_report.tools.items()}

    # 2. Run Three Baselines only with a live model provider. A mock provider is an explicit
    # evidence-blocked mode used by unit tests; it must never emit synthetic benchmark passes.
    if provider == "mock":
        cmp_report = BaselineComparisonReport(
            task_set_sha256=task_set_sha,
            benchmark_suite=suite_path.name,
            evaluated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            seed=seed,
            baselines={},
            task_runs=[],
        )
        execution_status = "BLOCKED_MOCK_PROVIDER"
        execution_message = "No performance benchmark executed: provider='mock' is not benchmark evidence."
    else:
        # Live performance numbers are only valid when the real verifier toolchain is runnable.
        # Do not spend model calls and do not emit zero-valued benchmark rows when prerequisites are absent.
        from .runner import check_live_prerequisites
        missing_live_prerequisites = check_live_prerequisites()
        if missing_live_prerequisites:
            raise RuntimeError(
                "LIVE_BENCHMARK_PREREQUISITES_MISSING: " + ", ".join(missing_live_prerequisites)
            )
        baseline_runner = BaselineComparisonRunner(
            tasks,
            model=model,
            provider=provider,
            seed=seed,
            api_key=api_key,
            base_url=base_url,
            liberty_path=liberty_path,
        )
        cmp_report = baseline_runner.execute_comparison()
        execution_status = "COMPLETED"
        execution_message = "Live model baseline comparison executed."

    # 3. Create subdirectories
    transcripts_dir = out / "transcripts"
    evidence_dir = out / "evidence"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # 4. Generate individual task evidence and transcripts
    failures_list: list[dict[str, Any]] = []
    mind_runs = [r for r in cmp_report.task_runs if r.baseline == BaselineType.MIND_3]

    for run in mind_runs:
        t_data = run.model_dump(mode="json")
        (transcripts_dir / f"{run.task_id}.json").write_text(json.dumps(t_data, indent=2) + "\n", encoding="utf-8")
        if not run.full_verified_pass:
            failures_list.append({
                "task_id": run.task_id,
                "canonical_category": run.failure_category.value,
                "gate_name": "SiliconSignoffVerifier",
                "deterministic_evidence": f"Run failed verification with run_hash {run.run_hash[:16]}",
                "run_hash": run.run_hash,
            })
            (evidence_dir / f"{run.task_id}_failure.log").write_text(
                f"Task: {run.task_id}\nCategory: {run.failure_category.value}\nHash: {run.run_hash}\n",
                encoding="utf-8",
            )

    # 5. Build summary.json
    n_total = len(mind_runs)
    n_comp = sum(1 for r in mind_runs if r.compile_pass)
    n_sim = sum(1 for r in mind_runs if r.simulation_pass)
    n_form = sum(1 for r in mind_runs if r.formal_pass)
    n_full = sum(1 for r in mind_runs if r.full_verified_pass)
    n_rep = sum(1 for r in mind_runs if r.repair_success)
    fails_count = Counter(r.failure_category.value for r in mind_runs if not r.full_verified_pass)
    ci_low, ci_high = _wilson_ci95(n_full, n_total)

    summary_data = {
        "execution_status": execution_status,
        "execution_message": execution_message,
        "performance_claim_valid": provider != "mock" and n_total > 0,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "task_set_path": str(tasks_file),
        "task_set_sha256": task_set_sha,
        "transcript_count": n_total,
        "real_transcript_count": n_total if provider != "mock" else 0,
        "fixture_count": 0,
        "compile_pass_count": n_comp,
        "simulation_pass_count": n_sim,
        "formal_pass_count": n_form,
        "full_verified_pass_count": n_full,
        "repair_success_count": n_rep,
        "compile_pass_rate": round(n_comp / n_total, 4) if n_total else 0.0,
        "simulation_pass_rate": round(n_sim / n_total, 4) if n_total else 0.0,
        "formal_pass_rate": round(n_form / n_total, 4) if n_total else 0.0,
        "full_verified_pass_rate": round(n_full / n_total, 4) if n_total else 0.0,
        "repair_success_rate": round(n_rep / n_total, 4) if n_total else 0.0,
        "full_verified_ci95": [ci_low, ci_high],
        "mean_runtime_sec": round(sum(r.runtime_sec for r in mind_runs) / n_total, 3) if n_total else 0.0,
        "mean_cost_usd": round(sum(r.estimated_cost_usd for r in mind_runs) / n_total, 5) if n_total else 0.0,
        "failure_categories": dict(fails_count),
        "tool_versions": tool_versions,
    }

    # Write files
    (out / "summary.json").write_text(json.dumps(summary_data, indent=2) + "\n", encoding="utf-8")
    (out / "failures.json").write_text(json.dumps(failures_list, indent=2) + "\n", encoding="utf-8")
    (out / "tool_versions.json").write_text(json.dumps(tool_versions, indent=2) + "\n", encoding="utf-8")
    (out / "environment.json").write_text(
        json.dumps(
            {
                "platform": platform.system(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "all_core_tools_passed": smoke_report.all_smoke_tests_passed,
                "summary": smoke_report.summary_message,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (out / "baseline_comparison.json").write_text(
        json.dumps(cmp_report.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )

    manifest_data = {
        "benchmark_suite": suite_path.name,
        "task_set_sha256": task_set_sha,
        "task_count": len(tasks),
        "real_task_count": n_total,
        "requested_task_count": len(tasks),
        "execution_status": execution_status,
        "model_version": model,
        "provider": provider,
        "performance_claim_valid": provider != "mock" and n_total > 0,
        "seed": seed,
        "git_commit_sha": git_sha,
        "environment": {
            "platform": platform.system(),
            "python": platform.python_version(),
            "tool_versions": tool_versions,
        },
        "summary_sha256": sha256_file(out / "summary.json"),
        "baseline_comparison_sha256": sha256_file(out / "baseline_comparison.json"),
        "failures_sha256": sha256_file(out / "failures.json"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out / "benchmark_manifest.json").write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    html_content = build_html_report(
        summary_data,
        {k: v.model_dump() for k, v in cmp_report.baselines.items()},
        failures_list,
        manifest_data,
    )
    (out / "report.html").write_text(html_content, encoding="utf-8")

    return out
