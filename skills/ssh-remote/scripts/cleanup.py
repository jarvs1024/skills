from __future__ import annotations

import shutil
import secrets
import stat
import time
from pathlib import Path, PurePosixPath
from typing import Any, List

_DENY_PREFIXES = frozenset({
    "/etc", "/usr", "/var", "/bin", "/sbin", "/lib", "/lib64",
    "/boot", "/proc", "/sys", "/dev", "/home", "/root",
})


def run_id() -> str:
    return f"ssh-remote-{int(time.time() * 1000)}-{secrets.token_hex(2)}"


def is_safe_to_delete(path: str) -> bool:
    """Return True only if the path is under an obviously temporary location.

    Remote paths (starting with '/') must be under /tmp/.
    Local paths must not be Windows system directories or the user home itself.
    """
    if path.startswith("/"):
        # Remote POSIX path: must be under /tmp/
        p = PurePosixPath(path)
        if len(p.parts) <= 1:
            return False
        if ".." in p.parts:
            return False
        s = str(p)
        if not s.startswith("/tmp/"):
            return False
        for prefix in _DENY_PREFIXES:
            if s.startswith(prefix + "/") or s == prefix:
                return False
        return True
    # Local path: Windows-aware safety checks
    p = Path(path).expanduser().resolve()
    if len(p.parts) <= 1:
        return False
    if ".." in p.parts:
        return False
    s = str(p)
    lower = s.lower()
    # Reject user home directory itself
    try:
        home = str(Path.home().resolve())
        if s == home or lower == home.lower():
            return False
    except Exception:
        pass
    # Reject Windows system directories
    for sys_dir in (
        "c:\\windows", "c:\\program files", "c:\\program files (x86)",
        "c:\\users\\all users", "c:\\users\\public", "c:\\users\\default",
        "c:\\perflogs", "c:\\programdata",
    ):
        if lower == sys_dir or lower.startswith(sys_dir + "\\"):
            return False
    return True


class CleanupRegistry:
    def __init__(self) -> None:
        self.local_paths: List[Path] = []
        self.remote_paths: List[tuple[Any, str]] = []
        self.dry_run: bool = False

    def add_local(self, path: Path | str) -> None:
        self.local_paths.append(Path(path).expanduser().resolve())

    def add_remote(self, client, remote_path: str) -> None:
        self.remote_paths.append((client, remote_path))

    def cleanup(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._cleanup_remote()
        self._cleanup_local()

    def _cleanup_remote(self) -> None:
        for client, remote_path in self.remote_paths:
            if not is_safe_to_delete(remote_path):
                print(f"[WARN] refusing to clean remote system path: {remote_path}")
                continue
            if self.dry_run:
                print(f"[DRY-RUN] would clean remote: {remote_path}")
                continue
            try:
                sftp = client.open_sftp()
                _sftp_rm_r(sftp, remote_path)
                sftp.close()
                print(f"[CLEANUP] remote: {remote_path}")
            except Exception as exc:
                print(f"[WARN] failed to clean remote {remote_path}: {exc}")

    def _cleanup_local(self) -> None:
        for p in reversed(self.local_paths):
            if not is_safe_to_delete(str(p)):
                print(f"[WARN] refusing to clean local system path: {p}")
                continue
            if self.dry_run:
                print(f"[DRY-RUN] would clean local: {p}")
                continue
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                print(f"[CLEANUP] local: {p}")
            except Exception as exc:
                print(f"[WARN] failed to clean local {p}: {exc}")


def _sftp_rm_r(sftp, remote_path: str) -> None:
    try:
        sftp.remove(remote_path)
    except IOError:
        for entry in sftp.listdir_attr(remote_path):
            child = remote_path.rstrip("/") + "/" + entry.filename
            if stat.S_ISDIR(entry.st_mode):
                _sftp_rm_r(sftp, child)
            else:
                try:
                    sftp.remove(child)
                except IOError:
                    pass
        sftp.rmdir(remote_path)

