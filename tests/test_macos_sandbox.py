from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mind3.sandbox.macos import MacOSSandbox


def test_macos_sandbox_requires_sandbox_exec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mind3.sandbox.macos.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="sandbox-exec binary not found"):
        MacOSSandbox(tmp_path)


def test_macos_sandbox_builds_deny_default_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mind3.sandbox.macos.shutil.which", lambda _: "/usr/bin/sandbox-exec")
    sb = MacOSSandbox(tmp_path)
    profile = sb._profile()
    assert "(deny default)" in profile
    assert "(deny network*)" in profile
    assert f"(allow file-read* file-write* (subpath \"{tmp_path.resolve()}\"))" in profile


def test_macos_sandbox_executes_through_seatbelt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mind3.sandbox.macos.shutil.which", lambda _: "/usr/bin/sandbox-exec")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        assert cmd[:2] == ["/usr/bin/sandbox-exec", "-p"]
        assert "(deny network*)" in cmd[2]
        assert cmd[-2:] == ["echo", "ok"]
        return subprocess.CompletedProcess(cmd, 0, "ok\n", "")

    monkeypatch.setattr("mind3.sandbox.macos.subprocess.run", fake_run)
    result = MacOSSandbox(tmp_path).run(["echo", "ok"], timeout_sec=5)
    assert result.returncode == 0
    assert calls


def test_local_sandbox_factory_selects_platform_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mind3.sandbox.platform.platform.system", lambda: "Darwin")
    monkeypatch.setattr("mind3.sandbox.platform.MacOSSandbox", lambda workspace, extra_ro_paths=None: (workspace, extra_ro_paths))
    result = __import__("mind3.sandbox.platform", fromlist=["get_local_sandbox"]).get_local_sandbox(tmp_path)
    assert result[0] == tmp_path
