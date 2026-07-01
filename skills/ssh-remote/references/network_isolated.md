# network_isolated 内部镜像源白名单

当 host 设置 `network_isolated: true` 时，ssh-remote 默认拒绝所有"看起来需要公网"的命令。但实际场景中内网镜像源（pip/npm/Maven/yum/dnf/Go 内部源）应被放行。本文档说明判定规则和绕过方法。

## 判定流程

ssh-remote 对 `network_isolated` 主机执行命令的判定逻辑：

1. **`--allow-internal-mirror` 已设置** → 直接放行（带 WARN 日志）
2. **命令不含公网关键字**（curl/wget/yum/apt/dnf/pip install/npm install 等）→ 放行
3. **命令含公网关键字 + 含显式 URL**：
   - URL host 在 RFC1918 私有 IP / loopback / link-local / `.internal` `.local` `.corp` `.lan` `.intranet` 等后缀 → 放行
   - URL host 是公网域名或 IP → 拒绝
4. **命令含公网关键字 + 无显式 URL**（如裸 `yum install foo`）：
   - 在远端探测默认 mirror 配置（pip.conf / npm config / yum repolist / Maven settings.xml / `go env GOPROXY`）
   - 默认源全部为内网 → 放行
   - 默认源为公网 / 探测失败 → 拒绝并提示

## 绕过方法

### 1. 命令里显式指向内网源

```bash
# pip
python scripts/ssh_ops.py exec --session lab -- "pip install -i http://pypi.corp/simple requests"

# npm
python scripts/ssh_ops.py exec --session lab -- "npm install --registry http://npm.corp/"

# yum (通过 baseurl 显式指向内网源)
python scripts/ssh_ops.py exec --session lab -- "yum install -y htop --enablerepo=internal"
```

### 2. 远端配置全局 mirror

```bash
# pip - 在远端配置
python scripts/ssh_ops.py exec --session lab -- "pip config set global.index-url http://pypi.corp/simple"
python scripts/ssh_ops.py exec --session lab -- "pip install requests"  # 之后裸 pip 就走内网源

# npm
python scripts/ssh_ops.py exec --session lab -- "npm config set registry http://npm.corp/"
```

### 3. 用 `--allow-internal-mirror` 强行放行

```bash
python scripts/ssh_ops.py --allow-internal-mirror exec --session lab -- "pip install requests"
```

⚠️ 此标志跳过 mirror 判定，会执行命令并可能触发公网访问。仅在你确认远端 mirror 不可达但需要临时绕过时使用。

## probe-net 的处理

`probe-net` 默认测公网目标（github.com, baidu.com, pypi.org），在 `network_isolated` 主机上会拒绝。

绕过方式：
- 用 `--targets` 限定内网目标：`probe-net --targets http://10.0.0.1:8080`
- 或加 `--allow-public-probe` 显式允许公网探测

## 退出码

| 场景 | 退出码 |
| --- | --- |
| network_isolated 拒绝执行 | `18` (EXIT_CONSTRAINT_DENIED) |
| probe-net 公网目标被拒 | `20` (EXIT_NETWORK_ISOLATED_PROBE) |
