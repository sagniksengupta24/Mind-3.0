"""Platform-aware local sandbox factory."""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

from .bwrap import BubblewrapSandbox
from .macos import MacOSSandbox


def get_local_sandbox(workspace: Path | str, **kwargs: Any):
    """Return the strongest supported local sandbox without falling back to unsandboxed execution."""
    system = platform.system().lower()
    if system == "linux":
        return BubblewrapSandbox(workspace=workspace, **kwargs)
    if system == "darwin":
        return MacOSSandbox(workspace=workspace, extra_ro_paths=kwargs.get("extra_ro_binds"))
    raise RuntimeError(
        f"Unsupported local sandbox platform: {platform.system()}. Configure EDA_REMOTE_HOST for a Linux verifier."
    )


__all__ = ["get_local_sandbox"]
