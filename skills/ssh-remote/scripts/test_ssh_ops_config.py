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