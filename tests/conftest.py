from __future__ import annotations

import shutil

import pytest


def _tool_present(name: str) -> bool:
    """Check one declared tool prerequisite (never a substitute for execution)."""
    import os

    if name == "sta/opensta":
        return shutil.which("sta") is not None or shutil.which("opensta") is not None
    if name == "sandbox":
        if os.uname().sysname == "Darwin":
            return shutil.which("sandbox-exec") is not None
        return shutil.which("bwrap") is not None
    return shutil.which(name) is not None


# Full default prerequisite set preserves the historical all-or-nothing gate
# for tests that do not declare narrower needs.
_DEFAULT_EDA_TOOLS = ("sandbox", "yosys", "sby", "verilator", "sta/opensta")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip EDA-marked tests when their declared live toolchain is not installed.

    A test may narrow its prerequisites with ``@pytest.mark.eda_tools(...)``
    (e.g. a CDC test needs only yosys); tests without the marker keep the
    historical full-toolchain requirement. CI/live hosts with the tools
    installed execute the exact same tests. This keeps plain `pytest` useful
    on developer machines without turning tool absence into a misleading
    assertion failure.
    """
    for item in items:
        if "eda" not in item.keywords:
            continue
        marker = item.get_closest_marker("eda_tools")
        required = list(marker.args) if marker is not None else list(_DEFAULT_EDA_TOOLS)
        missing = [name for name in required if not _tool_present(name)]
        if not missing:
            continue
        reason = "live EDA prerequisites missing: " + ", ".join(missing)
        item.add_marker(pytest.mark.skip(reason=reason))
