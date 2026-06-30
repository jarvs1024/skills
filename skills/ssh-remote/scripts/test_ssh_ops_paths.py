"""Unit tests for ssh_ops.py — focused on _normalize_remote_path.

Run with:
    cd C:/Users/2268/.claude/skills/ssh-remote
    python -m pytest scripts/test_ssh_ops_paths.py -v

These tests do not require SSH connectivity; they only exercise the
path-validation helper that protects against the Git Bash MSYS path
mangling bug discovered on 2026-06-29.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
SSH_OPS = HERE / "ssh_ops.py"


def _run_ssh_ops(*args, env_overrides=None):
    """Invoke ssh_ops.py as a subprocess so that argparse and
    MSYS path-mangling happen in the same way as a real invocation.
    Returns CompletedProcess.
    """
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SSH_OPS), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_normalize_simple_absolute_path():
    """A normal POSIX absolute path is returned normalized."""
    from ssh_ops import _normalize_remote_path
    assert _normalize_remote_path("/opt/ragflow") == "/opt/ragflow"


def test_normalize_collapses_trailing_slash():
    from ssh_ops import _normalize_remote_path
    assert _normalize_remote_path("/opt/ragflow/") == "/opt/ragflow"


def test_normalize_keeps_root():
    from ssh_ops import _normalize_remote_path
    assert _normalize_remote_path("/") == "/"


def test_normalize_preserves_dotdot_lexically():
    """PurePosixPath normalizes lexically but does NOT resolve ../
    against the filesystem (no FS access). This test pins that behavior
    so future maintainers know not to add realpath()-like semantics."""
    from ssh_ops import _normalize_remote_path
    # PurePosixPath keeps /opt/foo from /opt/ragflow/../foo lexically.
    assert _normalize_remote_path("/opt/ragflow/../foo") == "/opt/ragflow/../foo"


# ---------------------------------------------------------------------------
# Mangled-path rejection
# ---------------------------------------------------------------------------

def test_normalize_rejects_windows_drive_letter():
    """`C:/foo` must be rejected — that's the smoking gun of MSYS conversion."""
    from ssh_ops import _normalize_remote_path
    with pytest.raises(SystemExit) as exc_info:
        _normalize_remote_path("C:/Program Files/Git/opt/foo")
    assert exc_info.value.code == 2


def test_normalize_rejects_backslash_path():
    """A backslash anywhere means conversion already happened."""
    from ssh_ops import _normalize_remote_path
    with pytest.raises(SystemExit) as exc_info:
        _normalize_remote_path("\\tmp\\foo")
    assert exc_info.value.code == 2


def test_normalize_rejects_relative_path():
    from ssh_ops import _normalize_remote_path
    with pytest.raises(SystemExit) as exc_info:
        _normalize_remote_path("tmp/foo")
    assert exc_info.value.code == 2


def test_normalize_rejects_empty_path():
    from ssh_ops import _normalize_remote_path
    with pytest.raises(SystemExit) as exc_info:
        _normalize_remote_path("")
    assert exc_info.value.code == 2


def test_normalize_hint_mentions_msys():
    """The error message must guide Windows users to MSYS_NO_PATHCONV."""
    from ssh_ops import _normalize_remote_path, _print_msys_hint
    import io
    from contextlib import redirect_stderr

    buf = io.StringIO()
    with redirect_stderr(buf):
        try:
            _normalize_remote_path("C:/Users/foo")
        except SystemExit:
            pass
    text = buf.getvalue()
    assert "MSYS_NO_PATHCONV" in text, f"hint missing MSYS_NO_PATHCONV: {text!r}"
    assert "MSYS2_ARG_CONV_EXCL" in text, f"hint missing MSYS2_ARG_CONV_EXCL: {text!r}"


# ---------------------------------------------------------------------------
# End-to-end: subprocess invocation under simulated MSYS
# ---------------------------------------------------------------------------

def test_upload_rejects_mangled_path_under_default_git_bash():
    """Simulate the bug: Windows path sneaking in via --remote.

    We pass `--remote C:/Users/fake/Tmp/x.txt` as a command-line arg
    to `upload`. Argparse only knows the top-level flags (--session,
    --host, --yes, etc.), so subcommand flags like --remote go through
    to argparse. To make argparse happy we pass --host/--user/--port
    at the top level so it doesn't reject the subcommand line."""
    result = _run_ssh_ops(
        "--host", "10.20.30.40",
        "--user", "fake",
        "--port", "22",
        "--password", "fake",
        "--yes",
        "upload",
        "--local", str(HERE / "ssh_ops.py"),
        "--remote", "C:/Users/fake/Tmp/x.txt",
    )
    assert result.returncode == 2, (
        f"expected exit 2, got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "Windows path" in combined or "MSYS" in combined, (
        f"missing diagnostic in output: {combined!r}"
    )


def test_upload_rejects_backslash_path():
    result = _run_ssh_ops(
        "--host", "10.20.30.40",
        "--user", "fake",
        "--port", "22",
        "--password", "fake",
        "--yes",
        "upload",
        "--local", str(HERE / "ssh_ops.py"),
        "--remote", "\\tmp\\x.txt",
    )
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "backslash" in combined.lower()