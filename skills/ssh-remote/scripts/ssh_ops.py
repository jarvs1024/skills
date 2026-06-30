#!/usr/bin/env python3
"""ssh-remote skill v3 — SSH operations with ~/.config based host management.

Configuration
-------------
Default config path: ~/.config/ssh_remote_config.json
Override with: $SSHR_CONFIG_DIR or $XDG_CONFIG_HOME

The config is a JSON file with the following top-level keys:
  - version: 3
  - defaults: {"host": "alias", "env": "env-name"}
  - environments: mapping env-name -> {description, tags, constraints}
  - hosts: mapping alias -> {host, port, user, password, auth, environment,
                             label, tags, constraints, created, last_used}

Passwords are stored as plain text in the config file. On POSIX the file is
created with mode 0600. On Windows an ACL restriction is attempted and a
warning is emitted on failure.

Constraints
-----------
Constraints can be defined per environment and overridden per host:
  - read_only:        forbid exec and upload on this host/env.
  - require_double_confirm: require host confirm + one-time token for every exec.
  - denied_patterns:  list of regex strings; matching commands are rejected.
  - allowed_hours:    "HH:MM-HH:MM" local-time window for exec/upload.
  - network_isolated: bool, default false. If true, the host is assumed to live
    in an internal / air-gapped network. Commands that obviously need public
    Internet access (curl/wget/yum/apt/dnf/pip/npm install, etc.) are
    rejected; probe-net and any explicit `curl <public-host>` are also blocked.

Passwords
---------
Passwords are resolved in this order:
  1. --password CLI argument
  2. hosts[alias].password in the config file
If neither is set and the host has no --key-file, the command exits with usage
error. Environment variables (SSH_PASSWORD / SSH_PASSWORD_<ALIAS>) are no
longer read — configure the password in the JSON file instead.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

# Optional dependency: paramiko is required only when connecting.
try:
    import paramiko
except Exception as _exc:  # pragma: no cover
    paramiko = None


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
CONFIG_VERSION = 3

# Exit codes
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SESSION_NOT_FOUND = 14
EXIT_HOST_CONFIRM_DECLINED = 15
EXIT_HIGH_RISK_DECLINED = 16
EXIT_CONFIG_CORRUPTED = 17
EXIT_CONSTRAINT_DENIED = 18
EXIT_OUTSIDE_ALLOWED_HOURS = 19
EXIT_NETWORK_ISOLATED_PROBE = 20  # probe-net refused on a network_isolated host
EXIT_CONNECTION_FAILED = 10
EXIT_SSH_ERROR = 11
EXIT_AUTH_FAILED = 13

DANGEROUS_REMOTE_PATHS = (
    "/etc", "/var", "/usr", "/boot", "/proc", "/sys", "/dev",
    "/lib", "/lib64", "/opt", "/root", "/bin", "/sbin",
)

# Default constraint values
DEFAULT_CONSTRAINTS = {
    "read_only": False,
    "require_double_confirm": False,
    "denied_patterns": [],
    "allowed_hours": None,
    "network_isolated": False,
}

# Patterns that obviously require public Internet access. Used by the
# network_isolated guard. Matched as plain substrings (case-insensitive) so
# `yum install`, `curl http://...`, `apt-get update` etc. all trip.
PUBLIC_NETWORK_PATTERNS = [
    r"\bcurl\b",
    r"\bwget\b",
    r"\bhttpie\b",
    r"\blynx\b",
    r"\bw3m\b",
    r"\bnc\s+-",
    r"\bncat\b",
    r"\bssh\s+-",
    r"\bscp\s+",
    r"\brsync\s+",
    r"\bgit\s+(?:clone|pull|fetch|push|ls-remote)\b",
    r"\bapt(?:-get)?\b",
    r"\bdnf\b",
    r"\byum\b",
    r"\bmicrodnf\b",
    r"\bapk\b",
    r"\bpacman\b",
    r"\bzypper\b",
    r"\bbrew\b",
    r"\bpip3?\s+install\b",
    r"\bpipx\b",
    r"\bpoetry\s+(?:add|install|update)\b",
    r"\bconda\s+(?:install|create|update)\b",
    r"\bnpm\s+(?:install|i|add|update|publish)\b",
    r"\byarn\s+(?:add|install)\b",
    r"\bpnpm\s+(?:add|install)\b",
    r"\bgo\s+(?:install|get)\b",
    r"\bcargo\s+(?:install|update)\b",
    r"\bgem\s+install\b",
    r"\bcomposer\s+(?:install|require|update)\b",
    r"\bterraform\s+init\b",
    r"\bansible-galaxy\s+install\b",
    r"\bdocker\s+pull\b",
    r"\bdocker\s+push\b",
    r"\bhelm\s+(?:install|upgrade|pull|repo\s+add)\b",
    r"\bkubectl\s+apply\b",
    r"\bping\b",
    r"\btraceroute\b",
    r"\bnslookup\b",
    # 'host' is matched only when invoked as a DNS-query command (bare token + a hostname).
    # Previously the bare \bhost\b pattern was a notorious false-positive on --host/--bind
    # flags, /etc/hosts paths, hostname(1) arguments, etc.
    r"(?:^|\s|;|\||&)host\s+[A-Za-z0-9._-]+\b",
    r"\bwhois\b",
    r"\bntpdate\b",
]

# High-risk command patterns: (regex, level, reason).
# CRITICAL patterns are listed first so they win over general patterns.
HIGH_RISK_PATTERNS = [
    # === CRITICAL (system-destroying / non-recoverable) === #

    # rm against root or top-level system dirs
    (r"\brm\b[^|;&]*\s+/\*\s*$", "critical", "rm /* (deletes root filesystem)"),
    (r"\brm\b[^|;&]*\s+/\.(?:\s|$|;|\||&)", "critical", "rm /. (root)"),
    (r"\brm\b[^|;&]*\s+/(?:etc|var|usr|boot|home|root|lib|opt|bin|sbin|sys|proc|dev|tmp|mnt|media|srv|run)(?:[/\s\)\;\|\&]|$)", "critical", "rm against top-level system path"),
    (r"\brm\b[^|;&]*\s+/etc/(?:passwd|shadow|sudoers|hosts|fstab|resolv\.conf|ssh/sshd_config)", "critical", "rm critical system file"),

    # dd to/from raw disk devices
    (r"\bdd\b[^|;&]*\bof=/dev/(?:sd|hd|nvme|vd|mmcblk|xvd|loop|disk|zd|nbd|dasd)", "critical", "dd writing to raw disk device"),
    (r"\bdd\b[^|;&]*\bif=/dev/(?:sd|hd|nvme|vd|mmcblk|xvd|loop|disk|zd|nbd|dasd)", "critical", "dd reading from raw disk device"),

    # Direct write/cat/echo to disk devices
    (r"(?:>|>>|tee)\s*/dev/(?:sd|hd|nvme|vd|mmcblk|xvd|loop|disk|zd|nbd|dasd)", "critical", "redirect to raw disk device"),
    (r"\b(?:cat|echo|dd)\b[^|;&]*\s+>?\s*/dev/(?:sd|hd|nvme|vd|mmcblk|xvd|loop|disk|zd|nbd|dasd)", "critical", "cat/echo/dd to raw disk"),

    # Format disk
    (r"\bmkfs(?:\.\w+)?\b[^|;&]*\s+/dev/(?:sd|hd|nvme|vd|mmcblk|xvd|loop|disk|zd|nbd|dasd)", "critical", "format raw disk device"),
    (r"\b(?:fdisk|sfdisk|parted|wipefs)\b[^|;&]*\s+/dev/(?:sd|hd|nvme|vd|mmcblk|xvd|loop|disk|zd|nbd|dasd)", "critical", "partition table edit on raw disk"),

    # Truncate / shred device
    (r"\b(?:truncate|shred)\b[^|;&]*\s+/dev/", "critical", "truncate/shred on device"),

    # chmod 000 or 777 on /
    (r"\bchmod\b[^|;&]*\s+(?:-R\s+)?0+\s+/(?:\s|$|;|\||&)", "critical", "chmod 000 on root"),
    (r"\bchmod\b[^|;&]*\s+(?:-R\s+)?0?777\s+/(?:\s|$|;|\||&)", "critical", "chmod 777 on root"),

    # mv root contents
    (r"\bmv\b[^|;&]*\s+/*", "critical", "mv root contents"),
    (r"\bmv\b[^|;&]*\s+/\.", "critical", "mv /."),
    (r"\bmv\b[^|;&]*\s+/(?:home|var|usr|opt|root)(?:[\s/]|;|\||&|$)", "high", "mv against user/system data dir"),

    # Fork bomb and similar
    (r":\s*\(\s*\)\s*\{[^}]*:\s*\|", "critical", "fork bomb signature"),
    # rm root (no glob, no subdir) - the classic catastrophe
    (r"\brm\b[^|;&]*\s+-?\w*[rf]\w*[^|;&]*\s+/(?:\s|;|\||&|`|$)", "critical", "rm / (deletes root)"),
    (r"\brm\b[^|;&]*--no-preserve-root", "critical", "rm with --no-preserve-root"),

    # SUID / SGID bit on common privilege-escalation binaries
    (r"\bchmod\b[^|;&]*\s+[0-7]?[0-7]?[47][0-7]{1,2}\s+/", "critical", "chmod setuid/setgid on binary"),
    (r"\bchmod\b[^|;&]*\s+[ugoa]*[+]?s\b", "critical", "chmod +s (SUID/SGID)"),

    # ACL backdoor
    (r"\bsetfacl\b[^|;&]*\s+-m\b", "critical", "setfacl modify ACL"),

    # >> to boot persistence files
    (r">>\s*/etc/(?:rc\.local|rc\.d/|init\.d/|cron\.|crontab|cron\.d)", "critical", "append to boot/cron persistence"),
    (r">>\s*/etc/profile(?:\.d/)?", "critical", "append to /etc/profile"),
    (r">>\s*~/(?:\.bashrc|\.bash_profile|\.zshrc|\.profile)", "critical", "append to user shell rc"),

    # umount root or all
    (r"\bumount\b[^|;&]*\s+/(?:\s|;|\||&|`|$)", "critical", "umount /"),
    (r"\bumount\b[^|;&]*-a\b", "critical", "umount -a (all)"),


    # === HIGH (destructive but bounded) === #

    # File destruction
    (r"\brm\s+(?:-\w*r\w*|-\w*f\w*|--recursive|--force)", "high", "rm with -r/-f/--recursive/--force"),
    (r"\b(?:shred|truncate|unlink)\b", "high", "destructive file op"),
    (r"\bdd\b[^|;&]*\bof=", "high", "dd writing somewhere"),
    (r"\b(?:mkfs|fdisk|parted|sfdisk|wipefs)\b", "high", "disk formatting tool"),
    (r"\b(?:mkswap|swapoff)\b", "high", "swap manipulation"),
    (r"\bfind\b[^|;&]*-delete", "high", "find -delete"),
    (r"\bfind\b[^|;&]*-exec\s+rm\b", "high", "find -exec rm"),
    (r"\b(?:\.|source)\s+/dev/stdin", "high", "execute from stdin"),

    # System control
    (r"\b(?:systemctl|service)\b[^|;&]*\b(?:stop|disable|mask|restart|reload|kill)", "high", "service control"),
    (r"\b(?:reboot|shutdown|poweroff|halt|init\s+[016])\b", "high", "system power"),
    (r"\b(?:kill|killall|pkill|skill|taskkill)\b", "high", "process termination"),
    (r"\b(?:userdel|groupdel)\b", "high", "user/group deletion"),
    (r">\s*/etc/(?:passwd|shadow|sudoers|hosts|fstab)", "critical", "truncate critical system file"),
    (r"\bpasswd\b", "high", "password change"),
    (r"\busermod\b", "high", "user modification"),
    (r"\bchsh\b", "high", "shell change"),
    (r"\bcrontab\b[^|;&]*-r\b", "high", "remove crontab"),

    # Network / firewall
    (r"\b(?:iptables|nft|ufw|firewall-cmd)\b", "high", "firewall change"),
    (r"\bip\s+(?:link|addr|route)\b[^|;&]*\b(?:del|flush)", "high", "network interface change"),
    (r"\bifdown\b", "high", "interface down"),
    (r"\b(?:dhclient|dhcpcd)\b[^|;&]*-r\b", "high", "DHCP release"),

    # File permissions
    (r"\bchmod\s+(?:-R\s+)?0?777", "high", "chmod world-writable"),
    (r"\bchown\s+-R\b", "high", "recursive chown"),

    # System files via redirection. The previous version was a substring match on
    # ">\s*/opt/" which tripped on innocuous uses like `df -h /opt`, `ls /opt/x`.
    # Now requires the redirect operator to be at a command boundary (start of
    # string, after ; | &, or after a newline-equivalent space after a closing
    # paren/brace).
    (r"(?:(?:^|[|;&]\s*|^\s*)>>?\s*/(?:etc|var|usr|boot|proc|sys|dev|lib|opt|root|bin|sbin)/)", "high", "redirect to system path"),
    (r"\btee\s+/(?:etc|var|usr|boot|proc|sys|dev|lib|opt|root|bin|sbin)/", "high", "tee to system path"),
    (r"(?:(?:^|[|;&]\s*|^\s*)>>?\s*/etc/(?:passwd|shadow|sudoers|hosts|fstab|resolv\.conf))", "high", "redirect to critical system file"),
    (r"(?:(?:^|[|;&]\s*|^\s*)>>?\s*~/\.(?:bash|ssh|aws|kube|netrc|gitconfig|history|profile))", "high", "redirect to user credential/history file"),

    # Time / boot
    (r"\b(?:date|hwclock)\b[^|;&]*-s\b", "high", "time change"),
    (r"\b(?:grub-install|update-grub|grub2-install|grub-mkconfig)\b", "high", "bootloader change"),

    # Piped installs
    (r"\bcurl\b[^|;&]*\|\s*(?:sh|bash|zsh|sudo)\b", "high", "curl | sh"),
    (r"\bwget\b[^|;&]*\|\s*(?:sh|bash|zsh|sudo)\b", "high", "wget | sh"),

    # Database
    (r"\bDROP\s+(?:DATABASE|TABLE|SCHEMA|INDEX)\b", "high", "DDL drop"),
    (r"\bDELETE\s+FROM\b(?![^|;&]*\bWHERE\b)", "high", "DELETE without WHERE"),
    (r"\bTRUNCATE\b", "high", "TRUNCATE"),

    # Git
    (r"\bgit\s+push\b[^|;&]*--force", "high", "git force push"),
    (r"\bgit\s+reset\b[^|;&]*--hard", "high", "git hard reset"),
    (r"\bgit\s+clean\b[^|;&]*-fd?", "high", "git clean"),

    # Init killer
    (r"\bkill\s+-9\s+1\b", "high", "kill init"),

    # Recursive / broad rsync
    (r"\brsync\b[^|;&]*--delete", "high", "rsync with --delete"),

    # Publishing / multi-host automation
    (r"\bnpm\s+publish\b", "high", "npm publish"),
    (r"\btwine\s+upload\b", "high", "twine upload"),
    (r"\bterraform\s+apply\b", "high", "terraform apply"),
    (r"\bansible-playbook\b", "high", "ansible playbook"),
    (r"\b(?:docker|podman)\s+push\b", "high", "container push"),

    # Reverse shell / backdoor patterns
    (r"\bbash\s+-i\s+>&\s*/dev/tcp/", "high", "reverse shell (bash)"),
    (r"\bnc\b[^|;&]*-e\b", "high", "reverse shell (nc -e)"),
    (r"\bpython[23]?\b[^|;&]*-c\b[^|;&]*socket", "high", "python reverse shell"),
    (r"\bperl\b[^|;&]*-e\b[^|;&]*socket", "high", "perl reverse shell"),
    (r"\bphp\b[^|;&]*-r\b[^|;&]*(?:fsockopen|stream_socket_client)", "high", "php reverse shell"),

    # History cover
    (r"\bhistory\s+-c\b", "high", "clear shell history"),

    # Container / orchestration destruction
    (r"\bdocker\b[^|;&]*\bsystem\s+prune\b", "high", "docker system prune"),
    (r"\bdocker\b[^|;&]*\bvolume\s+prune\b", "high", "docker volume prune"),
    (r"\b(?:docker|podman)\b[^|;&]*\brm\s+-[af]+\b", "high", "container force-rm all"),
    (r"\bkubectl\b[^|;&]*\s+delete\s+--all\b", "high", "kubectl delete --all"),

    # Persistence: enable / disable / mask service, install kernel module
    (r"\bsystemctl\b[^|;&]*\b(?:enable|disable|mask)\b", "high", "service persistence change"),
    (r"\b(?:insmod|modprobe|rmmod)\b", "high", "kernel module load/unload"),
    (r"\bcrontab\b[^|;&]*-(?:l|r|e)\b", "high", "crontab read/edit/remove"),
    (r"\bcrontab\b[^|;&]*<<", "high", "crontab heredoc inject"),

    # Service control already CRITICAL for stop; add start/restart as HIGH
    (r"\b(?:systemctl|service)\b[^|;&]*\b(?:start|enable|reload)\b", "high", "service start/enable"),

    # Network reset
    (r"\bip\s+addr\s+flush\b", "high", "ip addr flush"),
    (r"\barp\b[^|;&]*-d\b", "high", "arp delete"),

    # Auth config tamper
    (r">>\s*/etc/(?:passwd|shadow|sudoers|sudoers\.d/|hosts\.allow|hosts\.deny)", "critical", "append to auth/access control file"),
]


# --------------------------------------------------------------------------- #
# Config management
# --------------------------------------------------------------------------- #
def _config_dir() -> Path:
    base = os.environ.get("SSHR_CONFIG_DIR") or os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base)
    if os.name == "nt":
        return Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / ".config"
    return Path.home() / ".config"


def _cfg_path() -> Path:
    return _config_dir() / "ssh_remote_config.json"


def _now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _default_cfg() -> dict:
    return {
        "version": CONFIG_VERSION,
        "defaults": {"host": None, "env": None},
        "environment": {},
        "hosts": {},
    }


def _ensure_cfg() -> dict:
    path = _cfg_path()
    existed = path.exists()
    cfg = _default_cfg()
    if existed:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            sys.stderr.write(f"[ERROR] config file corrupted: {path} ({exc})\n")
            sys.exit(EXIT_CONFIG_CORRUPTED)
        if isinstance(data, dict):
            cfg.update(data)

    cfg["version"] = CONFIG_VERSION
    cfg.setdefault("defaults", {"host": None, "env": None})
    cfg.setdefault("environment", {})
    cfg.setdefault("hosts", {})

    if not existed:
        _save_cfg(cfg)

    _check_cfg_permissions(path)
    return cfg


def _save_cfg(cfg: dict) -> None:
    path = _cfg_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        # Don't leave a half-written tmp file behind on crash / disk-full.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise
    _restrict_cfg_permission(path)


def _restrict_cfg_permission(path: Path) -> None:
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except OSError as exc:
            sys.stderr.write(f"[WARN] could not set config file permissions: {exc}\n")
    elif os.name == "nt":
        try:
            subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{os.environ.get('USERNAME', os.environ.get('USER'))}:(R,W)",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:
            sys.stderr.write(f"[WARN] could not restrict Windows ACL on config: {exc}\n")


def _check_cfg_permissions(path: Path) -> None:
    if not path.exists() or os.name != "posix":
        return
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & 0o077:
        sys.stderr.write(
            f"[WARN] config file is readable by group/others: {path} ({oct(mode & 0o777)})\n"
            "[HINT] run: chmod 600 ~/.config/ssh_remote_config.json\n"
        )


# --------------------------------------------------------------------------- #
# Constraints engine
# --------------------------------------------------------------------------- #
def _merge_constraints(env_constraints: dict | None, host_constraints: dict | None) -> dict:
    merged = dict(DEFAULT_CONSTRAINTS)
    if env_constraints:
        merged.update({k: v for k, v in env_constraints.items() if v is not None})
    if host_constraints:
        merged.update({k: v for k, v in host_constraints.items() if v is not None})
    return merged


def _get_effective_constraints(cfg: dict, alias: str) -> dict:
    host = cfg.get("hosts", {}).get(alias, {})
    env_name = host.get("environment") or cfg.get("defaults", {}).get("env")
    env_constraints = cfg.get("environment", {}).get(env_name, {}).get("constraints", {}) if env_name else {}
    return _merge_constraints(env_constraints, host.get("constraints", {}))


def _is_within_allowed_hours(spec: str | None) -> bool:
    if not spec:
        return True
    match = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", str(spec))
    if not match:
        sys.stderr.write(f"[WARN] invalid allowed_hours format: {spec!r}; ignored\n")
        return True
    sh, sm, eh, em = (int(x) for x in match.groups())
    now = _dt.datetime.now().time()
    start = _dt.time(sh, sm)
    end = _dt.time(eh, em)
    if start <= end:
        return start <= now <= end
    # crosses midnight
    return now >= start or now <= end


def _command_needs_public_network(command: str) -> bool:
    """Return True if the command obviously requires public Internet access."""
    if not command:
        return False
    for pat in PUBLIC_NETWORK_PATTERNS:
        try:
            if re.search(pat, command, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


def _check_constraints(cfg: dict, alias: str, op: str, command: str | None = None) -> None:
    """Check constraints for an operation. Raises SystemExit on denial."""
    constraints = _get_effective_constraints(cfg, alias)

    if op in ("exec", "upload") and constraints.get("read_only"):
        sys.stderr.write(f"[ERROR] host '{alias}' is read_only; {op} is forbidden\n")
        sys.exit(EXIT_CONSTRAINT_DENIED)

    if op in ("exec", "upload") and not _is_within_allowed_hours(constraints.get("allowed_hours")):
        sys.stderr.write(
            f"[ERROR] operation '{op}' outside allowed_hours "
            f"({constraints.get('allowed_hours')}) for host '{alias}'\n"
        )
        sys.exit(EXIT_OUTSIDE_ALLOWED_HOURS)

    if op in ("exec", "upload") and constraints.get("network_isolated") and _command_needs_public_network(command or ""):
        sys.stderr.write(
            f"[ERROR] host '{alias}' is marked network_isolated; "
            f"refusing {op} that appears to need public Internet access\n"
        )
        sys.exit(EXIT_CONSTRAINT_DENIED)

    if op == "exec" and command:
        for pat in constraints.get("denied_patterns", []):
            try:
                if re.search(pat, command, re.IGNORECASE):
                    sys.stderr.write(
                        f"[ERROR] command violates denied_pattern for host '{alias}': {pat}\n"
                    )
                    sys.exit(EXIT_CONSTRAINT_DENIED)
            except re.error as exc:
                sys.stderr.write(f"[WARN] invalid denied_pattern {pat!r}: {exc}\n")


def _constraint_requires_double_confirm(cfg: dict, alias: str) -> bool:
    return bool(_get_effective_constraints(cfg, alias).get("require_double_confirm"))


# --------------------------------------------------------------------------- #
# Path normalization
# --------------------------------------------------------------------------- #
def _normalize_remote_path(raw: str, label: str = "remote path") -> str:
    """Validate and normalize a remote path supplied via CLI.

    Detects Windows/MSYS path mangling and refuses to proceed.
    Returns a normalized POSIX absolute path.
    """
    if not raw:
        sys.stderr.write(f"[ERROR] {label} is empty\n")
        sys.exit(EXIT_USAGE)

    if "\\" in raw:
        sys.stderr.write(f"[ERROR] {label} contains a backslash: {raw!r}\n")
        sys.stderr.write("        Windows path conversion fired. Use forward slashes only.\n")
        _print_msys_hint()
        sys.exit(EXIT_USAGE)

    if len(raw) >= 2 and raw[1] == ":":
        sys.stderr.write(f"[ERROR] {label} looks like a Windows path: {raw!r}\n")
        sys.stderr.write("        Git Bash (MSYS) auto-converts /opt/... to C:/Program Files/Git/opt/... on Windows.\n")
        _print_msys_hint()
        sys.exit(EXIT_USAGE)

    if not raw.startswith("/"):
        sys.stderr.write(f"[ERROR] {label} must be an absolute POSIX path starting with '/'\n")
        sys.stderr.write(f"        got: {raw!r}\n")
        sys.exit(EXIT_USAGE)

    normed = str(PurePosixPath(raw))
    if raw == "/":
        return "/"
    return normed.rstrip("/") or "/"


def _print_msys_hint() -> None:
    sys.stderr.write("\n[HINT] On Windows + Git Bash, set BOTH before running:\n")
    sys.stderr.write("          export MSYS_NO_PATHCONV=1\n")
    sys.stderr.write("          export MSYS2_ARG_CONV_EXCL='*'\n")
    sys.stderr.write("        Or invoke python via cmd.exe / PowerShell directly.\n\n")


# --------------------------------------------------------------------------- #
# Risk classification + confirmation
# --------------------------------------------------------------------------- #
def _classify_exec_risk(command: str):
    for pat, level, reason in HIGH_RISK_PATTERNS:
        try:
            if re.search(pat, command, re.IGNORECASE):
                return reason, level
        except re.error:
            continue
    return None, None


def _classify_upload_risk(remote: str, mode: str | None):
    reasons = []
    rp = remote.rstrip("/")
    for p in DANGEROUS_REMOTE_PATHS:
        if rp == p or rp.startswith(p + "/"):
            reasons.append(f"target system path: {p}")
            break
    if mode:
        try:
            bits = int(mode, 8)
            if bits & 0o002:
                reasons.append(f"world-writable mode: {mode}")
            if bits & 0o111 and rp.startswith(("/etc", "/var", "/usr", "/boot")):
                reasons.append(f"executable bit on system path: {mode}")
        except ValueError:
            pass
    return reasons


def _format_target(target: dict, op_desc: str) -> str:
    return (
        f"  alias  : {target.get('session') or '-'}\n"
        f"  label  : {target.get('label') or '-'}\n"
        f"  user   : {target['user']}\n"
        f"  host   : {target['host']}:{target['port']}\n"
        f"  auth   : {target.get('key_file') or '(password)'}\n"
        f"  op     : {op_desc}\n"
    )


def _touch_last_used(cfg: dict, alias: str) -> None:
    """Persist the last_used timestamp for an alias after a successful op.

    Failures here must not propagate: a stale timestamp is acceptable, but a
    broken connection trace is not.
    """
    if not alias:
        return
    entry = cfg.get("hosts", {}).get(alias)
    if not entry:
        return
    entry["last_used"] = _now_iso()
    try:
        _save_cfg(cfg)
    except OSError as exc:
        sys.stderr.write(f"[WARN] could not persist last_used for '{alias}': {exc}\n")


def _confirm_host(target: dict, op_desc: str, args) -> None:
    if getattr(args, "yes", False):
        return
    sys.stderr.write("\n[CONFIRM] About to operate on:\n")
    sys.stderr.write(_format_target(target, op_desc))
    sys.stderr.write(
        "\n[NOTE] This prompt is the LAST line of defense.\n"
        "       The AI operator should have ALREADY obtained your explicit\n"
        "       confirmation in chat BEFORE invoking this command.\n"
        "       If you did NOT ask for this, type anything other than 'yes'.\n"
    )
    sys.stderr.flush()
    try:
        ans = input("Type 'yes' to continue (or anything else to abort): ")
    except EOFError:
        sys.stderr.write(
            "[ERROR] no stdin for host confirmation. "
            "Pass --yes if the operator has already confirmed in chat.\n"
        )
        sys.exit(EXIT_HOST_CONFIRM_DECLINED)
    if ans.strip().lower() != "yes":
        sys.stderr.write(f"[ABORT] host confirmation declined: {ans!r}\n")
        sys.exit(EXIT_HOST_CONFIRM_DECLINED)


def _confirm_high_risk(command: str, target: dict, reason: str, level: str, args) -> None:
    if getattr(args, "i_know", False):
        sys.stderr.write(
            f"[{level.upper()}-RISK] --i-know set; reason={reason}; "
            "operator accepts responsibility.\n"
        )
        return
    token = "RUN-" + secrets.token_hex(3).upper()
    if level == "critical":
        border = "!" * 60
        title = "!!! CRITICAL - SYSTEM-DESTROYING OPERATION DETECTED !!!"
        body = (
            "This will IRREVERSIBLY destroy the operating system and all data.\n"
            "There is NO recovery path short of reinstalling from scratch.\n"
        )
    else:
        border = "=" * 60
        title = "!!! HIGH-RISK OPERATION DETECTED !!!"
        body = (
            "This operation may destroy data, stop services, or impact\n"
            "system availability.\n"
        )
    sys.stderr.write("\n" + border + "\n")
    sys.stderr.write(title + "\n")
    sys.stderr.write(border + "\n")
    sys.stderr.write(_format_target(target, command))
    sys.stderr.write(f"  reason  : {reason}\n")
    sys.stderr.write(
        "\n" + body + "\n"
        "The operator (AI) must have obtained EXPLICIT chat confirmation\n"
        "from the user BEFORE invoking this command. The user must understand\n"
        "what data / services will be affected and have answered 'yes' / '确认'\n"
        "in the chat. If not, abort by typing anything other than the token.\n\n"
        f"To proceed, type the token below EXACTLY:\n\n    {token}\n"
    )
    sys.stderr.flush()
    try:
        ans = input("> ")
    except EOFError:
        sys.stderr.write(
            "[ERROR] no stdin for high-risk confirmation.\n"
            "[HINT] pass --i-know if the operator has already confirmed.\n"
        )
        sys.exit(EXIT_HIGH_RISK_DECLINED)
    if ans.strip() != token:
        sys.stderr.write(f"[ABORT] {level}-risk confirmation failed: got {ans!r}\n")
        sys.exit(EXIT_HIGH_RISK_DECLINED)
    sys.stderr.write(f"[OK] {level}-risk command confirmed via token\n")


# --------------------------------------------------------------------------- #
# Target resolution + connection
# --------------------------------------------------------------------------- #
def _resolve_target(args) -> dict:
    cfg = _ensure_cfg()

    if not getattr(args, "session", None):
        default = cfg.get("defaults", {}).get("host")
        if default and default in cfg.get("hosts", {}):
            args.session = default
            sys.stderr.write(f"[INFO] using default session '{default}'\n")

    if args.session:
        entry = cfg.get("hosts", {}).get(args.session)
        if not entry:
            avail = ", ".join(cfg.get("hosts", {}).keys()) or "(none)"
            sys.stderr.write(f"[ERROR] session '{args.session}' not found. Available: {avail}\n")
            sys.exit(EXIT_SESSION_NOT_FOUND)
        if not args.host:
            args.host = entry["host"]
        if not args.user:
            args.user = entry["user"]
        if (args.port == 22) and entry.get("port") and entry["port"] != 22:
            args.port = entry["port"]
        if not args.label and entry.get("label"):
            args.label = entry.get("label")

        # Key-file from config
        if not args.key_file:
            auth = entry.get("auth", {})
            if auth.get("type") == "key-file" and auth.get("path"):
                args.key_file = auth["path"]

        # NOTE: last_used is NOT updated here. Callers that successfully
        # complete an operation (cmd_test/exec/upload/download/probe-net) must
        # call _touch_last_used(cfg, alias) after their work finishes. Doing
        # it here would mean a constraint-rejected request still mutates the
        # config file (see issue A1 in the audit).

    if not args.host or not args.user:
        sys.stderr.write("[ERROR] --host and --user are required (or pass --session ALIAS)\n")
        sys.exit(EXIT_USAGE)

    session_alias = getattr(args, "session", None)
    password = args.password

    # Fallback to config password
    if not password and not args.key_file and session_alias:
        entry = cfg.get("hosts", {}).get(session_alias, {})
        password = entry.get("password")

    if not args.key_file and not password:
        sys.stderr.write("[ERROR] need --password 'xxx' or --key-file.\n")
        sys.exit(EXIT_USAGE)

    return {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "key_file": args.key_file,
        "password": password,
        "session": getattr(args, "session", None) or "",
        "label": getattr(args, "label", "") or "",
    }


def _build_client(target: dict, args):
    if paramiko is None:
        sys.stderr.write("[ERROR] paramiko is required for SSH connections. Run: pip install paramiko\n")
        sys.exit(EXIT_USAGE)

    client = paramiko.SSHClient()
    try:
        client.load_system_host_keys()
    except Exception:
        pass
    if args.host_key:
        client.load_host_keys(args.host_key)
    if getattr(args, "insecure", False):
        policy = paramiko.AutoAddPolicy()
        skip_kh_save = True
    elif args.trust_host:
        policy = paramiko.AutoAddPolicy()
        skip_kh_save = False
    else:
        policy = paramiko.RejectPolicy()
        skip_kh_save = False
    client.set_missing_host_key_policy(policy)

    connect_kwargs = dict(
        hostname=target["host"],
        port=target["port"],
        username=target["user"],
        timeout=args.timeout,
        allow_agent=False,
        look_for_keys=False,
        banner_timeout=args.timeout,
        auth_timeout=args.timeout,
    )
    if target["key_file"]:
        connect_kwargs["key_filename"] = target["key_file"]
        if target["password"] and not getattr(args, "no_password_with_key", False):
            connect_kwargs["password"] = target["password"]
    elif target["password"]:
        connect_kwargs["password"] = target["password"]

    try:
        client.connect(**connect_kwargs)
        if args.trust_host and not getattr(args, "insecure", False):
            kh_dir = Path.home() / ".ssh"
            kh_dir.mkdir(parents=True, exist_ok=True)
            # AutoAddPolicy populates client._host_keys in memory; persist them
            # explicitly so subsequent runs don't need --trust-host again.
            try:
                client.get_host_keys().save(str(kh_dir / "known_hosts"))
            except OSError as exc:
                sys.stderr.write(f"[WARN] could not save known_hosts: {exc}\n")
    except paramiko.AuthenticationException:
        sys.stderr.write("[ERROR] authentication failed\n")
        sys.exit(EXIT_AUTH_FAILED)
    except paramiko.SSHException as exc:
        sys.stderr.write(f"[ERROR] SSH error: {exc}\n")
        sys.exit(EXIT_SSH_ERROR)
    except OSError as exc:
        sys.stderr.write(f"[ERROR] connection failed: {exc}\n")
        sys.exit(EXIT_CONNECTION_FAILED)
    return client


# --------------------------------------------------------------------------- #
# Streaming / SFTP utilities
# --------------------------------------------------------------------------- #
def _run_and_print(client, command: str, timeout: int = 300) -> int:
    """Run a remote command, stream stdout/stderr, return its exit code.

    Two layers of timeout protection:
      1. paramiko's exec_command(timeout=...) — closes the channel when the
         command has not produced output within `timeout` seconds.
      2. A wall-clock deadline here — we bail out even if paramiko's internal
         timer doesn't fire (e.g. the channel is stuck on a half-open socket).
    """
    merged_env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    stdin, stdout, stderr = client.exec_command(
        command, timeout=timeout, environment=merged_env
    )
    chan = stdout.channel
    deadline = time.monotonic() + timeout
    timed_out = False
    while not chan.closed or chan.recv_ready() or chan.recv_stderr_ready():
        if time.monotonic() > deadline:
            timed_out = True
            try:
                chan.close()
            except Exception:
                pass
            break
        if chan.recv_ready():
            sys.stdout.buffer.write(chan.recv(4096))
        if chan.recv_stderr_ready():
            sys.stderr.buffer.write(chan.recv_stderr(4096))
        if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
            break
        time.sleep(0.02)
    while chan.recv_ready():
        sys.stdout.buffer.write(chan.recv(4096))
    while chan.recv_stderr_ready():
        sys.stderr.buffer.write(chan.recv_stderr(4096))
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    if timed_out:
        sys.stderr.write(
            f"[ERROR] remote command exceeded {timeout}s timeout; channel closed\n"
        )
        # 124 matches GNU coreutils `timeout` convention.
        return 124
    return chan.recv_exit_status()


def _remote_has(client, path: str) -> bool:
    stdin, stdout, _ = client.exec_command(
        f"[ -e {shlex.quote(path)} ] && echo Y || echo N"
    )
    return stdout.read().decode(errors="replace").strip() == "Y"


def _sftp_is_dir(sftp, path: str) -> bool:
    try:
        st = sftp.stat(path)
    except IOError:
        return False
    return stat.S_ISDIR(st.st_mode)


def _sftp_mkdir_p(sftp, path: str) -> None:
    if not path or path == "/":
        return
    parts = PurePosixPath(path).parts
    cur = ""
    for part in parts:
        cur = str(PurePosixPath(cur) / part)
        try:
            sftp.stat(cur)
        except IOError:
            try:
                sftp.mkdir(cur)
            except IOError:
                try:
                    sftp.stat(cur)
                except IOError as exc:
                    sys.stderr.write(f"[WARN] mkdir failed: {cur} ({exc})\n")


def _sftp_progress_callback(deadline: float, label: str):
    """Build a paramiko SFTP callback that aborts the transfer on deadline.

    paramiko calls the callback with (bytes_transferred, total_bytes). We
    only use the first argument to check elapsed time; raising from the
    callback propagates as IOError at the put/get call site.
    """
    def _cb(transferred: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise IOError(
                f"sftp transfer '{label}' exceeded deadline (after {transferred} bytes)"
            )
    return _cb


def _sftp_put_dir(sftp, src: Path, dst: str, timeout: int = 600) -> None:
    _sftp_mkdir_p(sftp, dst)
    deadline = time.monotonic() + timeout
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        remote_dir = (
            str(PurePosixPath(dst) / PurePosixPath(rel.as_posix()))
            if str(rel) != "."
            else dst
        )
        if rel.parts:
            _sftp_mkdir_p(sftp, remote_dir)
        for fname in files:
            lpath = Path(root) / fname
            rpath = str(PurePosixPath(remote_dir) / fname)
            sys.stdout.write(f"[INFO] uploading {lpath} -> {rpath}\n")
            cb = _sftp_progress_callback(deadline, f"put {rpath}")
            try:
                sftp.put(str(lpath), rpath, callback=cb)
            except IOError as exc:
                sys.stderr.write(f"[ERROR] upload failed: {exc}\n")
                raise


def _sftp_get_dir(sftp, src: str, dst: Path, timeout: int = 600) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    for entry in sftp.listdir_attr(src):
        spath = str(PurePosixPath(src) / entry.filename)
        dpath = dst / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            _sftp_get_dir(sftp, spath, dpath, timeout=timeout)
        else:
            sys.stdout.write(f"[INFO] downloading {spath} -> {dpath}\n")
            cb = _sftp_progress_callback(deadline, f"get {spath}")
            try:
                sftp.get(spath, str(dpath), callback=cb)
            except IOError as exc:
                sys.stderr.write(f"[ERROR] download failed: {exc}\n")
                raise


# --------------------------------------------------------------------------- #
# Subcommand handlers
# --------------------------------------------------------------------------- #
def cmd_test(args) -> int:
    cfg = _ensure_cfg()
    target = _resolve_target(args)
    alias = target["session"] or args.session or ""
    _check_constraints(cfg, alias, "test")
    _confirm_host(target, "test (connectivity check + host info)", args)
    client = _build_client(target, args)
    try:
        transport = client.get_transport()
        rsa_key = transport.get_remote_server_key() if transport else None
        if rsa_key:
            fp = ":".join(f"{b:02x}" for b in rsa_key.get_fingerprint())
            sys.stdout.write(f"[OK] connected to {target['host']}:{target['port']}\n")
            sys.stdout.write(f"[INFO] host key type={rsa_key.get_name()} fp={fp}\n")
        else:
            sys.stdout.write(f"[OK] connected to {target['host']}:{target['port']}\n")
        _run_and_print(
            client,
            "uname -a; echo '---'; cat /etc/os-release 2>/dev/null || true",
            timeout=args.timeout,
        )
        _touch_last_used(cfg, alias)
        return EXIT_OK
    finally:
        client.close()


def cmd_exec(args) -> int:
    cfg = _ensure_cfg()
    target = _resolve_target(args)
    alias = target["session"] or args.session or ""
    _check_constraints(cfg, alias, "exec", command=args.command)

    op = f"exec {args.command!r}"
    reason, level = _classify_exec_risk(args.command)
    if reason:
        _confirm_host(target, op, args)
        _confirm_high_risk(args.command, target, reason, level, args)
    else:
        _confirm_host(target, op, args)
        if _constraint_requires_double_confirm(cfg, alias):
            _confirm_high_risk(args.command, target, "host/env requires double confirm", "high", args)

    client = _build_client(target, args)
    try:
        rc = _run_and_print(client, args.command, timeout=args.cmd_timeout)
        if rc == 0:
            _touch_last_used(cfg, alias)
        return rc
    finally:
        client.close()


def _sftp_chmod_r(sftp, remote_path: str, mode: int) -> None:
    """Recursively chmod remote_path and everything beneath it.

    Walk is implemented via listdir_attr (not a shell chmod -R) so we don't
    trip the high-risk 'chmod -R 0777' / 'chmod 0?777' gates.
    """
    def _walk(path: str) -> None:
        try:
            sftp.chmod(path, mode)
        except OSError:
            pass
        try:
            entries = sftp.listdir_attr(path)
        except OSError:
            return
        for entry in entries:
            child = path.rstrip("/") + "/" + entry.filename
            if stat.S_ISDIR(entry.st_mode):
                _walk(child)
            else:
                try:
                    sftp.chmod(child, mode)
                except OSError:
                    pass

    _walk(remote_path)


def cmd_upload(args) -> int:
    cfg = _ensure_cfg()
    args.remote = _normalize_remote_path(args.remote, label="--remote")
    target = _resolve_target(args)
    alias = target["session"] or args.session or ""
    _check_constraints(cfg, alias, "upload")

    op = f"upload {args.local} -> {args.remote}"
    upload_risks = _classify_upload_risk(args.remote, args.mode)
    if upload_risks:
        _confirm_host(target, op, args)
        reason = "; ".join(upload_risks)
        confirm_cmd = f"upload to {args.remote}" + (f" mode {args.mode}" if args.mode else "")
        _confirm_high_risk(confirm_cmd, target, reason, "high", args)
    else:
        _confirm_host(target, op, args)

    local_path = Path(args.local)
    if not local_path.exists():
        sys.stderr.write(f"[ERROR] local path not found: {local_path}\n")
        return EXIT_USAGE
    client = _build_client(target, args)
    try:
        sftp = client.open_sftp()
        deadline = time.monotonic() + args.transfer_timeout
        if local_path.is_dir():
            _sftp_put_dir(sftp, local_path, args.remote, timeout=args.transfer_timeout)
        else:
            parent = str(PurePosixPath(args.remote).parent)
            if parent and parent != ".":
                _sftp_mkdir_p(sftp, parent)
            sys.stdout.write(f"[INFO] uploading {local_path} -> {args.remote}\n")
            cb = _sftp_progress_callback(deadline, f"put {args.remote}")
            try:
                sftp.put(str(local_path), args.remote, callback=cb)
            except IOError as exc:
                sys.stderr.write(f"[ERROR] upload failed: {exc}\n")
                return 124
        if args.mode:
            try:
                _sftp_chmod_r(sftp, args.remote, int(args.mode, 8))
            except OSError as exc:
                sys.stderr.write(f"[WARN] chmod failed: {exc}\n")
        sftp.close()
        sys.stdout.write(f"[OK] upload complete: {args.remote}\n")
        _touch_last_used(cfg, alias)
        return EXIT_OK
    finally:
        client.close()


def cmd_download(args) -> int:
    cfg = _ensure_cfg()
    args.remote = _normalize_remote_path(args.remote, label="--remote")
    target = _resolve_target(args)
    alias = target["session"] or args.session or ""
    _check_constraints(cfg, alias, "download")

    op = f"download {args.remote} -> {args.local}"
    _confirm_host(target, op, args)
    client = _build_client(target, args)
    try:
        sftp = client.open_sftp()
        local_path = Path(args.local)
        deadline = time.monotonic() + args.transfer_timeout
        if _sftp_is_dir(sftp, args.remote):
            _sftp_get_dir(sftp, args.remote, local_path, timeout=args.transfer_timeout)
        else:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            sys.stdout.write(f"[INFO] downloading {args.remote} -> {local_path}\n")
            cb = _sftp_progress_callback(deadline, f"get {args.remote}")
            try:
                sftp.get(args.remote, str(local_path), callback=cb)
            except IOError as exc:
                sys.stderr.write(f"[ERROR] download failed: {exc}\n")
                return 124
        sftp.close()
        sys.stdout.write(f"[OK] download complete: {local_path}\n")
        _touch_last_used(cfg, alias)
        return EXIT_OK
    finally:
        client.close()


def cmd_probe_net(args) -> int:
    cfg = _ensure_cfg()
    target = _resolve_target(args)
    alias = target["session"] or args.session or ""
    _check_constraints(cfg, alias, "probe-net")

    if _get_effective_constraints(cfg, alias).get("network_isolated"):
        sys.stderr.write(
            f"[ERROR] host '{alias}' is marked network_isolated; "
            "probe-net to public targets is refused by policy\n"
            "[HINT]  see references/offline-workflow.md for the offline playbook.\n"
            "        to override per-call, set --allow-probe-net (NOT YET IMPLEMENTED).\n"
        )
        return EXIT_NETWORK_ISOLATED_PROBE

    op = "probe-net (read-only network reachability)"
    _confirm_host(target, op, args)
    client = _build_client(target, args)
    try:
        shell = "/bin/bash" if _remote_has(client, "/bin/bash") else "/bin/sh"
        targets = args.targets if args.targets else [
            "https://github.com",
            "https://www.baidu.com",
            "https://pypi.org",
        ]
        any_online = False
        for t in targets:
            quoted = shlex.quote(t)
            cmd = (
                f"{shell} -c "
                f"'curl -sS --max-time {args.timeout2} -o /dev/null "
                f'-w "%{{http_code}}" {quoted} || echo CURL_FAIL\''
            )
            stdin, stdout, stderr = client.exec_command(
                cmd, timeout=args.timeout2 + 5,
                environment={"PATH": "/usr/bin:/bin"},
            )
            code = stdout.read().decode(errors="replace").strip()
            err = stderr.read().decode(errors="replace").strip()
            ok = code.startswith("2") or code.startswith("3")
            marker = "[ONLINE]" if ok else "[OFFLINE]"
            sys.stdout.write(f"{marker} {t} -> {code or 'n/a'} {err[:120]}\n")
            if ok:
                any_online = True
        sys.stdout.write(
            "[OK] remote has outbound network\n" if any_online
            else "[FAIL] remote appears offline\n"
        )
        _touch_last_used(cfg, alias)
        return EXIT_OK if any_online else 1
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# Session management (writes v3 config)
# --------------------------------------------------------------------------- #
def cmd_session(args) -> int:
    cfg = _ensure_cfg()
    action = args.session_action
    if action == "list":
        return _session_list(cfg)
    if action == "add":
        return _session_add(cfg, args)
    if action == "show":
        return _session_show(cfg, args)
    if action == "use":
        return _session_use(cfg, args)
    if action == "rm":
        return _session_rm(cfg, args)
    if action == "rename":
        return _session_rename(cfg, args)
    sys.stderr.write(f"[ERROR] unknown session action: {action}\n")
    return EXIT_USAGE


def _session_list(cfg: dict) -> int:
    hosts = cfg.get("hosts", {})
    if not hosts:
        sys.stdout.write("(no sessions saved; use 'session add' to create one)\n")
        return EXIT_OK
    name_w = max([len(n) for n in hosts], default=4)
    host_w = max(
        [len(f"{h.get('user','?')}@{h.get('host','?')}:{h.get('port',22)}")
         for h in hosts.values()], default=10
    )
    sys.stdout.write(
        f"{'ALIAS':<{name_w}}  {'USER@HOST:PORT':<{host_w}}  "
        f"ENV  LABEL  LAST_USED  TAGS\n"
    )
    for name, entry in hosts.items():
        marker = "*" if cfg.get("defaults", {}).get("host") == name else " "
        uhp = f"{entry.get('user','?')}@{entry.get('host','?')}:{entry.get('port',22)}"
        env = entry.get("environment", "") or "-"
        label = (entry.get("label") or "-")[:20]
        tags = ",".join(entry.get("tags") or [])
        sys.stdout.write(
            f"{marker}{name:<{name_w}}  {uhp:<{host_w}}  "
            f"{env:<3}  {label:<20}  "
            f"{(entry.get('last_used') or '-'):<19}  {tags}\n"
        )
    return EXIT_OK


def _session_add(cfg: dict, args) -> int:
    alias = args.name
    if not alias:
        sys.stderr.write("[ERROR] session add requires a NAME\n")
        return EXIT_USAGE
    if not args.host or not args.user:
        sys.stderr.write("[ERROR] session add needs --host and --user\n")
        return EXIT_USAGE

    auth_type = "password"
    auth_obj: dict = {"type": "password"}
    password = args.password
    if args.key_file:
        auth_type = "key-file"
        auth_obj = {"type": "key-file", "path": str(Path(args.key_file).expanduser())}
        password = password or ""

    if not args.key_file and not password:
        sys.stderr.write("[ERROR] need --key-file or --password 'xxx'\n")
        return EXIT_USAGE

    if alias in cfg.get("hosts", {}):
        sys.stderr.write(f"[WARN] overwriting existing session '{alias}'\n")
    existing = cfg["hosts"].get(alias, {})
    host_constraints: dict = dict(existing.get("constraints", {}))
    if getattr(args, "network_isolated", None) is not None:
        host_constraints["network_isolated"] = bool(args.network_isolated)
    cfg.setdefault("hosts", {})[alias] = {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "password": password or "",
        "auth": auth_obj,
        "environment": getattr(args, "env", "") or "",
        "label": args.label or "",
        "tags": list(args.tags or []),
        "constraints": host_constraints,
        "created": existing.get("created", _now_iso()),
        "last_used": existing.get("last_used", ""),
    }
    if cfg["defaults"]["host"] is None:
        cfg["defaults"]["host"] = alias
    _save_cfg(cfg)
    sys.stdout.write(f"[OK] saved session '{alias}' -> {args.user}@{args.host}:{args.port}\n")
    return EXIT_OK


def _session_show(cfg: dict, args) -> int:
    if not args.name:
        sys.stderr.write("[ERROR] session show requires a NAME\n")
        return EXIT_USAGE
    entry = cfg.get("hosts", {}).get(args.name)
    if not entry:
        sys.stderr.write(f"[ERROR] session '{args.name}' not found\n")
        return EXIT_SESSION_NOT_FOUND
    sys.stdout.write(f"alias      : {args.name}\n")
    sys.stdout.write(f"user       : {entry.get('user')}\n")
    sys.stdout.write(f"host       : {entry.get('host')}:{entry.get('port',22)}\n")
    sys.stdout.write(
        f"auth       : {entry.get('auth',{}).get('type')} "
        f"{entry.get('auth',{}).get('path','')}\n"
    )
    sys.stdout.write(f"password   : {'(set)' if entry.get('password') else '(not set)'}\n")
    sys.stdout.write(f"environment: {entry.get('environment','-')}\n")
    sys.stdout.write(f"label      : {entry.get('label','')}\n")
    sys.stdout.write(f"tags       : {','.join(entry.get('tags') or [])}\n")
    effective = _get_effective_constraints(cfg, args.name)
    sys.stdout.write(
        "constraints: "
        f"read_only={effective.get('read_only')}, "
        f"double_confirm={effective.get('require_double_confirm')}, "
        f"network_isolated={effective.get('network_isolated')}, "
        f"denied={effective.get('denied_patterns')}, "
        f"allowed_hours={effective.get('allowed_hours')}\n"
    )
    sys.stdout.write(f"created    : {entry.get('created','')}\n")
    sys.stdout.write(f"last_used  : {entry.get('last_used','')}\n")
    return EXIT_OK


def _session_use(cfg: dict, args) -> int:
    if not args.name:
        sys.stderr.write("[ERROR] session use requires a NAME\n")
        return EXIT_USAGE
    if args.name not in cfg.get("hosts", {}):
        sys.stderr.write(f"[ERROR] session '{args.name}' not found\n")
        return EXIT_SESSION_NOT_FOUND
    cfg["defaults"]["host"] = args.name
    _save_cfg(cfg)
    sys.stdout.write(f"[OK] default session set to '{args.name}'\n")
    return EXIT_OK


def _session_rm(cfg: dict, args) -> int:
    if not args.name:
        sys.stderr.write("[ERROR] session rm requires a NAME\n")
        return EXIT_USAGE
    if args.name not in cfg.get("hosts", {}):
        sys.stderr.write(f"[ERROR] session '{args.name}' not found\n")
        return EXIT_SESSION_NOT_FOUND
    del cfg["hosts"][args.name]
    if cfg.get("defaults", {}).get("host") == args.name:
        cfg["defaults"]["host"] = next(iter(cfg["hosts"]), None)
    _save_cfg(cfg)
    sys.stdout.write(f"[OK] removed session '{args.name}'\n")
    return EXIT_OK


def _session_rename(cfg: dict, args) -> int:
    if not args.name or not args.name2:
        sys.stderr.write("[ERROR] session rename needs OLD NEW\n")
        return EXIT_USAGE
    if args.name not in cfg.get("hosts", {}):
        sys.stderr.write(f"[ERROR] session '{args.name}' not found\n")
        return EXIT_SESSION_NOT_FOUND
    if args.name2 in cfg.get("hosts", {}):
        sys.stderr.write(f"[ERROR] target alias '{args.name2}' already exists\n")
        return EXIT_USAGE
    cfg["hosts"][args.name2] = cfg["hosts"].pop(args.name)
    if cfg.get("defaults", {}).get("host") == args.name:
        cfg["defaults"]["host"] = args.name2
    _save_cfg(cfg)
    sys.stdout.write(f"[OK] renamed '{args.name}' -> '{args.name2}'\n")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Config management subcommands
# --------------------------------------------------------------------------- #
def cmd_config(args) -> int:
    cfg = _ensure_cfg()
    if args.config_cmd == "show":
        return cmd_config_show(cfg, args)
    if args.config_cmd == "env":
        return cmd_config_env(cfg, args)
    if args.config_cmd == "host":
        return cmd_config_host(cfg, args)
    sys.stderr.write(f"[ERROR] unknown config command: {args.config_cmd}\n")
    return EXIT_USAGE


def cmd_config_show(cfg: dict, _args) -> int:
    # Mask passwords in show output for safety.
    display = copy.deepcopy(cfg)
    for host in display.get("hosts", {}).values():
        if host.get("password"):
            host["password"] = "***"
    sys.stdout.write(json.dumps(display, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return EXIT_OK


def cmd_config_env(cfg: dict, args) -> int:
    action = args.env_action
    if action == "list":
        envs = cfg.get("environment", {})
        if not envs:
            sys.stdout.write("(no environments defined)\n")
            return EXIT_OK
        name_w = max([len(n) for n in envs], default=4)
        sys.stdout.write(f"{'NAME':<{name_w}}  DESCRIPTION  TAGS  CONSTRAINTS\n")
        for name, info in sorted(envs.items()):
            desc = info.get("description", "") or "-"
            tags = ",".join(info.get("tags", []))
            constraints = json.dumps(info.get("constraints", {}), ensure_ascii=False)
            sys.stdout.write(f"{name:<{name_w}}  {desc:<32}  {tags:<20}  {constraints}\n")
        return EXIT_OK

    if action == "add":
        name = args.env_name
        if not name:
            sys.stderr.write("[ERROR] config env add requires a NAME\n")
            return EXIT_USAGE
        if name in cfg.get("environment", {}):
            sys.stderr.write(f"[WARN] environment '{name}' already exists, updating\n")
        cfg.setdefault("environment", {})[name] = {
            "description": args.desc or "",
            "tags": list(args.tags or []),
            "constraints": dict(DEFAULT_CONSTRAINTS),
        }
        _save_cfg(cfg)
        sys.stdout.write(f"[OK] environment '{name}' added/updated\n")
        return EXIT_OK

    if action == "rm":
        name = args.env_name
        if not name:
            sys.stderr.write("[ERROR] config env rm requires a NAME\n")
            return EXIT_USAGE
        if name not in cfg.get("environment", {}):
            sys.stderr.write(f"[ERROR] environment '{name}' not found\n")
            return EXIT_SESSION_NOT_FOUND
        del cfg["environment"][name]
        _save_cfg(cfg)
        sys.stdout.write(f"[OK] environment '{name}' removed\n")
        return EXIT_OK

    if action == "set-constraints":
        return _cmd_set_constraints(cfg, args, scope="environment")

    sys.stderr.write(f"[ERROR] unknown env action: {action}\n")
    return EXIT_USAGE


def cmd_config_host(cfg: dict, args) -> int:
    action = args.host_action
    if action == "list":
        return _session_list(cfg)

    if action == "add":
        return _session_add(cfg, args)

    if action == "rm":
        return _session_rm(cfg, args)

    if action == "set-constraints":
        return _cmd_set_constraints(cfg, args, scope="host")

    sys.stderr.write(f"[ERROR] unknown host action: {action}\n")
    return EXIT_USAGE


def _cmd_set_constraints(cfg: dict, args, scope: str) -> int:
    if scope == "environment":
        name = args.env_name
        container = cfg.setdefault("environment", {})
        key = "constraints"
    else:
        name = args.host_alias
        container = cfg.setdefault("hosts", {})
        key = "constraints"

    if not name:
        sys.stderr.write(f"[ERROR] {scope} name is required\n")
        return EXIT_USAGE
    if name not in container:
        sys.stderr.write(f"[ERROR] {scope} '{name}' not found\n")
        return EXIT_SESSION_NOT_FOUND

    entry = container[name]
    entry.setdefault(key, {})

    if getattr(args, "read_only", None) is not None:
        entry[key]["read_only"] = bool(args.read_only)
    if getattr(args, "require_double_confirm", None) is not None:
        entry[key]["require_double_confirm"] = bool(args.require_double_confirm)
    if getattr(args, "denied_patterns", None) is not None:
        entry[key]["denied_patterns"] = list(args.denied_patterns or [])
    if getattr(args, "allowed_hours", None) is not None:
        spec = args.allowed_hours
        if spec:
            if not re.fullmatch(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}", spec):
                sys.stderr.write(f"[ERROR] allowed_hours must be HH:MM-HH:MM, got {spec!r}\n")
                return EXIT_USAGE
        entry[key]["allowed_hours"] = spec
    if getattr(args, "network_isolated", None) is not None:
        entry[key]["network_isolated"] = bool(args.network_isolated)

    _save_cfg(cfg)
    sys.stdout.write(f"[OK] constraints updated for {scope} '{name}'\n")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def _bool_flag(raw):
    """argparse type for --flag true/false/1/0/yes/no (case-insensitive)."""
    s = str(raw).strip().lower()
    if s in ("true", "1", "yes", "y", "on"):
        return True
    if s in ("false", "0", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(
        f"expected true/false, got {raw!r}"
    )


def _opt_bool_flag():
    """Optional variant: returns None if not provided, otherwise bool."""
    return lambda x: _bool_flag(x)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ssh_ops.py",
        description="SSH operations helper (ssh-remote skill v3)",
    )
    p.add_argument("--session", help="alias from config")
    p.add_argument("--host", help="remote host or IP")
    p.add_argument("--port", type=int, default=22, help="SSH port (default 22)")
    p.add_argument("--user", help="remote username")
    p.add_argument("--label", help="human-readable label")
    p.add_argument("--password", help="remote password")
    p.add_argument("--key-file", help="SSH private key path")
    p.add_argument("--no-password-with-key", action="store_true",
                   help="do not use password as key passphrase")
    p.add_argument("--timeout", type=int, default=15, help="connect/auth timeout")
    p.add_argument("--trust-host", action="store_true",
                   help="auto-trust unknown host key")
    p.add_argument("--host-key", help="explicit known_hosts file")
    p.add_argument("--yes", action="store_true",
                   help="skip host confirmation")
    p.add_argument("--i-know", action="store_true",
                   help="skip high/critical risk token confirmation")
    p.add_argument("--insecure", action="store_true",
                   help="accept any host key (dangerous)")
    p.add_argument("--transfer-timeout", type=int, default=600,
                   help="SFTP upload/download wall-clock deadline, seconds (default 600)")
    p.add_argument("--cmd-timeout", type=int, default=600,
                   help="remote command wall-clock deadline, seconds (default 600, returns 124 on timeout)")

    sub = p.add_subparsers(dest="cmd", required=True)

    # test
    sp = sub.add_parser("test", help="connect and print host info")
    sp.set_defaults(func=cmd_test)

    # exec
    sp = sub.add_parser("exec", help="run a remote command")
    sp.add_argument("command", help="remote shell command")
    sp.add_argument("--sessions", help="comma-separated aliases for batch exec")
    sp.add_argument("--all", action="store_true", help="batch exec on all hosts")
    sp.set_defaults(func=cmd_exec)

    # upload
    sp = sub.add_parser("upload", help="upload file or directory")
    sp.add_argument("--local", required=True, help="local path")
    sp.add_argument("--remote", required=True, help="remote absolute path")
    sp.add_argument("--mode", help="chmod mode, e.g. 0755")
    sp.set_defaults(func=cmd_upload)

    # download
    sp = sub.add_parser("download", help="download file or directory")
    sp.add_argument("--remote", required=True, help="remote absolute path")
    sp.add_argument("--local", required=True, help="local destination")
    sp.set_defaults(func=cmd_download)

    # probe-net
    sp = sub.add_parser("probe-net", help="check outbound network from remote")
    sp.add_argument("--targets", nargs="+", help="URLs to probe")
    sp.add_argument("--timeout2", type=int, default=8, help="per-probe timeout")
    sp.set_defaults(func=cmd_probe_net)

    # session
    sp = sub.add_parser("session", help="manage saved sessions/aliases")
    sp.add_argument("session_action", choices=["add", "rm", "list", "show", "use", "rename"])
    sp.add_argument("name", nargs="?", help="alias")
    sp.add_argument("name2", nargs="?", help="new alias for rename")
    sp.add_argument("--host", help="remote host or IP")
    sp.add_argument("--port", type=int, default=22)
    sp.add_argument("--user", help="remote username")
    sp.add_argument("--password", help="remote password (saved in plaintext)")
    sp.add_argument("--key-file", help="SSH private key path")
    sp.add_argument("--env", help="environment name")
    sp.add_argument("--label", help="human-readable label")
    sp.add_argument("--tags", nargs="*", help="tags")
    sp.add_argument("--network-isolated", type=_bool_flag, default=None,
                    help="mark this host as network_isolated (true/false)")
    sp.set_defaults(func=cmd_session)

    # config
    sp = sub.add_parser("config", help="manage global config")
    config_sub = sp.add_subparsers(dest="config_cmd", required=True)

    sp_show = config_sub.add_parser("show", help="print config (passwords masked)")
    sp_show.set_defaults(func=cmd_config)

    sp_env = config_sub.add_parser("env", help="manage environments")
    sp_env.add_argument("env_action", choices=["add", "rm", "list", "set-constraints"])
    sp_env.add_argument("env_name", nargs="?", help="environment name")
    sp_env.add_argument("--desc", help="description (add only)")
    sp_env.add_argument("--tags", nargs="*", help="tags (add only)")
    sp_env.add_argument("--read-only", type=lambda x: x.lower() in ("true", "1", "yes"),
                        help="set read_only constraint (true/false)")
    sp_env.add_argument("--require-double-confirm", type=lambda x: x.lower() in ("true", "1", "yes"),
                        help="set require_double_confirm constraint (true/false)")
    sp_env.add_argument("--denied-patterns", nargs="*", help="space-separated regex list")
    sp_env.add_argument("--allowed-hours", help="HH:MM-HH:MM or empty")
    sp_env.add_argument("--network-isolated", type=_bool_flag, default=None,
                        help="mark this environment as network_isolated (true/false)")
    sp_env.set_defaults(func=cmd_config)

    sp_host = config_sub.add_parser("host", help="manage hosts")
    sp_host.add_argument("host_action", choices=["add", "rm", "list", "set-constraints"])
    sp_host.add_argument("host_alias", nargs="?", help="host alias")
    sp_host.add_argument("--host", help="remote host or IP")
    sp_host.add_argument("--port", type=int, default=22)
    sp_host.add_argument("--user", help="remote username")
    sp_host.add_argument("--key-file", help="SSH private key path")
    sp_host.add_argument("--password", help="remote password")
    sp_host.add_argument("--env", help="environment name")
    sp_host.add_argument("--label", help="human-readable label")
    sp_host.add_argument("--tags", nargs="*", help="tags")
    sp_host.add_argument("--read-only", type=lambda x: x.lower() in ("true", "1", "yes"),
                         help="set read_only constraint (true/false)")
    sp_host.add_argument("--require-double-confirm", type=lambda x: x.lower() in ("true", "1", "yes"),
                         help="set require_double_confirm constraint (true/false)")
    sp_host.add_argument("--denied-patterns", nargs="*", help="space-separated regex list")
    sp_host.add_argument("--allowed-hours", help="HH:MM-HH:MM or empty")
    sp_host.add_argument("--network-isolated", type=_bool_flag, default=None,
                         help="mark this host as network_isolated (true/false)")
    sp_host.set_defaults(func=cmd_config)

    return p


def _configure_msys_no_pathconv() -> None:
    """Disable MSYS path conversion on Windows so POSIX remote paths like
    /opt/... are not rewritten to C:/Program Files/Git/opt/...

    Safe no-op on non-Windows / non-MSYS runtimes.
    """
    if sys.platform != "win32":
        return
    # MSYS sets MSYSTEM=MSYS or MINGW64 etc.; Cygwin sets none of those.
    if not os.environ.get("MSYSTEM") and "MSYS" not in sys.version:
        return
    os.environ.setdefault("MSYS_NO_PATHCONV", "1")
    os.environ.setdefault("MSYS2_ARG_CONV_EXCL", "*")


def main(argv=None) -> int:
    _configure_msys_no_pathconv()
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
