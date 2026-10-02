from __future__ import annotations

import shutil

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip EDA-marked tests when the required live toolchain is not installed.

    CI/live hosts with the tools installed execute the exact same tests. This keeps
    plain `pytest` useful on developer machines without turning tool absence into a
    misleading assertion failure.
    """
    import os

    missing = []
    if os.uname().sysname == "Darwin":
        if shutil.which("sandbox-exec") is None:
            missing.append("sandbox-exec")
    elif shutil.which("bwrap") is None:
        missing.append("bwrap")
    for name in ("yosys", "sby", "verilator"):
        if shutil.which(name) is None:
            missing.append(name)
    if shutil.which("sta") is None and shutil.which("opensta") is None:
        missing.append("sta/opensta")
    if not missing:
        return
    reason = "live EDA prerequisites missing: " + ", ".join(missing)
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if "eda" in item.keywords:
            item.add_marker(marker)
