"""
Two-tier execution backend for Mind 3.0.
Provides unified EDARunner interface with LocalBwrapRunner and enterprise RemoteSSHRunner.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .bwrap import BubblewrapSandbox


class EDARunner(ABC):
    """Abstract interface for local sandboxed or remote cluster execution."""

    @abstractmethod
    def run(
        self,
        command: list[str],
        timeout_sec: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        """Execute command and return completed process record."""
        raise NotImplementedError("EDARunner subclass must implement run().")

    @property
    @abstractmethod
    def runner_type(self) -> str:
        """Identifier for execution tier."""
        raise NotImplementedError("EDARunner subclass must implement runner_type.")

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether execution tier is accessible."""
        raise NotImplementedError("EDARunner subclass must implement is_available.")


class LocalBwrapRunner(EDARunner):
    """Executes EDA commands locally within Bubblewrap sandbox or contained subprocess."""

    def __init__(
        self,
        workspace: Path | str,
        sandbox: BubblewrapSandbox | None = None,
    ) -> None:
        self.workspace: Path = Path(workspace).resolve()
        self.sandbox: BubblewrapSandbox | None = sandbox

    @property
    def runner_type(self) -> str:
        return "local_bwrap"

    def is_available(self) -> bool:
        return self.sandbox is not None or self.workspace.exists()

    def run(
        self,
        command: list[str],
        timeout_sec: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        if self.sandbox is not None:
            return self.sandbox.run(command, timeout_sec=timeout_sec)

        # Fallback to local subprocess if bwrap is mocked/omitted
        try:
            return subprocess.run(
                command,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(
                args=command,
                returncode=124,
                stdout=str(exc.stdout or ""),
                stderr=f"Local execution timed out after {timeout_sec}s.",
            )
        except Exception as exc:
            return subprocess.CompletedProcess(
                args=command,
                returncode=127,
                stdout="",
                stderr=f"Failed to execute local command: {exc}",
            )


class RemoteSSHRunner(EDARunner):
    """Offloads EDA compilation and formal verification to an enterprise cluster over SSH."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        user: str = "eda_runner",
        key_file: Path | str | None = None,
        remote_workdir: str = "/tmp/mind3_remote_eda",
    ) -> None:
        self.host: str = host.strip()
        self.port: int = port
        self.user: str = user.strip()
        self.key_file: Path | None = Path(key_file).resolve() if key_file else None
        self.remote_workdir: str = remote_workdir.strip()

    @property
    def runner_type(self) -> str:
        return "remote_ssh"

    def is_available(self) -> bool:
        return bool(self.host)

    def run(
        self,
        command: list[str],
        timeout_sec: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        """Wrap command in SSH invocation targeting remote compute node."""
        remote_cmd_str = " ".join(shlex.quote(c) for c in command)
        remote_full = f"mkdir -p {shlex.quote(self.remote_workdir)} && cd {shlex.quote(self.remote_workdir)} && {remote_cmd_str}"

        ssh_cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            "-p", str(self.port),
        ]
        if self.key_file is not None and self.key_file.exists():
            ssh_cmd.extend(["-i", str(self.key_file)])

        ssh_cmd.extend([f"{self.user}@{self.host}", remote_full])

        try:
            return subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(
                args=command,
                returncode=124,
                stdout=str(exc.stdout or ""),
                stderr=f"Remote execution on {self.host} timed out after {timeout_sec}s.",
            )
        except Exception as exc:
            return subprocess.CompletedProcess(
                args=command,
                returncode=255,
                stdout="",
                stderr=f"Remote SSH connection failed to {self.host}: {exc}",
            )


def get_eda_runner(
    workspace: Path | str,
    sandbox: BubblewrapSandbox | None = None,
) -> EDARunner:
    """Factory selecting RemoteSSHRunner if configured in environment, else LocalBwrapRunner."""
    remote_host = os.getenv("EDA_REMOTE_HOST", "").strip()
    if remote_host:
        port_raw = os.getenv("EDA_REMOTE_PORT", "22").strip()
        try:
            port = int(port_raw)
        except ValueError:
            port = 22
        user = os.getenv("EDA_REMOTE_USER", "eda_runner").strip()
        key = os.getenv("EDA_REMOTE_KEY", "").strip()
        return RemoteSSHRunner(
            host=remote_host,
            port=port,
            user=user,
            key_file=key if key else None,
        )

    return LocalBwrapRunner(workspace=workspace, sandbox=sandbox)
