"""macOS Seatbelt sandbox backend for Mind 3.0.

Bubblewrap is Linux-only.  On Darwin we use Apple's ``sandbox-exec`` command-line
Seatbelt interface with a deny-by-default profile: no network access, read-only
system/toolchain paths, and read/write access only to the task workspace plus
isolated temporary storage.

Apple documents ``sandbox-exec`` as deprecated; it remains a supported mechanism
for command-line sandboxing on current macOS releases.  This backend is therefore
kept narrowly scoped to local developer/benchmark execution and is not presented as
an App Sandbox replacement.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class MacOSSandbox:
    """Execute commands under a deny-by-default macOS Seatbelt profile."""

    def __init__(
        self,
        workspace: Path | str,
        sandbox_exec_binary: str | Path | None = None,
        extra_ro_paths: list[Path | str] | None = None,
    ) -> None:
        discovered = shutil.which(str(sandbox_exec_binary)) if sandbox_exec_binary else shutil.which("sandbox-exec")
        if not discovered:
            raise RuntimeError(
                "sandbox-exec binary not found on PATH. Mind 3.0 forbids unsandboxed execution."
            )

        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._sandbox_exec_bin = discovered
        self._extra_ro_paths = [Path(p).expanduser().resolve() for p in (extra_ro_paths or [])]
        self._tmpdir = self.workspace / ".mind3_tmp"
        self._tmpdir.mkdir(parents=True, exist_ok=True)

    @property
    def sandbox_binary(self) -> str:
        return self._sandbox_exec_bin

    @property
    def runner_type(self) -> str:
        return "local_macos_seatbelt"

    @property
    def execution_mode(self) -> str:
        return "local_macos_seatbelt"

    def is_available(self) -> bool:
        return bool(self._sandbox_exec_bin)

    @staticmethod
    def _sexpr_path(path: Path) -> str:
        # sandbox-exec profile strings use double-quoted string literals.
        value = str(path.resolve()).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{value}"'

    def _profile(self) -> str:
        lines = [
            "(version 1)",
            "(deny default)",
            # Commands launched by Yosys/SBY/Verilator may spawn helpers.
            "(allow process-fork)",
            "(allow process-exec)",
            "(allow signal (target same-sandbox))",
            "(allow process-info* (target same-sandbox))",
            "(allow sysctl*)",
            "(allow mach-lookup)",
            "(allow ipc-posix-sem)",
            "(allow ipc-posix-shm*)",
            "(allow file-ioctl)",
            # System-wide read-only access for toolchains, libraries, and dev devices
            "(allow file-read*)",
            '(allow file-write* (literal "/dev/null"))',
            '(allow file-write* (literal "/dev/dtracehelper"))',
        ]
        ws = self._sexpr_path(self.workspace)
        tmp = self._sexpr_path(self._tmpdir)
        lines.append(f"(allow file-read* file-write* (subpath {ws}))")
        lines.append(f"(allow file-read* file-write* (subpath {tmp}))")
        # Restrict all network access. The benchmark LLM call occurs outside this
        # sandbox; EDA execution itself must remain offline and deterministic.
        lines.append("(deny network*)")
        return "\n".join(lines)

    def run(self, command: list[str], timeout_sec: int = 60) -> subprocess.CompletedProcess[str]:
        if not command:
            return subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="Error: empty command list provided to sandbox."
            )
        if not command[0]:
            return subprocess.CompletedProcess(
                args=command, returncode=1, stdout="", stderr="Error: empty command executable provided to sandbox."
            )

        env = os.environ.copy()
        env["TMPDIR"] = str(self._tmpdir)
        cmd = [self._sandbox_exec_bin, "-p", self._profile(), "--", *[str(c) for c in command]]
        try:
            return subprocess.run(
                cmd,
                cwd=str(self.workspace),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "")
            msg = f"Sandbox execution timed out after {timeout_sec} seconds: {' '.join(map(str, command))}"
            return subprocess.CompletedProcess(
                args=cmd, returncode=124, stdout=stdout, stderr=f"{stderr}\n{msg}".strip()
            )
        except OSError as exc:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=127,
                stdout="",
                stderr=f"Operating system error executing macOS sandbox: {exc}",
            )


__all__ = ["MacOSSandbox"]
