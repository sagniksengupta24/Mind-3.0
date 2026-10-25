"""Host-independent sandbox double for unit tests.

The production driver refuses to run without a real sandbox (Bubblewrap on
Linux, Seatbelt on macOS). Unit tests that only exercise orchestration should
not require either binary, so they inject this stub explicitly. Any attempt to
actually execute a command through it fails loudly rather than silently running
unsandboxed.
"""

from __future__ import annotations

from typing import Any


class StubSandbox:
    """Minimal stand-in for a real sandbox; never executes commands."""

    runner_type = "stub"
    execution_mode = "stub"

    def is_available(self) -> bool:
        return True

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unit-test sandbox must not execute commands")

    def close(self) -> None:
        return None
