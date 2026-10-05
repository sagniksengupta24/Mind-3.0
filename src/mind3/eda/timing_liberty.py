"""Resolve the timing Liberty file for OpenSTA workloads.

Precedence (first existing file wins):

1. ``MIND3_NEGATIVE_CONTROL_LIBERTY`` — colon-separated liberty path(s).
2. ``MIND3_LIBERTY_PATH`` — colon-separated liberty path(s).
3. ``MIND3_SKY130_ROOT`` — SkyWater 130nm PDK root; derives
   ``libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib``.
4. Packaged fallback fixture
   ``src/mind3/pdata/sky130/sky130_fd_sc_hd__tt_025C_1v80.lib``.

An environment-supplied path is selected only when it points to a real,
non-empty file. Nothing is generated: when no candidate exists this module
returns ``(None, "missing")`` so callers fail closed with a clear message.
"""

from __future__ import annotations

import os
from pathlib import Path

_LIB_FILENAME = "sky130_fd_sc_hd__tt_025C_1v80.lib"

_PACKAGED_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "pdata"
    / "sky130"
    / _LIB_FILENAME
)


def _first_existing(candidates: list[str]) -> Path | None:
    for raw in candidates:
        text = (raw or "").strip()
        if not text:
            continue
        path = Path(text).expanduser()
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            continue
    return None


def resolve_timing_liberty() -> tuple[Path | None, str]:
    """Return ``(liberty_path, source)`` for OpenSTA timing workloads."""
    for var in ("MIND3_NEGATIVE_CONTROL_LIBERTY", "MIND3_LIBERTY_PATH"):
        found = _first_existing(os.getenv(var, "").split(":"))
        if found is not None:
            return found, var

    sky130_root = (os.getenv("MIND3_SKY130_ROOT", "") or "").strip()
    if sky130_root:
        derived = (
            Path(sky130_root).expanduser().resolve()
            / "libs.ref"
            / "sky130_fd_sc_hd"
            / "lib"
            / _LIB_FILENAME
        )
        if derived.is_file():
            try:
                derived_usable = derived.stat().st_size > 0
            except OSError:
                derived_usable = False
            if derived_usable:
                return derived, "MIND3_SKY130_ROOT"

    if _PACKAGED_FIXTURE.is_file():
        try:
            fixture_usable = _PACKAGED_FIXTURE.stat().st_size > 0
        except OSError:
            fixture_usable = False
        if fixture_usable:
            return _PACKAGED_FIXTURE, "packaged-fixture"
    return None, "missing"
