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

from .platform import get_local_sandbox


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

    @property
    def execution_mode(self) -> str:
        """Identifier for execution security mode (e.g. 'local_bwrap', 'local_macos_seatbelt', 'unsandboxed_local', 'remote_ssh')."""
        return self.runner_type

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether execution tier is accessible."""
        raise NotImplementedError("EDARunner subclass must implement is_available.")


class LocalBwrapRunner(EDARunner):
    """Executes EDA commands only through Bubblewrap by default.

    Unsandboxed execution is deliberately opt-in for local development and is
    never selected by the production runner factory.
    """

    def __init__(
        self,
        workspace: Path | str,
        sandbox: Any | None = None,
        allow_unsandboxed: bool = False,
    ) -> None:
        self.workspace: Path = Path(workspace).resolve()
        self.sandbox: BubblewrapSandbox | None = sandbox
        self.allow_unsandboxed = allow_unsandboxed

    @property
    def runner_type(self) -> str:
        return "local_bwrap"

    @property
    def execution_mode(self) -> str:
        if self.sandbox is not None:
            return getattr(self.sandbox, "runner_type", "local_sandbox")
        if self.allow_unsandboxed:
            return "unsandboxed_local"
        return "none"

    def is_available(self) -> bool:
        return self.sandbox is not None or self.allow_unsandboxed

    def run(
        self,
        command: list[str],
        timeout_sec: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        if self.sandbox is not None:
            return self.sandbox.run(command, timeout_sec=timeout_sec)

        if not self.allow_unsandboxed:
            return subprocess.CompletedProcess(
                args=command,
                returncode=127,
                stdout="",
                stderr="SANDBOX_UNAVAILABLE: Bubblewrap sandbox is required; refusing unsandboxed EDA execution.",
            )

        # Explicitly opt-in local development escape hatch.
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
    """Offloads EDA compilation and formal verification to an enterprise cluster over SSH with bidirectional sync."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        user: str = "eda_runner",
        key_file: Path | str | None = None,
        known_hosts_file: Path | str | None = None,
        remote_workdir: str = "/tmp/mind3_remote_eda",
        workspace: Path | str | None = None,
    ) -> None:
        self.host: str = host.strip()
        self.port: int = port
        self.user: str = user.strip()
        self.key_file: Path | None = Path(key_file).resolve() if key_file else None
        self.known_hosts_file: Path | None = Path(known_hosts_file).resolve() if known_hosts_file else None
        self.remote_workdir: str = remote_workdir.strip()
        self.workspace: Path | None = Path(workspace).resolve() if workspace else None

    @property
    def runner_type(self) -> str:
        return "remote_ssh"

    @property
    def execution_mode(self) -> str:
        return "remote_ssh"

    def is_available(self) -> bool:
        return bool(self.host and self.known_hosts_file and self.known_hosts_file.is_file())

    def _ssh_base_command(self) -> list[str]:
        """Build SSH arguments that require a pinned host key."""
        if not self.known_hosts_file or not self.known_hosts_file.is_file():
            raise RuntimeError("REMOTE_HOST_KEY_UNAVAILABLE: configure a readable known_hosts file for the EDA host.")
        command = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={self.known_hosts_file}",
            "-p", str(self.port),
        ]
        if self.key_file is not None and self.key_file.exists():
            command.extend(["-i", str(self.key_file)])
        return command

    def sync_to_remote(self, workspace: Path | str) -> bool:
        """Stream local workspace contents to the remote execution node via SSH."""
        ws_path = Path(workspace).resolve()
        if not ws_path.exists():
            return False

        try:
            ssh_cmd = self._ssh_base_command()
        except RuntimeError:
            return False

        remote_setup = f"mkdir -p {shlex.quote(self.remote_workdir)} && tar -xzf - -C {shlex.quote(self.remote_workdir)}"
        ssh_cmd.extend([f"{self.user}@{self.host}", remote_setup])
        tar_cmd = ["tar", "--exclude=.mind", "--exclude=.git", "-czf", "-", "-C", str(ws_path), "."]

        try:
            tar_proc = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            ssh_proc = subprocess.Popen(ssh_cmd, stdin=tar_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if tar_proc.stdout:
                tar_proc.stdout.close()
            ssh_proc.communicate(timeout=45)
            tar_proc.wait(timeout=10)
            return ssh_proc.returncode == 0
        except Exception:
            return False

    def sync_from_remote(self, workspace: Path | str) -> bool:
        """Retrieve generated EDA artifacts (netlists, logs, coverage) back to local workspace."""
        ws_path = Path(workspace).resolve()
        if not ws_path.exists():
            return False

        try:
            ssh_cmd = self._ssh_base_command()
        except RuntimeError:
            return False

        remote_tar = f"tar -czf - -C {shlex.quote(self.remote_workdir)} ."
        ssh_cmd.extend([f"{self.user}@{self.host}", remote_tar])
        tar_extract = ["tar", "-xzf", "-", "-C", str(ws_path)]

        try:
            ssh_proc = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            extract_proc = subprocess.Popen(tar_extract, stdin=ssh_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if ssh_proc.stdout:
                ssh_proc.stdout.close()
            extract_proc.communicate(timeout=45)
            ssh_proc.wait(timeout=10)
            return extract_proc.returncode == 0
        except Exception:
            return False

    def run(
        self,
        command: list[str],
        timeout_sec: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        """Wrap command in SSH invocation targeting remote compute node with synchronization."""
        # Synchronize workspace to remote compute node if workspace configured
        if self.workspace is not None and self.workspace.exists():
            self.sync_to_remote(self.workspace)

        remote_cmd_str = " ".join(shlex.quote(c) for c in command)
        remote_full = f"mkdir -p {shlex.quote(self.remote_workdir)} && cd {shlex.quote(self.remote_workdir)} && {remote_cmd_str}"

        try:
            ssh_cmd = self._ssh_base_command()
        except RuntimeError as exc:
            return subprocess.CompletedProcess(args=command, returncode=255, stdout="", stderr=str(exc))

        ssh_cmd.extend([f"{self.user}@{self.host}", remote_full])

        try:
            proc = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            # Retrieve generated artifacts back to local workspace
            if self.workspace is not None and self.workspace.exists():
                self.sync_from_remote(self.workspace)
            return proc
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
    sandbox: Any | None = None,
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
        known_hosts = os.getenv("EDA_REMOTE_KNOWN_HOSTS", "").strip()
        if not known_hosts:
            raise RuntimeError("EDA_REMOTE_KNOWN_HOSTS is required when EDA_REMOTE_HOST is configured.")
        return RemoteSSHRunner(
            host=remote_host,
            port=port,
            user=user,
            key_file=key if key else None,
            known_hosts_file=known_hosts,
            workspace=workspace,
        )

    return LocalBwrapRunner(workspace=workspace, sandbox=sandbox if sandbox is not None else get_local_sandbox(workspace))
