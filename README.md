# jarvs1024/skills

个人 Codex / Claude skill 集合。每个 skill 是**自包含、跨平台、可独立安装**的模块, 用同样的目录结构同时支持两个客户端。

## 支持的客户端

| 客户端 | 触发方式 | skill 路径 | 文档 |
|---|---|---|---|
| **Codex** (桌面 / CLI) | 自动 (匹配 description 字段) | `~/.codex/skills/<name>/` | — |
| **Claude Code** (CLI) | 手动输入 `/$skill-name` | `~/.claude/skills/<name>/` | [Claude Code skills 文档](https://docs.claude.com/en/docs/claude-code/skills) |

两个客户端的 skill 文件结构**完全一致** (`SKILL.md` + `references/` + `scripts/` + `agents/openai.yaml`), 本仓库直接装两份即可。

## 目录

- [可用 skill 列表](#可用-skill-列表)
- [安装 skill (Codex)](#安装-skill-codex)
  - [macOS / Linux](#macos--linux-codex)
  - [Windows](#windows-codex)
- [安装 skill (Claude Code)](#安装-skill-claude-code)
  - [macOS / Linux](#macos--linux-claude)
  - [Windows](#windows-claude)
- [使用 skill](#使用-skill)
- [添加新 skill](#添加新-skill)
- [升级 skill](#升级-skill)
- [仓库布局](#仓库布局)

## 可用 skill 列表

| Skill | 简介 | 主要场景 |
|---|---|---|
| [**weekly-report**](skills/weekly-report/) | 周报生成 + 工作流水账, 输出公司风 .xlsx | 每天随手记工作 / 周四一键出周报 / 修改历史记录 |

> 后续会持续添加新 skill, 上表会同步更新。

---

## 安装 skill (Codex)

通过 Codex 自带的 `skill-installer` 装到 `~/.codex/skills/`, 启动 Codex 时自动加载。

### macOS / Linux (Codex)

前置: Python 3.8+

```bash
# 1. 装 skill
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
    --repo jarvs1024/skills \
    --path skills/weekly-report

# 2. 装 skill 需要的 Python 依赖
pip3 install --user openpyxl jinja2

# 3. 重启 Codex app / 开新 thread
#    新会话里 "Available skills" 列表就会出现 weekly-report
```

验证:

```bash
ls ~/.codex/skills/weekly-report/
python3 ~/.codex/skills/weekly-report/scripts/smoke_test.py
# 期望: 通过 14 / 失败 0
```

### Windows (Codex)

前置: Python 3.8+, PowerShell 7+ (旧版 cmd.exe 中文会乱码)

```powershell
# 1. 装 skill
python $env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py `
    --repo jarvs1024/skills `
    --path skills/weekly-report

# 2. 装依赖
pip install openpyxl jinja2

# 3. 重启 Codex app / 开新 thread
```

验证:

```powershell
dir $env:USERPROFILE\.codex\skills\weekly-report\
python $env:USERPROFILE\.codex\skills\weekly-report\scripts\smoke_test.py
# 期望: 通过 14 / 失败 0
```

Windows 路径:
- Codex skill 默认位置: `C:\Users\<你的用户>\.codex\skills\`
- 数据目录 (weekly-report): `C:\Users\<你的用户>\Documents\WeeklyNotes\`
- 推荐用 **Windows Terminal** (Microsoft Store 免费装), 旧版 cmd 中文会乱码

---

## 安装 skill (Claude Code)

通过 git clone 或 GitHub 下载 zip 装到 `~/.claude/skills/`, 用 `/$skill-name` 触发。

### macOS / Linux (Claude)

前置: Python 3.8+, Git

```bash
# 1. Clone 仓库到本地 (只读够用)
git clone https://github.com/jarvs1024/skills.git /tmp/jarvs-skills

# 2. 复制 skill 到 Claude 的 skills 目录
cp -r /tmp/jarvs-skills/skills/weekly-report ~/.claude/skills/weekly-report
# Windows / macOS 一样命令

# 3. 装 skill 需要的 Python 依赖
pip3 install --user openpyxl jinja2

# 4. 重启 Claude Code (或开新会话)
#    在新会话里输入: /weekly-report
#    Claude 就会激活这个 skill
```

验证:

```bash
ls ~/.claude/skills/weekly-report/
# 应看到: SKILL.md  agents/  references/  scripts/
```

Claude 触发: 在会话里输入 `/weekly-report` (slash command), Claude 会加载 `SKILL.md` 并按其指令行动。

### Windows (Claude)

前置: Python 3.8+, PowerShell 7+, Git

```powershell
# 1. Clone 仓库
git clone https://github.com/jarvs1024/skills.git $env:TEMP\jarvs-skills

# 2. 复制 skill 到 Claude 的 skills 目录
Copy-Item -Recurse $env:TEMP\jarvs-skills\skills\weekly-report $env:USERPROFILE\.claude\skills\weekly-report

# 3. 装依赖
pip install openpyxl jinja2

# 4. 重启 Claude Code
```

Windows 路径:
- Claude skill 默认位置: `C:\Users\<你的用户>\.claude\skills\`
- 数据目录 (weekly-report): `C:\Users\<你的用户>\Documents\WeeklyNotes\`
- 推荐用 **Windows Terminal** (Microsoft Store 免费装), 旧版 cmd 中文会乱码

---

## 使用 skill

装好后, **新开客户端会话** 就能用。

### weekly-report 使用示例

| 你说 (Codex 自动触发) | 你输入 (Claude 手动) | 行为 |
|---|---|---|
| "记一笔" / "刚才跟 X 开了个会" | `/weekly-report` + "记一笔 ..." | 追加到本周流水账 |
| "写周报" / "出周报" | `/weekly-report` + "写周报" | 反问日期 → 读流水账 → 出 .xlsx |
| "把昨天那条 X 改成 Y" | `/weekly-report` + "改 ..." | 改历史记录 |
| "刚才那条删掉" | `/weekly-report` + "删 ..." | 删本周最后一条 |
| "再写一次" | `/weekly-report` + "再写一次" | 重生成, 旧版备份为 .bak |

详细规则看 [weekly-report/SKILL.md](skills/weekly-report/SKILL.md)。

### 同时装 Codex + Claude

两个客户端用同一份 skill, 互不干扰。数据目录 `~/Documents/WeeklyNotes/` 是**共享的**, 两边写的流水账和周报互相可见。

## 添加新 skill

每个 skill 是 `skills/<skill-name>/` 一个子目录, 自带 `SKILL.md` + `references/` + `scripts/` + `agents/openai.yaml`, 符合 Codex / Claude 通用规范。

新加 skill 的步骤:

1. 在 `skills/` 下建子目录 (例: `skills/my-new-skill/`)
2. 按规范写 `SKILL.md` (YAML frontmatter + markdown body)
3. 可选: `references/`, `scripts/`, `agents/openai.yaml`
4. 跑 `python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/my-new-skill` 验证
5. commit + push 到 main 分支
6. 在本 README 的"可用 skill 列表"加一行

参考 [weekly-report](skills/weekly-report/) 看完整结构。

## 升级 skill

### 方式 1: 重装 (覆盖本地 skill)

**Codex (Mac):**
```bash
rm -rf ~/.codex/skills/weekly-report
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
    --repo jarvs1024/skills --path skills/weekly-report
```

**Codex (Windows PowerShell):**
```powershell
Remove-Item -Recurse -Force $env:USERPROFILE\.codex\skills\weekly-report
python $env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py `
    --repo jarvs1024/skills --path skills/weekly-report
```

**Claude (Mac):**
```bash
rm -rf ~/.claude/skills/weekly-report
git clone https://github.com/jarvs1024/skills.git /tmp/jarvs-skills
cp -r /tmp/jarvs-skills/skills/weekly-report ~/.claude/skills/weekly-report
```

**Claude (Windows PowerShell):**
```powershell
Remove-Item -Recurse -Force $env:USERPROFILE\.claude\skills\weekly-report
git clone https://github.com/jarvs1024/skills.git $env:TEMP\jarvs-skills
Copy-Item -Recurse $env:TEMP\jarvs-skills\skills\weekly-report $env:USERPROFILE\.claude\skills\weekly-report
```

### 方式 2: 改用 git 同步 (适合开发者)

```bash
cd ~/.claude/skills/weekly-report
git init && git remote add origin https://github.com/jarvs1024/skills.git
git pull origin main --rebase
```

之后 `cd` 进去就能 `git pull` 升级。

## 仓库布局

```
.
├── README.md                       # 本文件
└── skills/
    └── weekly-report/              # weekly-report skill (Codex + Claude 通用)
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── references/
        └── scripts/
```

## 依赖

| Skill | Python 包 | 命令 |
|---|---|---|
| weekly-report | `openpyxl`, `jinja2` | `pip3 install --user openpyxl jinja2` |

## 许可

仅个人使用, 不对外授权。
