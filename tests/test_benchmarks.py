"""Tests for Mind 3.0 benchmark task specifications and transcript validation."""

import json
from pathlib import Path
import pytest

TASKS_FILE = Path(__file__).parent.parent / "benchmarks" / "tasks.jsonl"


def test_benchmark_tasks_file_exists_and_count() -> None:
    """Verify benchmarks/tasks.jsonl exists and contains exactly 50 tasks."""
    assert TASKS_FILE.exists(), f"Benchmark tasks file {TASKS_FILE} does not exist"
    lines = [line.strip() for line in TASKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 50, f"Expected 50 tasks, got {len(lines)}"


def test_benchmark_tasks_schema_and_categories() -> None:
    """Validate schema, category distribution, and SVA properties for each benchmark task."""
    lines = [line.strip() for line in TASKS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    categories: dict[str, int] = {}
    task_ids: set[str] = set()

    for line in lines:
        task = json.loads(line)
        
        # Required keys
        for key in ["task_id", "category", "name", "natural_language_spec", "expected_ports", "sva_properties", "benchmark_origin"]:
            assert key in task, f"Task {task.get('task_id')} missing key '{key}'"

        # Unique task_id
        tid = task["task_id"]
        assert tid not in task_ids, f"Duplicate task_id '{tid}' found"
        task_ids.add(tid)

        # Honest origin attribution
        assert "inspired by" in task["benchmark_origin"].lower(), f"Task {tid} must state 'inspired by' to avoid unverified benchmark claims"

        # Category counting
        cat = task["category"]
        categories[cat] = categories.get(cat, 0) + 1

        # Port validation
        ports = task["expected_ports"]
        assert len(ports) >= 2, f"Task {tid} must have at least 2 ports"
        for p in ports:
            assert "name" in p and isinstance(p["name"], str) and len(p["name"]) > 0
            assert p["direction"] in ("input", "output", "inout")
            assert isinstance(p["width"], int) and p["width"] >= 1

        # SVA properties validation (2-5 properties per task specification)
        svas = task["sva_properties"]
        assert isinstance(svas, list), f"Task {tid} sva_properties must be a list"
        assert 2 <= len(svas) <= 5, f"Task {tid} expected 2-5 SVA properties, got {len(svas)}"
        for sva in svas:
            assert isinstance(sva, str) and len(sva) > 0
            assert "assert" in sva or "cover" in sva or "assume" in sva

    # Category breakdown assertions
    assert categories.get("FSM") == 15, f"Expected 15 FSM tasks, got {categories.get('FSM')}"
    assert categories.get("Arithmetic") == 15, f"Expected 15 Arithmetic tasks, got {categories.get('Arithmetic')}"
    assert categories.get("Bus Protocol") == 10, f"Expected 10 Bus Protocol tasks, got {categories.get('Bus Protocol')}"
    assert categories.get("Memory Controller") == 10, f"Expected 10 Memory Controller tasks, got {categories.get('Memory Controller')}"
