# Troubleshooting

> ssh-remote 常见问题的诊断与处置。按现象分类，建议把本文链接挂在 SKILL.md 之外当作随手工具。

## A. 连不上

| 现象 | 可能原因 | 处置 |
| ---- | -------- | ---- |
| `Connection refused` | sshd 没开 / 端口错 / 安全组 | `test -Connection -Port 22 <host>`；找运维确认端口 |
| `Connection timed out` | 路由不通 / 防火墙挡 | 找运维排查网络；用户确认 IP 是否可达 |
| `No route to host` | 主机不可达 / VPN 没拨 | 检查本机 VPN/代理，重试 |
| `Name or service not known` | DNS 解析失败 | 确认是否能 `Resolve-DnsName <host>`；不行就用 IP |
| `Server host key mismatch` | 远端重装过系统 | `cat ~/.ssh/known_hosts \| grep <host>` 删除旧条目，或显式 `--trust-host` |

## B. 认证失败

| 现象 | 可能原因 | 处置 |
| ---- | -------- | ---- |
| `Permission denied (publickey)` | 私钥权限过宽 (0666 / 0755) | `icacls C:\Users\2268\.ssh\id_rsa /inheritance:r /grant:r "$env:USERNAME:(R)"` |
| `Permission denied (password)` | 用户名错 / 密码错 | 让用户再确认；推荐改用密钥 |
| `disc too many authentication failures` | sshd 只允许 3-5 个 key 试错 | `exec` 加 `IdentitiesOnly=yes`（脚本未支持，建议加 `-o`） |
| `passphrase required but not provided` | 私钥带口令但没给 | 设置 `$env:SSH_PASSWORD = '<passphrase>'` |
| `paramiko: Incompatible SSH peer` | 远端 OpenSSH 太新协议 (RFC 8308 ext-info) | 升级 paramiko 到 ≥ 2.9；先 `pip install -U paramiko` |

## C. SFTP 问题

| 现象 | 可能原因 | 处置 |
| ---- | -------- | ---- |
| `IOError: Failure` 上传 | 远端磁盘满 / 权限 | `exec df -h`、换目录、给 sudo |
| `IOError: No such file` | 远端目录不存在 | `cmd_upload` 会自动 `mkdir -p`；查 stderr 警告 |
| 目录下载空 | `_sftp_get_dir` 列表权限不足 | 改用 `tar -C /path -czf -` 然后下载 `.tar.gz` |
| 速度慢 | 高 RTT / 丢包 | 改 scp/sftp window，加 `-o Compression=yes`（默认 OpenSSH；脚本不支持） |

## D. 命令执行问题

| 现象 | 可能原因 | 处置 |
| ---- | -------- | ---- |
| 远端输出乱码 | LANG 没 UTF-8 | 脚本默认注入 `LC_ALL=C.UTF-8`；如远端无该 locale，手动 `export LC_ALL=en_US.UTF-8` |
| `exec` 卡住 | stdin 没关 | 脚本里 `stdin.write(''); stdin.channel.shutdown_write()` 即可（当前未实现，请用户命令自加 `< /dev/null`） |
| `Operation not permitted` | SELinux / AppArmor | 让运维修策略，或换 `--user` |
| `sudo: sorry, you must have a tty…` | 需要 TTY | 让用户先 `ssh -t`，或在 sudoers 配 `Defaults !requiretty`（脚本不做 sudo 提权） |

## E. 离线模式错误

| 现象 | 处置 |
| ---- | ---- |
| `probe-net` 全 `CURL_FAIL` | 远端没 `curl` → 用 `python3 -c "import urllib.request"` 探一下；或直接进入「离线模式」走本地下载 |
| 远端 `pip install --no-index` 找不到包 | 传输 `pip download` 的 wheel 目录 + `find-links` 指向它 |
| 远端 `apt-get` 报仓库不存在 | 编辑 `/etc/apt/sources.list.d/*.list`，加 `Acquire::http::Proxy=` 走代理 |

## F. Windows / PowerShell 兼容

| 现象 | 处置 |
| ---- | ---- |
| 行继续符 `\` 被识别成换行 | 改用 PowerShell 反引号 `` ` ``，或把整条命令用双引号包起来 |
| 中文路径上传 / 下载乱码 | 脚本默认走 UTF-8；如乱码，先在本机执行 `chcp 65001` |
| `paramiko` 报告 `cryptography` 缺失 | `pip install cryptography` 或 `pip install paramiko[all]` |
| `scp.exe` 找不到 | `Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0` |