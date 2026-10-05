"""Unit tests for ContentAddressedCache and FineTuningDatasetExporter."""

import json
from pathlib import Path

from mind3.core.cache import ContentAddressedCache
from mind3.core.dataset import FineTuningDatasetExporter, HardwareTrajectoryRecord


def test_content_addressed_cache(tmp_path: Path) -> None:
    """Verify ContentAddressedCache deterministic hashing, hit/miss, and eviction."""
    cache_dir = tmp_path / "cache"
    cache = ContentAddressedCache(cache_dir)

    src1 = tmp_path / "mod.sv"
    src1.write_text("module mod(); endmodule", encoding="utf-8")

    key1 = cache.compute_key([src1], "{}", "Gate 1: Yosys", "-O3")
    key2 = cache.compute_key([src1], "{}", "Gate 1: Yosys", "-O3")
    assert key1 == key2

    # Miss before put
    assert cache.get(key1) is None
    assert cache.stats["misses"] == 1
    assert cache.stats["hits"] == 0

    # Put and Hit
    cache.put(key1, "Gate 1: Yosys", {"passed": True, "cells": 12})
    hit_res = cache.get(key1)
    assert hit_res is not None
    assert hit_res["passed"] is True
    assert hit_res["cells"] == 12
    assert cache.stats["hits"] == 1

    # Clear
    removed = cache.clear()
    assert removed == 1
    assert cache.get(key1) is None


def test_dataset_exporter(tmp_path: Path) -> None:
    """Verify FineTuningDatasetExporter JSONL and ShareGPT formatting."""
    exporter = FineTuningDatasetExporter()

    traj = HardwareTrajectoryRecord(
        session_id="test_sess_01",
        module_name="fifo",
        functional_spec="Synchronous FIFO queue with 8-bit width",
        interface_contract_json='{"module_name": "fifo"}',
        initial_rtl="module fifo(); /* bug */ endmodule",
        repair_turns=[
            {
                "failing_rtl": "module fifo(); /* bug */ endmodule",
                "error_feedback": "LATCH_INFERRED: dlatch on full signal",
                "repaired_rtl": "module fifo(input clk); reg full; always @(posedge clk) full <= 0; endmodule",
            }
        ],
        final_repaired_rtl="module fifo(input clk); reg full; always @(posedge clk) full <= 0; endmodule",
        silicon_signoff_passed=True,
        timing_wns_ps=120.0,
        branch_coverage=100.0,
    )
    exporter.record(traj)

    # Export JSONL
    jsonl_path = tmp_path / "dataset.jsonl"
    count_jsonl = exporter.export_jsonl(jsonl_path)
    assert count_jsonl == 3  # contract + rtl + repair
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        entry = json.loads(line)
        assert "instruction" in entry
        assert "input" in entry
        assert "output" in entry
        assert entry["module"] == "fifo"

    # Export ShareGPT
    sharegpt_path = tmp_path / "sharegpt.jsonl"
    count_sg = exporter.export_sharegpt(sharegpt_path)
    assert count_sg == 1
    sg_entry = json.loads(sharegpt_path.read_text(encoding="utf-8").strip())
    assert "conversations" in sg_entry
    assert len(sg_entry["conversations"]) == 6
