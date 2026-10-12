"""Gate 6 crux backend: probe, selection order, and verdict mapping.

Fixtures are real captured crux 0.1.0 reports: cdc_bad (unsynchronized
clk_a->clk_b crossing) and cdc_good2 (2FF synchronizer chain).
"""
import json
from pathlib import Path

from mind3.core import verifier as verifier_mod

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _report(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_crux_pinned_version_matches_fixtures() -> None:
    assert verifier_mod.CRUX_VERSION == "0.1.0"
    assert _report("cdc_crux_bad.json")["version"] == verifier_mod.CRUX_VERSION
    assert _report("cdc_crux_good.json")["version"] == verifier_mod.CRUX_VERSION


def test_crux_absent_by_default_in_this_env(monkeypatch) -> None:
    monkeypatch.delenv("MIND3_CRUX_BIN", raising=False)
    monkeypatch.delenv("MIND3_CDC_NO_CRUX", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert verifier_mod.has_crux() is False


def test_crux_opt_out_wins(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "crux"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("MIND3_CRUX_BIN", str(fake))
    monkeypatch.setenv("MIND3_CDC_NO_CRUX", "1")
    assert verifier_mod.has_crux() is False


def test_no_fallback_flag_also_blocks_crux(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "crux"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("MIND3_CRUX_BIN", str(fake))
    monkeypatch.delenv("MIND3_CDC_NO_CRUX", raising=False)
    monkeypatch.setenv("MIND3_CDC_NO_FALLBACK", "1")
    assert verifier_mod.has_crux() is False


def test_crux_env_override_detected(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "crux"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("MIND3_CRUX_BIN", str(fake))
    monkeypatch.delenv("MIND3_CDC_NO_CRUX", raising=False)
    assert verifier_mod.has_crux() is True


def test_selection_order_external_then_crux_then_structural(monkeypatch) -> None:
    monkeypatch.setattr(verifier_mod, "has_external_yosys_cdc", lambda: True)
    assert verifier_mod.select_cdc_implementation()[0] == "external"
    monkeypatch.setattr(verifier_mod, "has_external_yosys_cdc", lambda: False)
    monkeypatch.setattr(verifier_mod, "has_crux", lambda: True)
    kind, version = verifier_mod.select_cdc_implementation()
    assert kind == "crux" and verifier_mod.CRUX_VERSION in version
    monkeypatch.setattr(verifier_mod, "has_crux", lambda: False)
    kind, version = verifier_mod.select_cdc_implementation()
    assert kind == "structural"


def test_verdict_bad_report_fails() -> None:
    gate_passed, category, violations, details = verifier_mod.crux_report_to_verdict(
        _report("cdc_crux_bad.json")
    )
    assert gate_passed is False
    assert category == "CDC_VIOLATION"
    assert len(violations) == 1 and "MISSING_SYNC" in violations[0]


def test_verdict_good_report_passes() -> None:
    gate_passed, category, violations, details = verifier_mod.crux_report_to_verdict(
        _report("cdc_crux_good.json")
    )
    assert gate_passed is True
    assert category is None
    assert violations == []
    assert "1 crossing" in details


def test_verdict_unreadable_report_blocks() -> None:
    gate_passed, category, violations, details = verifier_mod.crux_report_to_verdict({})
    assert gate_passed is False
    assert category == "CDC_CHECKER_ERROR"


def test_verdict_warnings_do_not_fail() -> None:
    report = _report("cdc_crux_good.json")
    report["violations"] = [
        {"rule": "RECONVERGENCE", "severity": "warn", "message": "reconvergence noted"}
    ]
    gate_passed, category, violations, details = verifier_mod.crux_report_to_verdict(report)
    assert gate_passed is True
    assert category is None
    assert "warning" in details
