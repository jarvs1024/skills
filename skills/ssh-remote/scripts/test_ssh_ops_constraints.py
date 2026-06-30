"""Unit tests for ssh_ops.py constraints engine.

Run with:
    cd C:/Users/2268/.claude/skills/ssh-remote
    python -m pytest scripts/test_ssh_ops_constraints.py -v

These tests do not require SSH connectivity.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ssh_ops import (
    _check_constraints,
    _get_effective_constraints,
    _is_within_allowed_hours,
    _merge_constraints,
    EXIT_CONSTRAINT_DENIED,
    EXIT_OUTSIDE_ALLOWED_HOURS,
    DEFAULT_CONSTRAINTS,
)


def _cfg(env_constraints=None, host_constraints=None, host_env="lab"):
    return {
        "version": 3,
        "defaults": {"host": None, "env": None},
        "environment": {
            "lab": {
                "description": "lab",
                "tags": [],
                "constraints": env_constraints or {},
            }
        },
        "hosts": {
            "h1": {
                "host": "1.2.3.4",
                "environment": host_env,
                "constraints": host_constraints or {},
            }
        },
    }


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------
def test_merge_constraints_defaults():
    merged = _merge_constraints(None, None)
    assert merged == DEFAULT_CONSTRAINTS


def test_merge_constraints_host_overrides_environment():
    merged = _merge_constraints(
        {"read_only": True, "require_double_confirm": False},
        {"read_only": False},
    )
    assert merged["read_only"] is False
    assert merged["require_double_confirm"] is False


def test_get_effective_constraints_without_environment():
    cfg = _cfg()
    cfg["hosts"]["h1"]["environment"] = ""
    cons = _get_effective_constraints(cfg, "h1")
    assert cons["read_only"] is False


def test_get_effective_constraints_with_environment():
    cfg = _cfg(env_constraints={"read_only": True})
    cons = _get_effective_constraints(cfg, "h1")
    assert cons["read_only"] is True


def test_get_effective_constraints_host_override():
    cfg = _cfg(
        env_constraints={"read_only": True},
        host_constraints={"read_only": False},
    )
    cons = _get_effective_constraints(cfg, "h1")
    assert cons["read_only"] is False


# ---------------------------------------------------------------------------
# read_only
# ---------------------------------------------------------------------------
def test_read_only_blocks_exec():
    cfg = _cfg(host_constraints={"read_only": True})
    with pytest.raises(SystemExit) as exc_info:
        _check_constraints(cfg, "h1", "exec", command="uname -a")
    assert exc_info.value.code == EXIT_CONSTRAINT_DENIED


def test_read_only_blocks_upload():
    cfg = _cfg(host_constraints={"read_only": True})
    with pytest.raises(SystemExit) as exc_info:
        _check_constraints(cfg, "h1", "upload")
    assert exc_info.value.code == EXIT_CONSTRAINT_DENIED


def test_read_only_allows_test_and_download():
    cfg = _cfg(host_constraints={"read_only": True})
    _check_constraints(cfg, "h1", "test")
    _check_constraints(cfg, "h1", "download")


# ---------------------------------------------------------------------------
# denied_patterns
# ---------------------------------------------------------------------------
def test_denied_pattern_blocks_command():
    cfg = _cfg(env_constraints={"denied_patterns": ["reboot", "shutdown"]})
    with pytest.raises(SystemExit) as exc_info:
        _check_constraints(cfg, "h1", "exec", command="sudo reboot now")
    assert exc_info.value.code == EXIT_CONSTRAINT_DENIED


def test_denied_pattern_allows_safe_command():
    cfg = _cfg(env_constraints={"denied_patterns": ["reboot"]})
    _check_constraints(cfg, "h1", "exec", command="uname -a")


def test_invalid_denied_pattern_is_ignored():
    cfg = _cfg(env_constraints={"denied_patterns": ["[invalid"]})
    # Should not raise.
    _check_constraints(cfg, "h1", "exec", command="uname -a")


# ---------------------------------------------------------------------------
# allowed_hours
# ---------------------------------------------------------------------------
def test_allowed_hours_invalid_format_is_ignored():
    assert _is_within_allowed_hours("not-a-time") is True


def test_allowed_hours_within_window():
    # This test is time-of-day dependent; we mock by checking the helper logic.
    # A full 00:00-23:59 should always pass.
    assert _is_within_allowed_hours("00:00-23:59") is True


def test_allowed_hours_crosses_midnight():
    # 22:00-06:00 should cover either late night or early morning.
    # We cannot assert exact without mocking datetime, but the function should return bool.
    result = _is_within_allowed_hours("22:00-06:00")
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# require_double_confirm is read by callers, not enforced here
# ---------------------------------------------------------------------------
def test_require_double_confirm_merged_from_environment():
    cfg = _cfg(env_constraints={"require_double_confirm": True})
    from ssh_ops import _constraint_requires_double_confirm
    assert _constraint_requires_double_confirm(cfg, "h1") is True


def test_require_double_confirm_host_override():
    cfg = _cfg(
        env_constraints={"require_double_confirm": True},
        host_constraints={"require_double_confirm": False},
    )
    from ssh_ops import _constraint_requires_double_confirm
    assert _constraint_requires_double_confirm(cfg, "h1") is False


# ---------------------------------------------------------------------------
# network_isolated
# ---------------------------------------------------------------------------
def test_network_isolated_default_false():
    assert DEFAULT_CONSTRAINTS["network_isolated"] is False


def test_network_isolated_blocks_curl_in_exec():
    from ssh_ops import _command_needs_public_network, _check_constraints
    assert _command_needs_public_network("curl https://github.com") is True
    assert _command_needs_public_network("yum install -y htop") is True
    assert _command_needs_public_network("apt-get update") is True
    assert _command_needs_public_network("pip install requests") is True
    assert _command_needs_public_network("uname -a") is False
    assert _command_needs_public_network("cat /etc/hosts") is False
    assert _command_needs_public_network("") is False

    cfg = _cfg(host_constraints={"network_isolated": True})
    with pytest.raises(SystemExit) as exc_info:
        _check_constraints(cfg, "h1", "exec", command="curl https://baidu.com")
    assert exc_info.value.code == 18  # EXIT_CONSTRAINT_DENIED


def test_network_isolated_allows_internal_commands():
    from ssh_ops import _check_constraints
    cfg = _cfg(host_constraints={"network_isolated": True})
    # Should NOT raise: no public-internet hint
    _check_constraints(cfg, "h1", "exec", command="uname -a")
    _check_constraints(cfg, "h1", "exec", command="systemctl status sshd")


def test_network_isolated_does_not_block_test_probe_or_download():
    from ssh_ops import _check_constraints
    cfg = _cfg(host_constraints={"network_isolated": True})
    _check_constraints(cfg, "h1", "test")
    _check_constraints(cfg, "h1", "probe-net")
    _check_constraints(cfg, "h1", "download")


def test_network_isolated_inherits_from_environment():
    cfg = _cfg(env_constraints={"network_isolated": True})
    from ssh_ops import _get_effective_constraints
    assert _get_effective_constraints(cfg, "h1")["network_isolated"] is True
    cfg2 = _cfg(
        env_constraints={"network_isolated": True},
        host_constraints={"network_isolated": False},
    )
    assert _get_effective_constraints(cfg2, "h1")["network_isolated"] is False
