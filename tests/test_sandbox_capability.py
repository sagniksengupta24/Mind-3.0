"""SYNTHETIC unit tests for Bubblewrap namespace-capability detection.

Every test in this file fakes the host interaction (``shutil.which`` /
``subprocess.run`` are monkeypatched). These tests prove only the decision
mapping of :func:`mind3.sandbox.bwrap.probe_bubblewrap_namespace_capability`:

* missing binary -> incapable with a PATH reason;
* clean namespace creation -> capable;
* kernel refusing namespaces -> incapable with the kernel reason attached;
* timeout / OS error -> incapable, never raised.

They execute no real sandbox and are NOT sandbox evidence. Real
enforcement is asserted only by
``test_bubblewrap_sandbox_network_isolation_outbound_blocked`` on a
namespace-capable Linux host.
"""

from __future__ import annotations

import shutil
import subprocess

from mind3.sandbox import bwrap as bwrap_module
from mind3.sandbox.bwrap import probe_bubblewrap_namespace_capability


def _fake_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["bwrap"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_probe_missing_binary_reports_incapable(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    capable, reason = probe_bubblewrap_namespace_capability()
    assert capable is False
    assert "not found on PATH" in reason


def test_probe_success_reports_capable(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/bwrap")
    seen: dict[str, object] = {}

    def fake_run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert isinstance(cmd, list)
        seen["cmd"] = cmd
        return _fake_completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    capable, reason = probe_bubblewrap_namespace_capability()
    assert capable is True
    assert isinstance(reason, str) and reason != ""
    # The probe must exercise namespace creation, not a metadata query.
    assert "--unshare-all" in seen["cmd"]


def test_probe_namespace_denied_reports_incapable_with_reason(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/bwrap")

    def fake_run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return _fake_completed(1, "", "bwrap: No permissions to create a new namespace")

    monkeypatch.setattr(subprocess, "run", fake_run)
    capable, reason = probe_bubblewrap_namespace_capability()
    assert capable is False
    assert "No permissions to create a new namespace" in reason
    assert "exit 1" in reason


def test_probe_timeout_reports_incapable(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/bwrap")

    def fake_run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["bwrap"], timeout=20)

    monkeypatch.setattr(subprocess, "run", fake_run)
    capable, reason = probe_bubblewrap_namespace_capability()
    assert capable is False
    assert "timed out" in reason


def test_probe_os_error_reports_incapable(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/bwrap")

    def fake_run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("execve refused")

    monkeypatch.setattr(subprocess, "run", fake_run)
    capable, reason = probe_bubblewrap_namespace_capability()
    assert capable is False
    assert "could not execute" in reason


def test_probe_respects_explicit_binary(monkeypatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(shutil, "which", lambda name: name if name == "/opt/bwrap" else None)

    def fake_run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["cmd"] = cmd
        return _fake_completed(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    capable, _reason = probe_bubblewrap_namespace_capability(bwrap_binary="/opt/bwrap")
    assert capable is True
    assert seen["cmd"][0] == "/opt/bwrap"


def test_probe_function_is_exported() -> None:
    assert "probe_bubblewrap_namespace_capability" in bwrap_module.__all__
