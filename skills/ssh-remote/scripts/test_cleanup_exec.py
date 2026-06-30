from pathlib import Path
from unittest.mock import MagicMock, patch

import ssh_ops


def test_exec_creates_and_registers_remote_staging():
    args = MagicMock()
    args.command = "echo ok"
    args.session = "lab"
    args._run_id = "ssh-remote-abc123"
    args.remote_staging_dir = "/tmp"
    args.local_staging_dir = str(Path.home() / ".ssh-remote" / "tmp")
    args.timeout = 15
    args.cmd_timeout = 600
    registry = MagicMock()
    args._registry = registry

    fake_client = MagicMock()

    with patch.object(ssh_ops, "_ensure_cfg", return_value={}), \
         patch.object(ssh_ops, "_resolve_target", return_value={"session": "lab", "host": "1.2.3.4", "port": 22, "user": "tester"}), \
         patch.object(ssh_ops, "_check_constraints", return_value=None), \
         patch.object(ssh_ops, "_classify_exec_risk", return_value=(None, None)), \
         patch.object(ssh_ops, "_confirm_host", return_value=None), \
         patch.object(ssh_ops, "_confirm_high_risk", return_value=None), \
         patch.object(ssh_ops, "_constraint_requires_double_confirm", return_value=False), \
         patch.object(ssh_ops, "_build_client", return_value=fake_client), \
         patch.object(ssh_ops, "_run_and_print", return_value=0) as mock_run, \
         patch.object(ssh_ops, "_touch_last_used", return_value=None):
        rc = ssh_ops.cmd_exec(args)
        assert rc == 0
        assert mock_run.call_count == 2
        first_call = mock_run.call_args_list[0]
        assert first_call.args[1].startswith("mkdir -p")
        assert "/tmp/ssh-remote-abc123" in first_call.args[1]
        second_call = mock_run.call_args_list[1]
        assert second_call.args[1] == "echo ok"
        assert second_call.kwargs.get("env", {}).get("SSH_REMOTE_TMP") == "/tmp/ssh-remote-abc123"
        registry.add_remote.assert_called_once_with(fake_client, "/tmp/ssh-remote-abc123")
