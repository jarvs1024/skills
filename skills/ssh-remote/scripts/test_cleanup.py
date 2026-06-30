from cleanup import CleanupRegistry, is_safe_to_delete, run_id

def test_run_id_is_unique():
    a, b = run_id(), run_id()
    assert a != b
    assert a.startswith("ssh-remote-")

def test_is_safe_to_delete_rejects_system_paths():
    assert not is_safe_to_delete("/")
    assert not is_safe_to_delete("/etc")
    assert not is_safe_to_delete("/home/user")
    assert not is_safe_to_delete("/root")

def test_is_safe_to_delete_allows_temp_paths():
    assert is_safe_to_delete("/tmp/ssh-remote-abc123")

def test_cleanup_registry_local_paths(tmp_path):
    p = tmp_path / "junk.txt"
    p.write_text("x")
    reg = CleanupRegistry()
    reg.add_local(p)
    reg.cleanup()
    assert not p.exists()
