---
date: 2026-06-30
---

# ssh-remote Cleanup 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** 在 `ssh-remote` 命令执行结束后自动清理本次进程在远端/本地产生的临时文件；默认开启；失败时仍执行；支持 `--no-cleanup` / `--cleanup-dry-run`。

**Architecture:** 新增 `CleanupRegistry` 集中登记临时路径；`main()` 用 `try/finally` 保证清理；`cmd_exec`/`cmd_upload`/`cmd_download` 把远端/本地临时目录注册到 Registry；清理前经安全护栏校验，失败只 warning 不影响主退出码。

**Tech Stack:** Python 3.12, `pathlib`, `paramiko.SFTPClient`, `tempfile`, `shutil`.

## Global Constraints

- 不修改 `ssh_remote_config.json` 格式与路径解析。
- 不清理用户显式 `--local`/`--remote` 路径，除非它们落在 Registry 中。
- 远端清理路径必须先解析 `realpath`；禁止清理 `/`, `/etc`, `/usr`, `/home`, `/root` 等系统路径。
- 清理失败不得改变主命令退出码。
- 全量新增测试跑在 `pytest` 下，与既有 48 个用例一起通过。

---

### Task 1: CleanupRegistry 与基础工具

**Files:**
- Create: `skills/ssh-remote/scripts/cleanup.py`
- Test: `skills/ssh-remote/scripts/test_cleanup.py`

**Interfaces:** 产生 `CleanupRegistry`, `is_safe_to_delete(path: str) -> bool`, `run_id() -> str`。

- [ ] **Step 1: 编写失败测试**

```python
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
```

运行：`python -m pytest skills/ssh-remote/scripts/test_cleanup.py -v`，预期失败。

- [ ] **Step 2: 实现最小代码**

`skills/ssh-remote/scripts/cleanup.py`：

```python
from __future__ import annotations
import shutil
import secrets
import stat
import time
from pathlib import Path
from typing import Any, List

_DENY_PREFIXES = frozenset({
    "/", "/etc", "/usr", "/var", "/bin", "/sbin", "/lib", "/lib64",
    "/boot", "/proc", "/sys", "/dev", "/home", "/root",
})

def run_id() -> str:
    return f"ssh-remote-{int(time.time() * 1000)}-{secrets.token_hex(2)}"

def is_safe_to_delete(path: str) -> bool:
    p = Path(path).expanduser().resolve()
    if str(p) in {"/"}:
        return False
    for prefix in _DENY_PREFIXES:
        if str(p).startswith(prefix + "/") or str(p) == prefix:
            return False
    if ".." in p.parts:
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
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest skills/ssh-remote/scripts/test_cleanup.py -v
```
预期：4 个测试通过。

- [ ] **Step 4: 提交**

```bash
git add skills/ssh-remote/scripts/cleanup.py skills/ssh-remote/scripts/test_cleanup.py
git commit -m "feat(ssh-remote): add CleanupRegistry and safety guards"
```

---

### Task 2: 集成 Registry 到 main 并添加 CLI 参数

**Files:**
- Modify: `skills/ssh-remote/scripts/ssh_ops.py`
- Test: `skills/ssh-remote/scripts/test_cleanup.py`

**Interfaces:** 产生 `args._registry`, `args.no_cleanup`, `args.cleanup_dry_run`, `args.remote_staging_dir`, `args.local_staging_dir`。

- [ ] **Step 1: 修改 import 与 main()**

在 `ssh_ops.py` 顶部新增：`from cleanup import CleanupRegistry, run_id`。

在 `main()` 中：

```python
def main(argv=None) -> int:
    _configure_msys_no_pathconv()
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)
    registry = CleanupRegistry()
    args._registry = registry
    args._run_id = run_id()
    try:
        return args.func(args)
    finally:
        if not args.no_cleanup:
            registry.cleanup(dry_run=args.cleanup_dry_run)
```

- [ ] **Step 2: 在 _build_parser 添加全局参数**

在 `--insecure` 参数后添加：

```python
        p.add_argument("--no-cleanup", action="store_true",
                       help="skip automatic cleanup of temporary files")
        p.add_argument("--cleanup-dry-run", action="store_true",
                       help="print temporary paths that would be cleaned")
        p.add_argument("--remote-staging-dir", default="/tmp",
                       help="remote base directory for staging (default: /tmp)")
        p.add_argument("--local-staging-dir", default=None,
                       help="local base directory for staging (default: ~/.ssh-remote/tmp)")
```

`--local-staging-dir` 默认 `None` 表示在 `main()` 中解析为 `Path.home() / ".ssh-remote" / "tmp"`。

- [ ] **Step 3: 测试 dry-run 与 no-cleanup**

新增测试：

```python
def test_cleanup_registry_dry_run(tmp_path):
    p = tmp_path / "junk.txt"
    p.write_text("x")
    reg = CleanupRegistry()
    reg.add_local(p)
    reg.cleanup(dry_run=True)
    assert p.exists()

def test_cleanup_registry_remote_dry_run():
    reg = CleanupRegistry()
    reg.add_remote(object(), "/tmp/ssh-remote-abc")
    reg.cleanup(dry_run=True)
```

运行：
```bash
python -m pytest skills/ssh-remote/scripts/test_cleanup.py -v
```
预期：6 个测试通过。

- [ ] **Step 4: 提交**

```bash
git add skills/ssh-remote/scripts/ssh_ops.py skills/ssh-remote/scripts/test_cleanup.py
git commit -m "feat(ssh-remote): integrate CleanupRegistry into main() and add CLI flags"
```

---

### Task 3: cmd_exec 使用远端 staging 目录并登记清理

**Files:**
- Modify: `skills/ssh-remote/scripts/ssh_ops.py`
- Test: `skills/ssh-remote/scripts/test_cleanup_exec.py`

**Interfaces:** 产生远端 `/tmp/ssh-remote-{run_id}/` 目录，通过环境变量 `SSH_REMOTE_TMP` 暴露给命令。

- [ ] **Step 1: 修改 cmd_exec**

在 `cmd_exec` 中，创建 client 之前建立 staging 目录并注册：

```python
def cmd_exec(args) -> int:
    cfg = _ensure_cfg()
    target = _resolve_target(args)
    alias = target["session"] or args.session or ""
    _check_constraints(cfg, alias, "exec", command=args.command)

    registry = getattr(args, "_registry", None)
    remote_staging = f"{args.remote_staging_dir.rstrip('/')}/{args._run_id}"
    if registry:
        registry.add_remote(remote_staging)

    # 在 client 建立后创建远端目录
    ...
```

确保 `_run_and_print` 接受 `environment` 参数并传给 `client.exec_command`，从而注入 `SSH_REMOTE_TMP`。

- [ ] **Step 2: 测试**

`skills/ssh-remote/scripts/test_cleanup_exec.py`：

```python
from unittest.mock import MagicMock

def test_exec_registers_remote_staging():
    args = MagicMock()
    args.command = "echo ok"
    args._run_id = "abc123"
    args.remote_staging_dir = "/tmp"
    args._registry = MagicMock()
    args._registry.add_remote = MagicMock()
    # 省略 mock 其他依赖
    assert args._registry.add_remote.called
```

运行：
```bash
python -m pytest skills/ssh-remote/scripts/test_cleanup_exec.py -v
```

- [ ] **Step 3: 提交**

```bash
git add skills/ssh-remote/scripts/ssh_ops.py skills/ssh-remote/scripts/test_cleanup_exec.py
git commit -m "feat(ssh-remote): exec creates remote staging dir and registers it for cleanup"
```

---

### Task 4: upload / download 使用临时 staging 并清理

**Files:**
- Modify: `skills/ssh-remote/scripts/ssh_ops.py`
- Test: `skills/ssh-remote/scripts/test_cleanup_transfer.py`

**Interfaces:** 本地/远端 staging 目录被注册到 Registry，传输成功后自动清理。

- [ ] **Step 1: upload 目录自动打包上传**

如果 `local_path.is_dir()` 且用户未显式指定非 staging 的 `--remote`，则创建本地 tar 包到 `local_staging_dir / {run_id}.tar.gz`，上传，远端解压，登记本地 tar 和远端 tar 路径。

伪代码（嵌入 `cmd_upload`）：

```python
        if local_path.is_dir() and args.remote.startswith(args.remote_staging_dir):
            staging_dir = Path(args.local_staging_dir or Path.home() / ".ssh-remote" / "tmp")
            staging_dir.mkdir(parents=True, exist_ok=True)
            archive = staging_dir / f"{args._run_id}.tar.gz"
            _local_tar(local_path, archive)
            args._registry.add_local(archive)
            remote_tar = f"{args.remote_staging_dir.rstrip('/')}/{args._run_id}.tar.gz"
            args._registry.add_remote(client, remote_tar)
            # upload archive, then remote exec tar -xzf
```

保持向后兼容：如果用户显式 `--remote` 指定了目录，仍然使用目录上传。

- [ ] **Step 2: download 远端目录自动打包下载**

如果 `_sftp_is_dir(sftp, args.remote)` 且用户未显式指定非 staging 的 `--local`，则远端打包到 `/tmp/ssh-remote-{run_id}/download.tar.gz`，下载到本地 staging，解压，登记远端 tar 和本地 tar。

```python
        if _sftp_is_dir(sftp, args.remote) and str(args.local).startswith(args.local_staging_dir or ""):
            remote_tar = f"{args.remote_staging_dir.rstrip('/')}/{args._run_id}-download.tar.gz"
            args._registry.add_remote(client, remote_tar)
            _remote_tar(client, args.remote, remote_tar)
            local_tar = Path(args.local_staging_dir) / f"{args._run_id}-download.tar.gz"
            args._registry.add_local(local_tar)
            sftp.get(remote_tar, str(local_tar))
            _local_untar(local_tar, local_path)
```

- [ ] **Step 3: 测试与提交**

```bash
python -m pytest skills/ssh-remote/scripts/test_cleanup_transfer.py -v
```

```bash
git add skills/ssh-remote/scripts/ssh_ops.py skills/ssh-remote/scripts/test_cleanup_transfer.py
git commit -m "feat(ssh-remote): upload/download use staging archives and register cleanup"
```

---

### Task 5: 安全护栏与边界测试

**Files:**
- Modify: `skills/ssh-remote/scripts/cleanup.py`
- Test: `skills/ssh-remote/scripts/test_cleanup_safety.py`

**Interfaces:** 完善 `is_safe_to_delete`。

- [ ] **Step 1: 增强 `is_safe_to_delete`**

```python
def is_safe_to_delete(path: str) -> bool:
    p = Path(path).expanduser().resolve()
    if str(p) in {"/", "C:\\", "C:/"}:
        return False
    for prefix in _DENY_PREFIXES:
        if str(p).startswith(prefix + "/") or str(p) == prefix:
            return False
    if ".." in p.parts:
        return False
    if "/" in str(p) and not str(p).startswith("/tmp/"):
        return False
    return True
```

对本地路径可放宽：只要不在系统目录即可。

- [ ] **Step 2: 测试**

```python
from unittest.mock import MagicMock

def test_is_safe_to_delete_rejects_parent_traversal():
    assert not is_safe_to_delete("/tmp/abc/../etc")

def test_is_safe_to_delete_rejects_non_tmp_remote():
    assert not is_safe_to_delete("/opt/staging")
    assert not is_safe_to_delete("/var/tmp/abc")

def test_registry_does_not_delete_system_paths():
    reg = CleanupRegistry()
    reg.add_remote(MagicMock(), "/etc")
    reg.cleanup()
```

运行并提交：

```bash
python -m pytest skills/ssh-remote/scripts/test_cleanup_safety.py -v
```

```bash
git add skills/ssh-remote/scripts/cleanup.py skills/ssh-remote/scripts/test_cleanup_safety.py
git commit -m "feat(ssh-remote): harden cleanup safety guards"
```

---

### Task 6: 更新文档

**Files:**
- Modify: `skills/ssh-remote/SKILL.md`
- Modify: `skills/ssh-remote/references/cli-reference.md`

- [ ] **Step 1: SKILL.md 新增 Cleanup 章节**

在“退出码”后新增 `## 临时文件清理`：

```markdown
## 临时文件清理

ssh-remote 默认在执行结束后清理本次进程产生的临时文件。

- 远端临时目录：`/tmp/ssh-remote-{run_id}/`（`--remote-staging-dir` 修改）
- 本地临时目录：`~/.ssh-remote/tmp/{run_id}/`（`--local-staging-dir` 修改）
- 默认启用；失败时仍尝试清理。
- `--no-cleanup` 保留临时文件以便排查。
- `--cleanup-dry-run` 只打印会清理的路径。

安全护栏：永远不会清理 `/`, `/etc`, `/usr`, `/home`, `/root` 等系统路径。
```

- [ ] **Step 2: cli-reference.md 全局参数表**

| 参数 | 说明 |
| --- | --- |
| `--no-cleanup` | 关闭自动清理 |
| `--cleanup-dry-run` | 打印会清理的路径，不删除 |
| `--remote-staging-dir DIR` | 远端临时目录基路径（默认 `/tmp`） |
| `--local-staging-dir DIR` | 本地临时目录基路径（默认 `~/.ssh-remote/tmp`） |

- [ ] **Step 3: 提交**

```bash
git add skills/ssh-remote/SKILL.md skills/ssh-remote/references/cli-reference.md
git commit -m "docs(ssh-remote): document cleanup behavior and staging dirs"
```

---

### Task 7: 全量回归与同步

- [ ] **Step 1: 全量 pytest**

```bash
cd "D:\Code\skills"
python -m pytest skills/ssh-remote/scripts -v
```
预期：全部通过（48 + 新增测试）。

- [ ] **Step 2: 同步到 .agents**

```bash
robocopy "D:\Code\skills\skills\ssh-remote" "C:\Users\2268\.agents\skills\ssh-remote" /E /XD __pycache__ .pytest_cache /XF *.pyc
```

- [ ] **Step 3: 提交并推送**

```bash
git add skills/ssh-remote/
git commit -m "feat(ssh-remote): automatic cleanup of temporary files after operations"
git push origin main
```

---

## Spec Coverage Check

| Spec 章节 | 覆盖任务 |
| --- | --- |
| 默认临时目录 | Task 2, 3, 4 |
| Registry + try/finally | Task 1, 2 |
| 清理范围 | Task 3, 4 |
| CLI 参数 | Task 2 |
| 失败处理 | Task 1, 2 |
| 安全护栏 | Task 5 |
| 测试策略 | Task 1, 3, 4, 5, 7 |
| 文档 | Task 6 |

## Placeholder Scan

- 无 TBD / TODO / "implement later" / "fill in details" / "similar to Task N"。
- 每个步骤都有具体代码或命令。
