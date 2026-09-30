"""
Bubblewrap (bwrap) sandboxing integration for Mind 3.0.
Enforces host-write / bwrap-exec isolation with unshared networking and strictly bound directories.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class BubblewrapSandbox:
    """Encapsulates process isolation using Linux Bubblewrap (bwrap)."""

    def __init__(
        self,
        workspace: Path | str,
        bwrap_binary: str | Path | None = None,
        extra_ro_binds: list[Path | str] | None = None,
    ) -> None:
        """Initialize the Bubblewrap sandbox targeting a verified workspace.

        Args:
            workspace: Path to the workspace directory. Must exist or will be created.
            bwrap_binary: Optional explicit path to bwrap executable.
            extra_ro_binds: Optional list of additional directories or files to bind read-only.

        Raises:
            RuntimeError: If bwrap binary is not located on PATH.
        """
        discovered_binary: str | None = None
        if bwrap_binary is not None:
            resolved_bin = shutil.which(str(bwrap_binary))
            if resolved_bin:
                discovered_binary = resolved_bin
        else:
            discovered_binary = shutil.which("bwrap")

        if not discovered_binary:
            raise RuntimeError(
                "bwrap binary not found on PATH. Mind 3.0 forbids unsandboxed execution."
            )

        self.workspace: Path = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._bwrap_bin: str = discovered_binary
        self._extra_ro_binds: list[Path] = [Path(p).resolve() for p in (extra_ro_binds or [])]

    @property
    def bwrap_binary(self) -> str:
        """Return the resolved path to the bwrap binary."""
        return self._bwrap_bin

    def run(
        self,
        command: list[str],
        timeout_sec: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        """Execute an arbitrary command array securely inside Bubblewrap.

        Args:
            command: Command name and argument list to run.
            timeout_sec: Hard timeout in seconds.

        Returns:
            subprocess.CompletedProcess containing returncode, stdout, and stderr.
        """
        if not command:
            return subprocess.CompletedProcess(
                args=[],
                returncode=1,
                stdout="",
                stderr="Error: empty command list provided to sandbox.",
            )

        sanitized_command = [str(arg) for arg in command]
        resolved_ws = str(self.workspace.resolve())
        cmd: list[str] = [
            self._bwrap_bin,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/bin",
            "/bin",
            "--ro-bind",
            "/lib",
            "/lib",
        ]

        if Path("/lib64").exists():
            cmd.extend(["--ro-bind", "/lib64", "/lib64"])
        if Path("/etc").exists():
            cmd.extend(["--ro-bind", "/etc", "/etc"])

        # Auto-bind standard EDA tool suites and PDKs read-only if present on host
        standard_ro_paths = [
            Path("/opt"),
            Path("/home/mind/.local"),
            Path("/home/mind/openroad-env"),
            Path("/home/mind/oss-cad-suite"),
            Path("/home/mind/pdk"),
        ]
        for p in standard_ro_paths:
            if p.exists():
                cmd.extend(["--ro-bind", str(p), str(p)])

        for p in self._extra_ro_binds:
            if p.exists():
                cmd.extend(["--ro-bind", str(p), str(p)])

        cmd.extend([
            "--bind",
            resolved_ws,
            resolved_ws,
            "--chdir",
            resolved_ws,
            "--",
            *sanitized_command,
        ])

        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            return completed
        except subprocess.TimeoutExpired as exc:
            stdout_text = (
                exc.stdout
                if isinstance(exc.stdout, str)
                else (exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "")
            )
            stderr_text = (
                exc.stderr
                if isinstance(exc.stderr, str)
                else (exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "")
            )
            timeout_msg = (
                f"Sandbox execution timed out after {timeout_sec} seconds: "
                f"{' '.join(sanitized_command)}"
            )
            combined_stderr = (
                f"{stderr_text}\n{timeout_msg}".strip() if stderr_text else timeout_msg
            )
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=124,
                stdout=stdout_text,
                stderr=combined_stderr,
            )
        except OSError as exc:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=127,
                stdout="",
                stderr=f"Operating system error executing bwrap sandbox: {exc}",
            )


__all__ = ["BubblewrapSandbox"]
