# ssh-remote CLI Reference (v3)

> 完整记录 `scripts/ssh_ops.py` 的所有参数、退出码、约束与风险模式。SKILL.md 之后按需阅读。

## 全局参数（所有子命令通用）

| 参数 | 说明 |
| ---- | ---- |
| `--session ALIAS` | 从 `~/.config/ssh_remote_config.json` 预填 `--host/--user/--port/--key-file`；CLI 显式给的覆盖 session；不传时使用 `defaults.host` 设定的默认别名 |
| `--host HOST` | 远端主机或 IP |
| `--port N` | SSH 端口，默认 22 |
| `--user USER` | 远端用户名 |
| `--label TEXT` | 人类可读标签，会被打印在确认提示里 |
| `--password PASS` | 远端密码，**优先级最高**；配置中已有密码可省略 |
| `--key-file PATH` | SSH 私钥路径（与 `auth.type=key-file` 配合） |
| `--no-password-with-key` | 用了 `--key-file` 就不再用密码字段当私钥口令 |
| `--timeout N` | 网络/认证超时，默认 15s |
| `--trust-host` | 自动信任未知 host key（仅首次连陌生主机） |
| `--host-key PATH` | 显式指定 known_hosts 文件 |
| `--insecure` | 接受任何 host key（**危险**，慎用） |
| `--yes` | 跳过主机确认；调用前**必须**已在聊天里确认 |
| `--i-know` | 跳过高/极高危 token 确认；调用前**必须**已在聊天里确认风险 |

## 密码读取优先级（高 → 低）

1. `--password` 显式参数
2. 配置文件 `hosts[alias].password`（明文）

> 已移除 `SSH_PASSWORD` / `SSH_PASSWORD_{ALIAS}` 环境变量。

## 子命令

### `test`
只连一次 SSH 不跑任何破坏性命令。输出：

- `[OK] connected to <host>:<port>`
- host key 类型 + fingerprint
- `uname -a` 和 `/etc/os-release`

### `exec`
- 必填：`command`（整条 shell 命令）
- 可选：`--cmd-timeout` 默认 600s
- 可选：`--sessions a,b,c` 或 `--all` 走批量
- 输出：远端 stdout → 本地 stdout，远端 stderr → 本地 stderr
- 退出码：透传远端命令的 exit code
- **风险门**：命令匹配 `HIGH_RISK_PATTERNS` 时弹一次性 `RUN-XXXXXX` token
- **约束门**：受 `read_only` / `denied_patterns` / `allowed_hours` / `require_double_confirm` 制约

### `upload`
- 必填：`--local`（可文件或目录）、`--remote`（远端绝对路径，POSIX 写法）
- 可选：`--mode 0755` 上传后立即 chmod
- 自动 `mkdir -p` 远端父目录
- **风险门**：远端路径在 `/etc` `/var` `/usr` `/boot` `/proc` `/sys` `/dev` `/lib` `/opt` `/root` `/bin` `/sbin` 之下，或 `--mode` 含 world-writable，弹 HIGH token
- **约束门**：受 `read_only` / `allowed_hours` 制约

### `download`
- 必填：`--remote`（POSIX 路径，自动识别文件/目录）、`--local`（本地落点）
- 本地父目录不存在会自动创建
- 不需要 token（下载到本地是低风险）

### `probe-net`
- 可选：`--targets url1 url2 …`、`--timeout2 N`（单次超时，默认 8s）
- 默认对 `github.com / baidu.com / pypi.org` 三个目标做 `curl`
- 退出码：至少一个目标 2xx/3xx → 0，否则 1
- 若目标主机/环境 `network_isolated=true`，执行前会先 WARN 提示该主机不该主动探测公网

### `session`
管理持久化目标。会话存储：**`~/.config/ssh_remote_config.json`**，POSIX 模式 `0600`。

| 子命令 | 必填 | 说明 |
| --- | --- | --- |
| `session add ALIAS` | `--host --user`（可选 `--key-file` / `--password` / `--network-isolated`） | 新建。`--password` 直接写入配置（明文）；`--network-isolated` 把 `constraints.network_isolated` 标记为对应值 |
| `session list` | - | 表格：alias / user@host:port / env / label / last_used / tags；带 `*` 的是 default |
| `session show ALIAS` | - | 详细字段（含 password 存在性，但不显示明文） |
| `session use ALIAS` | - | 设为 default；之后不传 `--session` 时自动用 |
| `session rm ALIAS` | - | 删除 |
| `session rename OLD NEW` | - | 改名 |

### `config`

| 子命令 | 必填 | 说明 |
| --- | --- | --- |
| `config show` | - | 打印完整配置 JSON，密码遮罩为 `***` |
| `config env list` | - | 列出所有 environment 及其约束 |
| `config env add NAME` | `--desc / --tags` | 新建环境 |
| `config env rm NAME` | - | 删除环境 |
| `config env set-constraints NAME` | `--read-only / --require-double-confirm / --denied-patterns / --allowed-hours / --network-isolated` | 修改环境级约束 |
| `config host list` | - | 等价于 `session list` |
| `config host add ALIAS` | `--host --user --key-file 或 --password` | 同 `session add` |
| `config host rm ALIAS` | - | 同 `session rm` |
| `config host set-constraints ALIAS` | `--read-only / --require-double-confirm / --denied-patterns / --allowed-hours / --network-isolated` | 修改主机级约束（覆盖环境级） |

约束参数取值：

- `--read-only true|false`：禁止 exec/upload
- `--require-double-confirm true|false`：每次 exec 都要 token
- `--denied-patterns PAT1 PAT2 ...`：空格分隔的正则列表，匹配即拒绝
- `--allowed-hours "09:00-18:00"`：本地时间窗口；空字符串清除限制
- `--network-isolated true|false`：标记为内网隔离，exec/upload 命中公网特征（curl/wget/yum/apt/pip install/...）即拒绝

## 退出码

| 码 | 含义 |
| -- | ---- |
| 0 | 成功 |
| 2 | 参数缺失 / 本地路径不存在 |
| 10 | TCP 层面连不上（防火墙、DNS、端口错） |
| 11 | SSH 协议错（banner 解析失败、协议不匹配） |
| 13 | 认证失败 |
| 14 | session alias 不存在 |
| 15 | 主机确认被用户拒绝，或 stdin 关闭 |
| 16 | 高危 token 失败 / 拒绝 / 无 stdin |
| 17 | 配置文件 JSON 损坏或格式错 |
| 18 | 约束拒绝（read_only / denied_patterns） |
| 19 | 时间窗口外（allowed_hours 不覆盖当前时间） |
| 其他 | 远端命令自身的 exit code |

## 风险模式分类

完整的 `HIGH_RISK_PATTERNS` 在 `scripts/ssh_ops.py`。结构：`(regex, level, reason)`。

### CRITICAL（系统级毁灭，要求 `--i-know` + 一次性 token，提示更响）

- `rm -rf /`、`rm /*`、`rm /`（带 `-r`/`-f`/`--no-preserve-root`）
- `dd of=/dev/sd*|hd*|nvme*|vd*|mmcblk*|xvd*|loop*` 等
- `cat/echo >/dev/sd*`、`tee /dev/sd*`
- `mkfs`/`fdisk`/`sfdisk`/`parted`/`wipefs` 作用在 `/dev/sd*` 等
- `chmod 000 /`、`chmod 777 /`
- `mv /*`、`mv /.`
- `umount /`、`umount -a`
- `chmod 4755 /bin/bash`、`chmod u+s`、`chmod +s`
- `setfacl -m`
- fork bomb `:(){ :|:& };:`
- `> /etc/passwd` / `/etc/shadow` / `/etc/sudoers` / `/etc/hosts` / `/etc/fstab`
- `>> /etc/rc.local` / `/etc/init.d/` / `/etc/cron.*` / `/etc/profile` / `/etc/profile.d/`
- `>> ~/.bashrc` / `~/.zshrc` / `~/.bash_profile` / `~/.profile`

### HIGH（破坏性但不毁灭）

- 任何 `rm -r`/`-f`/`--recursive`/`--force`
- `kill`/`killall`/`pkill`/`skill`/`taskkill`
- `systemctl/service` 的 stop/disable/mask/restart/reload/kill
- `systemctl enable/start/reload`（持久化/启服务）
- `reboot`/`shutdown`/`poweroff`/`halt`/`init [016]`
- `iptables`/`nft`/`ufw`/`firewall-cmd`
- `passwd`/`usermod`/`userdel`/`groupdel`/`chsh`
- `crontab -r/-l/-e` 或 heredoc 注入
- `insmod`/`modprobe`/`rmmod`
- `rsync --delete`
- `terraform apply`/`ansible-playbook`
- `npm publish`/`twine upload`/`docker|podman push`
- `docker system prune`/`docker volume prune`/`docker|podman rm -f`
- `kubectl delete --all`
- `ip addr flush`、`arp -d`
- `bash -i >& /dev/tcp/...`、`nc -e`、`python/perl/php` 反向 shell
- `history -c`
- 上传到系统路径、带 world-writable 模式

## 约束 vs 风险门

| 维度 | 来源 | 检查时机 |
| --- | --- | --- |
| `read_only` | 环境/主机 | exec / upload 入口 |
| `allowed_hours` | 环境/主机 | exec / upload 入口 |
| `network_isolated` | 环境/主机 | exec / upload 入口（命中公网特征即拒绝）；probe-net 仅 WARN |
| `denied_patterns` | 环境/主机 | exec 命令字符串 |
| `require_double_confirm` | 环境/主机 | exec 命令字符串 |
| `HIGH_RISK_PATTERNS` | 内置 | exec 命令字符串 |

两者独立生效：内置风险门与用户约束都需满足才会真正下发命令。

## 故障诊断

按症状分类的 runbook 详见 `references/troubleshooting.md`。