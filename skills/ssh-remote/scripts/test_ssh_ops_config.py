"""Unit tests for ssh_ops.py config management.

Run with:
    cd C:/Users/2268/.claude/skills/ssh-remote
    python -m pytest scripts/test_ssh_ops_config.py -v

These tests use a temporary config directory to avoid touching the user's
real ~/.config/ssh-remote_config.json.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ssh_ops import (
    _cfg_path,
    _config_dir,
    _default_cfg,
    _ensure_cfg,
    _save_cfg,
    CONFIG_VERSION,
)


@pytest.fixture
def isolated_cfg(monkeypatch):
    """Provide a temporary config directory and reset SSHR_CONFIG_DIR."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SSHR_CONFIG_DIR", tmp)
        yield Path(tmp)


def test_config_dir_respects_env_var(isolated_cfg):
    assert _config_dir() == isolated_cfg
    assert _cfg_path() == isolated_cfg / "ssh_remote_config.json"


def test_ensure_cfg_creates_default(isolated_cfg):
    cfg = _ensure_cfg()
    assert cfg["version"] == CONFIG_VERSION
    assert cfg["hosts"] == {}
    assert cfg["environment"] == {}
    assert (_cfg_path()).exists()


def test_save_and_load_roundtrip(isolated_cfg):
    cfg = _default_cfg()
    cfg["hosts"]["lab"] = {
        "host": "192.168.1.1",
        "port": 22,
        "user": "root",
        "password": "secret",
        "auth": {"type": "password"},
        "environment": "lab",
        "label": "test",
        "tags": [],
        "constraints": {},
        "created": "2026-06-30T00:00:00",
        "last_used": "",
    }
    _save_cfg(cfg)

    loaded = _ensure_cfg()
    assert loaded["hosts"]["lab"]["password"] == "secret"
    assert loaded["hosts"]["lab"]["host"] == "192.168.1.1"


def test_corrupted_config_exits(isolated_cfg):
    cfg_path = _cfg_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("not json", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        _ensure_cfg()
    assert exc_info.value.code == 17


def test_save_cfg_writes_password_in_plaintext(isolated_cfg):
    cfg = _default_cfg()
    cfg["hosts"]["x"] = {
        "host": "1.2.3.4",
        "port": 22,
        "user": "u",
        "password": "PlainTextPassword",
        "auth": {"type": "password"},
        "environment": "",
        "label": "",
        "tags": [],
        "constraints": {},
        "created": "2026-06-30T00:00:00",
        "last_used": "",
    }
    _save_cfg(cfg)

    raw = _cfg_path().read_text(encoding="utf-8")
    assert "PlainTextPassword" in raw


def test_save_cfg_cleans_up_tmp_on_failure(isolated_cfg, monkeypatch):
    """If json.dump blows up, the .tmp sidecar must not be left behind."""
    from ssh_ops import _save_cfg

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("ssh_ops.json.dump", boom)
    cfg = _default_cfg()
    with pytest.raises(RuntimeError):
        _save_cfg(cfg)
    tmp = _cfg_path().with_suffix(_cfg_path().suffix + ".tmp")
    assert not tmp.exists(), f"leftover tmp file: {tmp}"


def test_resolve_target_does_not_touch_last_used_on_session_lookup(isolated_cfg):
    """Audit fix A1: last_used + _save_cfg must NOT fire on _resolve_target.

    Previously the lookup itself wrote last_used and persisted the config,
    which meant constraint-rejected requests still mutated config state.
    """
    from ssh_ops import _resolve_target

    cfg = _ensure_cfg()
    cfg["hosts"]["h1"] = {
        "host": "10.0.0.1",
        "port": 22,
        "user": "root",
        "password": "secret",
        "auth": {"type": "password"},
        "environment": "",
        "label": "",
        "tags": [],
        "constraints": {},
        "created": "2026-06-30T00:00:00",
        "last_used": "",
    }
    _save_cfg(cfg)

    initial_mtime = _cfg_path().stat().st_mtime_ns
    args = type(
        "A",
        (),
        {
            "session": "h1",
            "host": None,
            "user": None,
            "port": 22,
            "label": "",
            "password": None,
            "key_file": None,
        },
    )()
    target = _resolve_target(args)
    assert target["host"] == "10.0.0.1"
    # last_used must remain empty AND the config file must not have been
    # rewritten (mtime unchanged) just for session lookup.
    reloaded = _ensure_cfg()
    assert reloaded["hosts"]["h1"]["last_used"] == ""
    assert _cfg_path().stat().st_mtime_ns == initial_mtime


def test_touch_last_used_persists_and_handles_empty_alias(isolated_cfg):
    """_touch_last_used must write a timestamp and silently no-op on empty alias."""
    from ssh_ops import _touch_last_used, _now_iso

    cfg = _ensure_cfg()
    cfg["hosts"]["h1"] = {
        "host": "10.0.0.1",
        "port": 22,
        "user": "root",
        "password": "secret",
        "auth": {"type": "password"},
        "environment": "",
        "label": "",
        "tags": [],
        "constraints": {},
        "created": "2026-06-30T00:00:00",
        "last_used": "",
    }
    _save_cfg(cfg)

    _touch_last_used(cfg, "h1")
    after = _ensure_cfg()["hosts"]["h1"]["last_used"]
    assert after, "last_used must be populated"
    assert after != "", "last_used must not be empty string"

    # empty alias: must not raise and must not mutate the file
    before = _cfg_path().stat().st_mtime_ns
    _touch_last_used(cfg, "")
    assert _cfg_path().stat().st_mtime_ns == before


def test_bool_flag_accepts_true_false_variants():
    """Audit fix B9: --network-isolated must be able to express both True and False."""
    from ssh_ops import _bool_flag

    for v in ("true", "True", "1", "yes", "y", "on", "YES"):
        assert _bool_flag(v) is True, v
    for v in ("false", "False", "0", "no", "n", "off", "NO"):
        assert _bool_flag(v) is False, v
    import argparse
    for v in ("maybe", "enabled", ""):
        with pytest.raises(argparse.ArgumentTypeError):
            _bool_flag(v)


def test_session_add_network_isolated_can_be_disabled(isolated_cfg):
    """Re-running session add with --network-isolated false must clear the flag."""
    import argparse
    from ssh_ops import _build_parser, _ensure_cfg

    parser = _build_parser()

    args = parser.parse_args([
        "session", "add", "h1",
        "--host", "10.0.0.1", "--user", "root", "--password", "pw",
        "--network-isolated", "true",
    ])
    assert args.func is not None
    args.func(args)
    assert _ensure_cfg()["hosts"]["h1"]["constraints"]["network_isolated"] is True

    # Now disable it
    args2 = parser.parse_args([
        "session", "add", "h1",
        "--host", "10.0.0.1", "--user", "root", "--password", "pw",
        "--network-isolated", "false",
    ])
    args2.func(args2)
    assert _ensure_cfg()["hosts"]["h1"]["constraints"]["network_isolated"] is False


def test_argparse_rejects_invalid_bool_for_network_isolated(isolated_cfg):
    """--network-isolated must reject garbage like 'maybe' instead of silently
    becoming True (the old lambda *only* accepted truthy strings)."""
    from ssh_ops import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "session", "add", "h1",
            "--host", "10.0.0.1", "--user", "root", "--password", "pw",
            "--network-isolated", "maybe",
        ])