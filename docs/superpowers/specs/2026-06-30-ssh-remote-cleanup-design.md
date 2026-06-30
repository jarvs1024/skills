---
title: ssh-remote Cleanup 设计
date: 2026-06-30
status: draft
---

# ssh-remote Cleanup 设计

## 1. 目标与范围

在 `ssh-remote` skill 的执行流程中增加**自动清理临时文件**能力，使 `exec` / `upload` / `download` / `probe-net` 等命令产生的中间文件在流程结束后被自动删除。

范围：
- 默认开启；流程结束后无论成功/失败都尝试清理。
- 清理范围限定为**本次 `ssh_ops.py` 进程自己产生并登记为临时的文件和目录**。
- 不影响用户显式指定的上传/下载目标路径。
- 提供 `--no-cleanup` 关闭，提供 `--cleanup-dry-run` 只打印不删除。

## 2. 清理模型：Registry + try-finally

新增 `CleanupRegistry`（dataclass）集中管理临时路径：

```python
@dataclass
class CleanupRegistry:
    local_paths: list[Path]          # 本地临时路径
    remote_paths: list[tuple]      # (paramiko SSHClient, remote_path)

    def add_local(self, path: Path | str) -> None:
        """登记本地临时路径。"""

    def add_remote(self, client, remote_path: str) -> None:
        """登记远端临时路径。"""

    def cleanup(self, dry_run: bool = False) -> None:
        """先删远端，再删本地；dry_run 只打印不删除。"""
```

在 `main()` 中实例化 Registry，并用 `try/finally` 保证清理一定执行：

```python
registry = CleanupRegistry()
try:
    return dispatch_command(args, registry)
finally:
    if not args.no_cleanup:
        registry.cleanup(dry_run=args.cleanup_dry_run)
```

各命令函数（`cmd_exec`、`cmd_upload`、`cmd_download`、`cmd_probe_net`）在产生临时文件时调用 `registry.add_local()` / `add_remote()` 登记。

## 3. 默认临时目录

每次运行生成唯一 `run_id`：

```python
run_id = f"{int(time.time() * 1000)}-{secrets.token_hex(2)}"
```

- **远端**：`/tmp/ssh-remote-{run_id}/`
- **本地**：`~/.ssh-remote/tmp/{run_id}/`（Windows：`%USERPROFILE%\.ssh-remote\tmp\{run_id}\`）

命令产生中间文件时默认落到这些目录并登记。用户可通过 `--remote-staging-dir` / `--local-staging-dir` 覆盖。

## 4. 清理范围

会被清理的内容：

| 场景 | 登记内容 |
| --- | --- |
| `upload` 本地先打包 | 本地压缩包 |
| `upload` 上传到远端 staging | 远端 staging 目录 |
| `exec` 输出重定向到 staging | 远端 staging 输出文件 |
| `download` 远端先打包 | 远端打包文件 |
| `download` 落到本地 staging | 本地 staging 文件 |
| `probe-net` 本地日志 | 本地日志文件 |

**不会被清理**（避免误删）：
- 用户显式 `--local` / `--remote` 的路径
- `--cleanup-paths` 之外的重要系统路径
- 根目录 `/` 或 `/etc` `/usr` `/home` `/root` 等系统目录

## 5. CLI 参数

| 参数 | 含义 |
| --- | --- |
| `--no-cleanup` | 关闭本次清理 |
| `--cleanup-dry-run` | 打印会清理哪些路径，不删除（主命令成功执行） |
| `--cleanup-remote-paths PATH[,PATH]` | 额外指定要清理的远端路径（逗号分隔） |
| `--cleanup-local-paths PATH[,PATH]` | 额外指定要清理的本地路径（逗号分隔） |
| `--remote-staging-dir DIR` | 覆盖远端默认临时目录 |
| `--local-staging-dir DIR` | 覆盖本地默认临时目录 |

`--no-cleanup` 优先级最高：一旦指定，自动清理和用户显式指定的额外路径都不会被删除。`--cleanup-dry-run` 不会跳过清理逻辑，只是把删除动作替换成打印。

## 6. 失败处理

- 清理逻辑放在 `finally` 中，失败时也会执行。
- 清理失败只打印 warning，**不改变主命令的退出码**。
- 清理顺序：先远端后本地，避免本地文件删了但远端残留。
- 如果 `cleanup` 过程中出现异常，捕获并打印后继续执行，避免影响 `finally` 后续流程。

## 7. 安全护栏

- 禁止清理以下路径（解析 `realpath` 后匹配）：
  - 根目录 `/`
  - 系统目录：`/etc`, `/usr`, `/var`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/boot`, `/proc`, `/sys`, `/dev`
  - 用户主目录本身（如 `/home/tester` 或 `/root`）
  - Windows 系统盘根目录（如 `C:\`）和用户目录本身（如 `C:\Users\tester`）
- 禁止清理包含 `..` 或解析后跳出版图根目录的路径。
- `--cleanup-paths` 命中系统路径时必须搭配 `--i-know` 确认；否则拒绝并退出码 `EXIT_CONSTRAINT_DENIED`。

## 8. 测试策略

- 新增 `scripts/test_cleanup.py`：Registry 本地增删、dry-run、失败不影响主退出码。
- 新增 `scripts/test_cleanup_safety.py`：系统路径拒绝、路径逃逸防护、`--i-know` 门控。
- 在 `test_ssh_ops_*.py` 中增加集成用例：验证 `exec`/`upload`/`download` 执行后 staging 目录被删除。

## 9. 实现顺序

1. 在 `ssh_ops.py` 中实现 `CleanupRegistry`。
2. 在 `main()` 中注入 `try/finally` 清理流程。
3. 修改 `cmd_upload` / `cmd_download` / `cmd_exec` / `cmd_probe_net`，把过程产生的临时文件登记到 Registry。
4. 新增 CLI 参数：`--no-cleanup`、`--cleanup-dry-run`、`--cleanup-paths`。
5. 补充安全护栏与错误处理。
6. 更新 `SKILL.md` 与 `references/cli-reference.md` 说明清理行为。
7. 添加测试用例并跑全量 pytest 验证。

## 10. 非目标

- 不清理用户历史配置文件 `~/.config/ssh_remote_config.json`。
- 不清理用户已有的远端目录（如 `/opt` 下长期存在的安装目录）。
- 不提供跨会话的持久化清理列表（每次运行独立管理）。
- 禁止清理包含 `..` 或解析后跳出版图根目录的路径。
- `--cleanup-remote-paths` 和 `--cleanup-local-paths` 命中系统路径时必须搭配 `--i-know` 确认；否则拒绝并退出码 `EXIT_CONSTRAINT_DENIED`。
