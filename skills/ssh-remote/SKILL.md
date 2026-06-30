---
name: ssh-remote
description: SSH 远程操作 skill — 通过 ~/.config/ssh_remote_config.json 统一管理主机与连接，凭据可明文保存在配置中；支持环境分组约束、主机级只读模式、网络隔离模式（自动拒绝公网操作）。Use when the user wants to SSH to / run commands on / upload or download files from / probe network on a remote Linux host, manage SSH host aliases in a config file, or enforce environment-level constraints (read-only / time window / denied command patterns) on remote operations.
---

# ssh-remote

> 通过 SSH 远程登录并执行命令、上传/下载文件、探测网络。所有主机信息统一存在 `~/.config/ssh_remote_config.json`，明文密码亦存于该文件（POSIX 强制 0600；Windows 警告权限），按需读写。

## 触发方式

| 触发语 | 含义 |
| --- | --- |
| `连到 <别名>` / `ssh <别名>` | 触发 test 子命令连通指定主机 |
| `在 <别名> 上跑 <命令>` / `exec ...` | 执行远端命令 |
| `把 <本地路径> 上传到 <别名>` | upload |
| `从 <别名> 拉 <远端路径>` | download |
| `查 <别名> 网络` | probe-net |
| `添加主机 <别名>` / `新主机` | session add |
| `列出主机` / `查主机` | session list |
| `导出配置` / `config show` | 查看当前配置（密码遮罩） |

> 调用入口固定为 `python scripts/ssh_ops.py ...`，所有参数与 v3 schema 对齐。

## 配置文件位置

按以下优先级解析：

1. `$SSHR_CONFIG_DIR/ssh_remote_config.json`
2. `$XDG_CONFIG_HOME/ssh_remote_config.json`
3. `~/.config/ssh_remote_config.json`（Windows 为 `%USERPROFILE%\.config\ssh_remote_config.json`）

## 配置 schema（v3）

```json
{
  "version": 3,
  "defaults": {"host": "lab-nvme-01", "env": "lab"},
  "environment": {
    "prod": {
      "description": "生产环境",
      "tags": ["prod"],
      "constraints": {
        "read_only": false,
        "require_double_confirm": true,
        "denied_patterns": ["reboot", "shutdown"],
        "allowed_hours": "09:00-18:00"
      }
    },
    "lab": {
      "description": "实验室测试",
      "tags": ["lab"],
      "constraints": {
        "read_only": false,
        "require_double_confirm": false,
        "denied_patterns": [],
        "allowed_hours": null
      }
    }
  },
  "hosts": {
    "lab-nvme-01": {
      "host": "192.168.10.21",
      "port": 22,
      "user": "tester",
      "password": "PlainTextPassword",
      "auth": {"type": "password"},
      "environment": "lab",
      "label": "NVMe 测试机 01",
      "tags": ["nvme", "fio"],
      "constraints": {"read_only": false},
      "created": "2026-06-30T10:00:00",
      "last_used": "2026-06-30T10:00:00"
    }
  }
}
```

## 约束引擎

约束合并顺序：`defaults < environment < host`（后者覆盖前者）。

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `read_only` | bool | 为 `true` 时禁止 `exec` 和 `upload`；`test`/`probe-net`/`download` 仍可执行 |
| `require_double_confirm` | bool | 为 `true` 时，任何 `exec` 都需先确认主机再输入一次性 token |
| `denied_patterns` | list[str] | 正则列表；命令匹配任一正则即拒绝，退出码 18 |
| `allowed_hours` | str \| null | `"HH:MM-HH:MM"` 本地时间窗口；非窗口期内 `exec`/`upload` 拒绝，退出码 19 |
| `network_isolated` | bool | 主机/环境处于内网隔离；exec/upload 命令若显式需要公网（curl/wget/yum/apt/pip install/...）会被直接拒绝，退出码 18；`probe-net` 直接拒绝执行（避免触发出口探测），退出码 18 |

## 密码读取优先级

1. `--password` 显式参数
2. 配置文件 `hosts[alias].password`（明文）

> 已移除 `SSH_PASSWORD` / `SSH_PASSWORD_{ALIAS}` 环境变量读取，密码统一只从配置和 CLI 来。

## CLI 子命令

| 子命令 | 用途 |
| --- | --- |
| `test` | 连一次 SSH 并打印 host key + uname + /etc/os-release |
| `exec <command>` | 跑远端命令；支持 `--sessions a,b,c` 或 `--all` 批量 |
| `upload --local X --remote Y` | 上传文件或目录；`--mode 0755` 调整权限 |
| `download --remote Y --local X` | 下载文件或目录 |
| `probe-net` | curl 默认目标检查远端是否可出公网 |
| `session add/list/show/use/rm/rename` | 别名管理（基于 v3 配置） |
| `config show` | 打印完整配置（密码遮罩为 `***`） |
| `config env add/list/rm/set-constraints` | 环境与约束管理 |
| `config host add/list/rm/set-constraints` | 主机与约束管理 |

完整参数说明见 `references/cli-reference.md`。

## 退出码

| 码 | 含义 |
| -- | ---- |
| 0 | 成功 |
| 2 | 参数缺失 / 本地路径不存在 |
| 10 | TCP 层面连不上 |
| 11 | SSH 协议错 |
| 13 | 认证失败 |
| 14 | session alias 不存在 |
| 15 | 主机确认被拒绝 / stdin 关闭 |
| 16 | 高危 token 失败 / 拒绝 |
| 17 | 配置文件 JSON 损坏 |
| 18 | 约束拒绝（read_only / denied_patterns） |
| 19 | 时间窗口外 |
| 其他 | 远端命令自身的 exit code |

## 风险模式

保留 v1 高危命令门（`HIGH_RISK_PATTERNS`），分 critical / high 两级。critical 命令会强制要求 `--i-know` + 一次性 `RUN-XXXXXX` token。

## 密码安全提示

> 配置文件含明文密码；务必：

- POSIX：确认文件权限为 0600（启动时若检测到过宽会打印警告）
- Windows：建议将该文件所在目录加入 EFS 或限制 ACL
- 共享主机：慎用 `--password` 参数；优先使用 key-file
- 切勿把配置文件提交到 Git 仓库或上传到任何位置

## 离线 / 内网

远端无公网时，先 `probe-net` 确认；离线模式参见 `references/offline-workflow.md`。

## 故障诊断

按症状分类的 runbook 详见 `references/troubleshooting.md`。

## 自动化约定

- Codex / Claude 调用前应已在聊天里确认目标主机与命令。
- 调用 `exec` / `upload` 时务必带上 `--yes` 与 `--i-know`（如已确认）。
- 涉及 batch / 多主机时再用 `--sessions a,b,c` 或 `--all`，由 skill 走 batch 流程。

## 验证

```bash
cd C:/Users/2268/.claude/skills/ssh-remote
python -m pytest scripts/ -v
```

期望：路径 / 约束 / 配置三类测试全部通过（当前 37 用例）。
