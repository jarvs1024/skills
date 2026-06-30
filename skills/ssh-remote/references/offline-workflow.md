# Offline / 内网隔离工作流

> 测试服务器通常无法直接访问公网。本文给出「远端可能不可达公网」场景下的标准操作流。

## 判断流程

1. 第一次连上远端，**先** `probe-net`，3 个默认目标若全部 `[OFFLINE]` → 进入「离线模式」。
2. 用户本来也可能已告知「在内网」，此时跳过 `probe-net`，直接进入「离线模式」。

## 离线模式原则

> 「**Anything you want on the remote, stage it locally first.**」

任何要在远端跑 / 安装 / 拉取的东西：
1. 在本机 PowerShell / 浏览器下载、构建、校验。
2. 传给 `ssh_ops.py upload`，落到远端 `/tmp` 或 `~/transfer/`。
3. `ssh_ops.py exec` 在远端做安装 / 解压 / 拷贝 / 跑测试。

## 典型套路

### A. 装一个 pip 包（无法 `pip install`）

1. 本地：`pip download requests==2.32.3 -d $env:USERPROFILE\pkgs --only-binary=:all: --platform manylinux2014_x86_64`
2. 上传：`ssh_ops.py ... upload --local $env:USERPROFILE\pkgs --remote ~/pkgs`
3. 远端：`ssh_ops.py ... exec -- "cd ~/pkgs && pip install --no-index --find-links . requests"`

### B. 装一个二进制（fio / perf / stress-ng 等）

1. 本地：`Invoke-WebRequest` 或 `curl` 拉到本地。
2. 上传 + 在远端 `chmod +x`、放到 `~/bin/`。
3. 需要时 `exec` 自带的 `Makefile` 在远端构建（前提：gcc 已装）。

### C. 拉一份代码仓库并跑测试

1. 本地：`git clone` 到 `$env:USERPROFILE\repo`。
2. 打包 + 上传：`Compress-Archive` / `7z` 后 `ssh_ops.py upload`。
3. 远端 `exec` 解压 → 编译 → 跑用例 → 把日志 `download` 回来。

### D. 抓远程日志 / 数据

- 用 `ssh_ops.py download --remote /path --local ./out` 拉文件或目录树。
- **大文件优先压缩再传**：先 `exec` 在远端 `tar czf /tmp/lo.gz /var/log/...`，再 `download`。

### E. 远端有外网，但要装内部源

- 走 `probe-net` 验证后再装。
- pip：`pip install -i http://internal-pypi.xxx/simple ...`
- apt：`/etc/apt/sources.list.d/` 加内部源后再 `apt-get install`。

## 离线模式推荐参数

| 场景 | 推荐参数 |
| ---- | ---- |
| 大文件 (GB 级) | `upload` 自动走 SFTP 4 KiB 块；如丢包严重可先用 `exec` 远端 `tar -c` + `upload` 块 + `exec` `tar -x` |
| 频繁跑命令 | 脚本会自动复用 SFTP；同一 `--host` 可以连开多次 |
| 想持久化心跳 | 自己 `exec` `keepalive` 写 cron（脚本不内置） |

## 反例（禁止）

- 离线环境下直接远端 `pip install …` → `probe-net` 都没做过就盲猜远端可联网。
- 把大目录放在 SFTP 「同步式」上传不打包 → 几万个文件会非常慢。
- 把本地 `~/.ssh/id_rsa` 上传到远端「备用」 → 凭据大忌。