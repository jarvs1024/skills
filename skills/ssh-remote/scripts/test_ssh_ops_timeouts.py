"""Unit tests for timeout plumbing in ssh_ops.py.

Run with:
    cd C:/Users/2268/.claude/skills/ssh-remote
    python -m pytest scripts/test_ssh_ops_timeouts.py -v

The SFTP callback deadline and the _run_and_print wall-clock deadline are the
two pieces of "soft" timeout protection on top of paramiko's own channel /
transport timers. These tests don't open a real SSH connection — they use
fakes that simulate a hanging channel and verify the deadline fires.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ssh_ops import (
    _run_and_print,
    _sftp_progress_callback,
)


class _FakeChannel:
    """Minimal stand-in for paramiko's Channel that never reports ready/closed."""
    def __init__(self):
        self.closed = False
        self._bytes = b""

    def recv(self, _n):
        return self._bytes

    def recv_stderr(self, _n):
        return b""

    def recv_ready(self):
        return False

    def recv_stderr_ready(self):
        return False

    def exit_status_ready(self):
        return False

    def recv_exit_status(self):
        return 0

    def close(self):
        self.closed = True


class _FakeClient:
    """Records the command, returns a never-ending channel."""
    def __init__(self):
        self.last_command = None
        self.last_timeout = None
        self.channel = _FakeChannel()

    def exec_command(self, command, timeout=None, environment=None):
        self.last_command = command
        self.last_timeout = timeout
        stdin = object()
        return stdin, type("S", (), {"channel": self.channel})(), object()


def test_run_and_print_returns_124_on_deadline(monkeypatch):
    """When the channel never closes and exit_status never arrives, the
    wall-clock deadline must kick in and return 124 (GNU `timeout` convention).
    """
    client = _FakeClient()

    # Patch the busy-wait sleep so the test does not actually sleep 0.02s
    # thousands of times.
    monkeypatch.setattr("ssh_ops.time.sleep", lambda _s: None)

    t0 = time.monotonic()
    rc = _run_and_print(client, "sleep 9999", timeout=1)
    elapsed = time.monotonic() - t0

    assert rc == 124, f"expected 124 on timeout, got {rc}"
    assert elapsed < 5, f"deadline path took too long: {elapsed}s"
    assert client.channel.closed, "channel must be closed on deadline"
    assert client.last_timeout == 1, "paramiko-level timeout must be passed through"


def test_run_and_print_returns_immediately_when_command_succeeds(monkeypatch):
    """If the channel reports exit_status_ready, the loop must exit promptly."""
    class _QuickChannel(_FakeChannel):
        def __init__(self):
            super().__init__()
            self._ready_once = [False]

        def exit_status_ready(self):
            return True

        def recv_exit_status(self):
            return 0

    client = _FakeClient()
    client.channel = _QuickChannel()
    monkeypatch.setattr("ssh_ops.time.sleep", lambda _s: None)

    t0 = time.monotonic()
    rc = _run_and_print(client, "true", timeout=10)
    elapsed = time.monotonic() - t0
    assert rc == 0
    assert elapsed < 1


def test_sftp_progress_callback_raises_after_deadline():
    """The SFTP callback must raise IOError once the deadline passes."""
    deadline = time.monotonic() + 0.05
    cb = _sftp_progress_callback(deadline, "put /tmp/x")

    # First call: still within deadline, no raise.
    cb(1024, 4096)

    time.sleep(0.1)
    with pytest.raises(IOError) as exc_info:
        cb(2048, 4096)
    assert "deadline" in str(exc_info.value).lower()
    assert "1024" not in str(exc_info.value) or "after" in str(exc_info.value)


def test_sftp_progress_callback_does_not_raise_well_within_deadline():
    deadline = time.monotonic() + 5
    cb = _sftp_progress_callback(deadline, "put /tmp/x")
    # No raise expected for a few quick calls.
    for i in range(100):
        cb(i * 4096, 409600)


def test_cli_exposes_transfer_timeout_flag():
    """`--transfer-timeout` and `--cmd-timeout` must default to sane values
    and be override-able via the CLI.

    Note: global flags (--transfer-timeout, --cmd-timeout, --session, ...)
    are parsed before the subcommand, mirroring --session's contract.
    """
    from ssh_ops import _build_parser

    parser = _build_parser()

    # defaults — exec subcommand exposes cmd_timeout
    args = parser.parse_args(["exec", "ls"])
    assert args.cmd_timeout == 600
    assert args.transfer_timeout == 600

    # override --transfer-timeout (global flag, before subcommand)
    args = parser.parse_args([
        "--transfer-timeout", "30",
        "upload", "--local", "x", "--remote", "/tmp/x",
    ])
    assert args.transfer_timeout == 30

    # override --cmd-timeout (global flag, before subcommand)
    args = parser.parse_args(["--cmd-timeout", "5", "exec", "sleep 1"])
    assert args.cmd_timeout == 5