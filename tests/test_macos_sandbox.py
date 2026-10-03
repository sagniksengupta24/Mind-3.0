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


def test_macos_seatbelt_egress_blocked_by_real_socket_attempt(tmp_path: Path) -> None:
    """Prove Seatbelt denies a REAL outbound socket attempt (darwin only, no mocks).

    A host loopback listener provably accepts a connection outside the sandbox
    (baseline). The identical connection attempted inside MacOSSandbox must be
    denied by the OS. The observed denial (returncode, stdout/stderr) is
    asserted — never simulated. Skips carry meaningful reasons and are not passes.
    """
    import platform
    import shutil
    import socket
    import sys
    import threading

    if platform.system().lower() != "darwin":
        pytest.skip("macOS Seatbelt egress test requires Darwin.")
    if shutil.which("sandbox-exec") is None:
        pytest.skip("sandbox-exec binary not found on PATH.")
    if shutil.which("python3") is None:
        pytest.skip("python3 binary not found on PATH.")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host_port = server.getsockname()[1]

    def _accept_once() -> None:
        try:
            conn, _ = server.accept()
            conn.close()
        except OSError:
            pass

    try:
        # Baseline outside the sandbox: the listener must accept, proving the
        # endpoint is live. Without this, a sandbox-side failure proves nothing.
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(4.0)
            probe.connect(("127.0.0.1", host_port))
            probe.close()
        except OSError as exc:
            pytest.skip(f"host loopback baseline failed ({exc}); cannot attribute a sandbox denial.")

        threading.Thread(target=_accept_once, daemon=True).start()
        threading.Thread(target=_accept_once, daemon=True).start()

        sb = MacOSSandbox(tmp_path)
        res = sb.run(
            [
                sys.executable,
                "-c",
                (
                    "import socket, sys\n"
                    f"try:\n"
                    f"    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                    f"    s.settimeout(5.0)\n"
                    f"    s.connect(('127.0.0.1', {host_port}))\n"
                    f"    sys.stdout.write('CONNECTED_UNEXPECTEDLY\\n')\n"
                    f"    sys.exit(0)\n"
                    f"except OSError as e:\n"
                    f"    sys.stdout.write(f'BLOCKED_BY_SANDBOX: errno={{e.errno}} {{e}}\\n')\n"
                    f"    sys.exit(42)\n"
                ),
            ],
            timeout_sec=15,
        )
        assert res.returncode == 42, (
            f"Seatbelt must deny the outbound socket attempt (rc=42), got rc={res.returncode}: "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )
        assert "BLOCKED_BY_SANDBOX" in res.stdout
        assert "CONNECTED_UNEXPECTEDLY" not in res.stdout
    finally:
        server.close()


def test_local_sandbox_factory_selects_platform_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mind3.sandbox.platform.platform.system", lambda: "Darwin")
    monkeypatch.setattr("mind3.sandbox.platform.MacOSSandbox", lambda workspace, extra_ro_paths=None: (workspace, extra_ro_paths))
    result = __import__("mind3.sandbox.platform", fromlist=["get_local_sandbox"]).get_local_sandbox(tmp_path)
    assert result[0] == tmp_path
