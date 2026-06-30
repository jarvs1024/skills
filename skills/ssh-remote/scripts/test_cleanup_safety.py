from pathlib import Path
from unittest.mock import MagicMock

from cleanup import CleanupRegistry, is_safe_to_delete, run_id


def test_is_safe_to_delete_rejects_parent_traversal():
    assert not is_safe_to_delete("/tmp/abc/../etc")


def test_is_safe_to_delete_rejects_non_tmp_remote():
    assert not is_safe_to_delete("/opt/staging")
    assert not is_safe_to_delete("/var/tmp/abc")
    assert not is_safe_to_delete("/home/user/transfer")


def test_is_safe_to_delete_rejects_windows_system_dirs():
    assert not is_safe_to_delete(r"C:\Windows")
    assert not is_safe_to_delete(r"C:\Windows\System32")
    assert not is_safe_to_delete(r"C:\Program Files")
    assert not is_safe_to_delete(r"C:\Program Files (x86)")


def test_is_safe_to_delete_rejects_user_home():
    assert not is_safe_to_delete(str(Path.home()))


def test_is_safe_to_delete_allows_windows_local_staging():
    p = Path.home() / ".ssh-remote" / "tmp" / run_id()
    assert is_safe_to_delete(str(p))


def test_registry_skips_unsafe_system_paths_during_cleanup(capsys):
    """Registry.add_remote should record, but cleanup() should refuse to remove /etc."""
    reg = CleanupRegistry()
    reg.add_remote(MagicMock(), "/etc")
    reg.add_local(Path(r"C:\Windows"))
    reg.cleanup()
    captured = capsys.readouterr().out
    assert "refusing to clean" in captured
