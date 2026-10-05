"""Regression tests for environment-aware timing Liberty resolution.

The resolver prefers a real SKY130 library supplied via the existing
environment mechanisms and falls back to the packaged fixture. It never
generates library content.
"""

from __future__ import annotations

from pathlib import Path

from mind3.eda.timing_liberty import resolve_timing_liberty


def test_packaged_fixture_is_fallback(monkeypatch) -> None:
    for var in ("MIND3_NEGATIVE_CONTROL_LIBERTY", "MIND3_LIBERTY_PATH", "MIND3_SKY130_ROOT"):
        monkeypatch.delenv(var, raising=False)
    liberty, source = resolve_timing_liberty()
    assert liberty is not None and liberty.is_file()
    assert source == "packaged-fixture"
    assert liberty.name == "sky130_fd_sc_hd__tt_025C_1v80.lib"


def test_env_liberty_takes_precedence_over_fixture(tmp_path, monkeypatch) -> None:
    real = tmp_path / "custom_tt.lib"
    real.write_text("library (custom) {}\n", encoding="utf-8")
    monkeypatch.setenv("MIND3_NEGATIVE_CONTROL_LIBERTY", str(real))
    monkeypatch.delenv("MIND3_LIBERTY_PATH", raising=False)
    monkeypatch.delenv("MIND3_SKY130_ROOT", raising=False)
    liberty, source = resolve_timing_liberty()
    assert liberty == real
    assert source == "MIND3_NEGATIVE_CONTROL_LIBERTY"


def test_missing_env_entry_falls_through(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "MIND3_NEGATIVE_CONTROL_LIBERTY",
        str(tmp_path / "does_not_exist.lib"),
    )
    monkeypatch.delenv("MIND3_LIBERTY_PATH", raising=False)
    monkeypatch.delenv("MIND3_SKY130_ROOT", raising=False)
    liberty, source = resolve_timing_liberty()
    assert liberty is not None and liberty.is_file()
    assert source == "packaged-fixture"


def test_sky130_root_derives_real_library(tmp_path, monkeypatch) -> None:
    lib_dir = tmp_path / "libs.ref" / "sky130_fd_sc_hd" / "lib"
    lib_dir.mkdir(parents=True)
    derived = lib_dir / "sky130_fd_sc_hd__tt_025C_1v80.lib"
    derived.write_text("library (derived) {}\n", encoding="utf-8")
    monkeypatch.delenv("MIND3_NEGATIVE_CONTROL_LIBERTY", raising=False)
    monkeypatch.delenv("MIND3_LIBERTY_PATH", raising=False)
    monkeypatch.setenv("MIND3_SKY130_ROOT", str(tmp_path))
    liberty, source = resolve_timing_liberty()
    assert liberty == derived
    assert source == "MIND3_SKY130_ROOT"


def test_empty_file_is_not_selected(tmp_path, monkeypatch) -> None:
    empty = tmp_path / "empty.lib"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("MIND3_NEGATIVE_CONTROL_LIBERTY", str(empty))
    monkeypatch.delenv("MIND3_LIBERTY_PATH", raising=False)
    monkeypatch.delenv("MIND3_SKY130_ROOT", raising=False)
    liberty, source = resolve_timing_liberty()
    assert source == "packaged-fixture"
    assert liberty is not None and liberty != empty
