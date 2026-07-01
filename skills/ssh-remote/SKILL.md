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

## network_isolated 内部镜像源白名单

设置 `network_isolated: true` 的 host 默认拒绝公网访问。ssh-remote 区分"内网目标"与"公网目标"，
放行内网镜像源：

- 显式 URL：host 是 RFC1918 / loopback / link-local / `.internal` `.local` `.corp` `.lan` `.intranet` → 放行
- 无显式 URL：探测远端默认源（pip.conf / npm config / yum repolist / Maven / Go env），全内网 → 放行
- 探测失败或默认源为公网 → 拒绝并提示配置源

绕过：

- 命令里显式指向内网源：`pip install -i http://pypi.corp/simple ...`
- 远端配置全局 mirror 后重跑
- 临时放行：`--allow-internal-mirror`
- probe-net 公网目标用 `--allow-public-probe`

详细判定逻辑、probe-net 处理、绕过示例：见 [references/network_isolated.md](references/network_isolated.md)。

## 临时文件清理

ssh-remote 默认在执行结束后清理本次进程产生的临时文件，无论成功或失败。

- 远端 staging 目录：`/tmp/ssh-remote-{run_id}/`（可通过 `--remote-staging-dir` 修改基路径）
- 本地 staging 目录：`~/.ssh-remote/tmp/{run_id}/`（可通过 `--local-staging-dir` 修改）
- `exec` 命令自动创建 `/tmp/ssh-remote-{run_id}/` 并将路径注入到命令的 `SSH_REMOTE_TMP` 环境变量；命令可直接用此目录暂存文件
- `upload` / `download` 当目标路径落在 staging 目录内时会被登记到清理列表
- 默认开启；失败时仍尝试清理（清理失败只 warn，不改变主命令退出码）
- 使用 `--no-cleanup` 保留临时文件以便排查
- 使用 `--cleanup-dry-run` 只打印会清理的路径，不删除

安全护栏：

- 远端清理路径必须以 `/tmp/` 开头；`/etc` `/usr` `/home` `/root` 等系统目录拒绝清理
- 本地清理路径禁止是 Windows 系统目录（`C:\Windows` 等）或用户主目录本身
- 含 `..` 的路径或解析后跳出 staging 的路径被拒绝


## 风险模式

保留 v1 高危命令门（`HIGH_RISK_PATTERNS`），分 critical / high 两级。critical 命令会强制要求 `--i-know` + 一次性 `RUN-XXXXXX` token。

## AI 调用前确认清单（强制）

> 本 skill 由 AI 在对话中调用。AI **必须**在调用前完成以下确认，**不得**擅自推断或默认执行。

### 1. 环境信息不确定时，必须反问用户

以下任一情况缺失或模糊时，AI 要停下来向用户确认或请求补充，不能直接猜：

- 目标主机别名/地址未给出，或别名不在 `session list` 中
- 用户说"那台机器"、"测试机"等不唯一指向
- 目标主机密码未配置且用户未提供 `--password`
- 用户命令里包含相对路径、通配符、环境变量等可能因主机不同而解析出错的片段
- 不确定目标是 `lab` / `prod` / `internal` 等环境

示例：

> "你说‘在测试机上跑’，但配置里有 lab-nvme-01 / lab-nvme-02 / lab-sata-01。请确认具体是哪一台，或者我帮你列出所有主机。"

### 2. 涉及服务器数据的删除/修改/重启，必须用户先确认

以下操作在聊天中**必须**得到用户明确同意（口头/文字"可以"/"执行"/"确认"）后，AI 才能带 `--yes --i-know` 调用：

- `rm` / `dd` / `mkfs` / `fdisk` / `wipefs` / `shred` / `truncate` 等删除/覆写数据
- `chmod` / `chown` 大范围改权限
- `systemctl stop/disable/mask/restart` / `reboot` / `shutdown` / `poweroff`
- 写入 `/etc/*`、`/boot/*`、systemd unit、crontab、profile.d 等系统文件
- `iptables` / `nft` / `firewall-cmd` 改防火墙
- `passwd` / `userdel` / `usermod` / `groupdel` 改账号
- 上传文件覆盖远端系统路径或重要配置文件
- 任何对生产环境（prod）的 exec / upload

> 禁止：用户只说"清理一下"，AI 就直接 `rm -rf`；用户只说"重启"，AI 就直接 `reboot`。

### 3. 读-only / 诊断操作也要先确认目标

`test`、`probe-net`、`download`、`session list`、`config show` 虽然不修改远端，但如果目标主机不确定，AI 仍应先确认：

> "要查哪台主机的网络？"

### 4. `--yes` 与 `--i-know` 的使用纪律

- `--yes`：仅在用户**已经在当前对话中确认过目标主机**时使用
- `--i-know`：仅在用户**已经在当前对话中确认过高危操作风险**时使用
- 严禁：为了绕过确认流程而自动加 `--yes` / `--i-know`

### 5. 批量操作更严格

使用 `--sessions a,b,c` 或 `--all` 前，AI 必须：

- 列出会受影响的主机清单
- 说明命令/上传内容
- 得到用户明确同意

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

> 完整规则见上文"AI 调用前确认清单（强制）"。下面是速记版：

- Codex / Claude 调用前应已在聊天里确认目标主机与命令。
- 调用 `exec` / `upload` 时务必带上 `--yes` 与 `--i-know`（如已确认）。
- 涉及 batch / 多主机时再用 `--sessions a,b,c` 或 `--all`，由 skill 走 batch 流程。

## 验证

```bash
cd C:/Users/2268/.claude/skills/ssh-remote
python -m pytest scripts/ -v
```

期望：路径 / 约束 / 配置 / 超时四类测试全部通过（当前 48 用例）。
