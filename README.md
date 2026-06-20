# jarvs1024/skills

个人 Codex skill 集合。每个 skill 是一个**可独立安装**的模块, 通过 `skill-installer` 一行命令从本仓库装到本地 `~/.codex/skills/`。

## 目录

- [可用 skill 列表](#可用-skill-列表)
- [安装 skill](#安装-skill)
  - [macOS / Linux](#macos--linux)
  - [Windows](#windows)
- [使用 skill](#使用-skill)
- [添加新 skill](#添加新-skill)
- [升级 skill](#升级-skill)
- [仓库布局](#仓库布局)

## 可用 skill 列表

| Skill | 简介 | 主要场景 |
|---|---|---|
| [**weekly-report**](skills/weekly-report/) | 周报生成 + 工作流水账, 输出公司风 .xlsx | 每天随手记工作 / 周四一键出周报 / 修改历史记录 |

> 后续会持续添加新 skill, 上表会同步更新。

## 安装 skill

通过 Codex 自带的 `skill-installer` 安装, 默认装到 `~/.codex/skills/`。

### macOS / Linux

前置: Python 3.8+

```bash
# 1. 装 skill (一行)
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
    --repo jarvs1024/skills \
    --path skills/weekly-report

# 2. 装 skill 需要的 Python 依赖 (按 skill 要求)
pip3 install --user openpyxl jinja2

# 3. 重启 Codex app / 开新 thread
#    新会话里 "Available skills" 列表就会出现 weekly-report
```

验证安装:

```bash
ls ~/.codex/skills/weekly-report/        # 应看到 SKILL.md / references/ / scripts/ / agents/
python3 ~/.codex/skills/weekly-report/scripts/smoke_test.py
# 期望: 通过 14 / 失败 0
```

### Windows

前置: Python 3.8+, PowerShell 7+ (旧版 cmd.exe 中文会乱码)

```powershell
# 1. 装 skill
python $env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py `
    --repo jarvs1024/skills `
    --path skills/weekly-report

# 2. 装 skill 需要的 Python 依赖
pip install openpyxl jinja2

# 3. 重启 Codex app / 开新 thread
```

验证安装:

```powershell
dir $env:USERPROFILE\.codex\skills\weekly-report\
python $env:USERPROFILE\.codex\skills\weekly-report\scripts\smoke_test.py
# 期望: 通过 14 / 失败 0
```

#### Windows 路径说明

- Codex skill 默认位置: `C:\Users\<你的用户>\.codex\skills\`
- 数据目录 (weekly-report): `C:\Users\<你的用户>\Documents\WeeklyNotes\`
- PowerShell 7+ 自带, Windows 10+ 自带 `python` 命令 (在 Microsoft Store 装 Python 3.8+)
- 旧版 Windows Terminal 中文乱码, 推荐用 **Windows Terminal** (Microsoft Store 免费装)

## 使用 skill

装好后, **新开 Codex 会话** 就能用。触发条件写在每个 skill 的 `description` 字段里, LLM 看到匹配就激活。

### weekly-report 使用示例

| 你说 | Codex 行为 |
|---|---|
| "记一笔" / "刚才跟 X 开了个会" | 追加到本周流水账 |
| "写周报" / "出周报" | 反问日期 → 读流水账 → 出 .xlsx |
| "把昨天那条 X 改成 Y" | 改历史记录 |
| "刚才那条删掉" | 删本周最后一条 |
| "再写一次" | 重生成, 旧版备份为 .bak |

详细规则看 [weekly-report/SKILL.md](skills/weekly-report/SKILL.md)。

## 添加新 skill

每个 skill 是 `skills/<skill-name>/` 一个子目录, 自带 `SKILL.md` + `references/` + `scripts/` + `agents/openai.yaml`, 符合 Codex 规范。

新加 skill 的步骤:

1. 在 `skills/` 下建子目录 (例: `skills/my-new-skill/`)
2. 按 Codex 规范写 `SKILL.md` (YAML frontmatter + markdown body)
3. 可选: `references/`, `scripts/`, `agents/openai.yaml`
4. 跑 `python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/my-new-skill` 验证
5. commit + push 到 main 分支
6. 在本 README 的"可用 skill 列表"加一行

参考 [weekly-report](skills/weekly-report/) 看完整结构。

## 升级 skill

升级有 2 种方式:

### 方式 1: 重装 (覆盖本地 skill)

```bash
# macOS / Linux
rm -rf ~/.codex/skills/weekly-report
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
    --repo jarvs1024/skills --path skills/weekly-report

# Windows
Remove-Item -Recurse -Force $env:USERPROFILE\.codex\skills\weekly-report
python $env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py `
    --repo jarvs1024/skills --path skills/weekly-report
```

### 方式 2: 用 git pull 同步 (适合开发者)

```bash
# macOS / Linux
cd ~/.codex/skills/weekly-report
git init && git remote add origin https://github.com/jarvs1024/skills.git
git pull origin main --rebase
```

> 注意: 方式 2 会把本地 skill 变成 git repo, 之后 `cd` 进去就能 `git pull` 升级, 但 uninstall 时要 `rm -rf` 加 `rm -rf .git`。

## 仓库布局

```
.
├── README.md                       # 本文件
└── skills/
    └── weekly-report/              # weekly-report skill
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── references/
        └── scripts/
```

## 依赖

不同 skill 有不同依赖, 装时看 skill 自己的 `SKILL.md` 或 `references/scripts.md`。当前:

| Skill | 依赖 |
|---|---|
| weekly-report | `openpyxl`, `jinja2` |

## 许可

仅个人使用, 不对外授权。
