import json
from pathlib import Path


def test_negative_control_corpus_is_complete_and_explicitly_expected() -> None:
    root = Path(__file__).parent / "negative_controls"
    manifest_file = root / "negative_controls_manifest.json"
    assert manifest_file.is_file(), "negative_controls_manifest.json must exist"

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(manifest) >= 15, f"Expected at least 15 negative controls, found {len(manifest)}"

    # Check each fixture has valid fields
    for entry in manifest:
        assert "id" in entry
        assert "source" in entry
        assert (root / entry["source"]).is_file(), f"Missing source file: {entry['source']}"
        assert entry["expected_compile"] in ("PASS", "FAIL")
        assert entry["expected_category"] in (
            "LATCH_INFERRED",
            "COMBINATIONAL_LOOP",
            "FORMAL_INVARIANT_BREACH",
            "SIMULATION_FAILURE",
            "CDC_VIOLATION",
            "TIMING_SLACK_VIOLATION",
            "SYNTHESIS_ELABORATION_ERROR",
            "COVERAGE_DEFICIT",
        )

    # Check all 15 required categories from primary prompt are represented
    ids = {e["id"] for e in manifest}
    required_ids = {
        "latch_inference",
        "combinational_loop",
        "incorrect_reset_behavior",
        "reset_deassertion_problem",
        "cdc_violation",
        "fifo_overflow",
        "fifo_underflow",
        "off_by_one_counter",
        "incorrect_handshake",
        "incorrect_fsm_transition",
        "width_truncation",
        "signed_unsigned_error",
        "timing_violation",
        "false_formal",
        "sim_behavioral_failure",
    }
    assert required_ids.issubset(ids), f"Missing required negative controls: {required_ids - ids}"

    readme = (root / "README.md").read_text(encoding="utf-8")
    for category in (
        "LATCH_INFERRED",
        "COMBINATIONAL_LOOP",
        "FORMAL_INVARIANT_BREACH",
        "SIMULATION_FAILURE",
        "COVERAGE_DEFICIT",
        "TIMING_SLACK_VIOLATION",
        "CDC_VIOLATION",
    ):
        assert category in readme
