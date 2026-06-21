---
name: weekly-report
description: >-
  Log work entries to a weekly Markdown journal and produce a styled Excel
  weekly report on demand. Triggers: 记一笔, 写周报, 出周报, 把昨天那条
  改成..., delete/edit requests. Author is an SSD test engineer; polish
  professionally but never fabricate. Default data root is
  ~/Documents/WeeklyNotes/, with two subdirs: notes/ and reports/ (no logs/,
  no HTML output). The user can switch the per-session data root in-chat with
  phrases like 用 [path] 当根目录 or 切回默认, supporting arbitrary paths
  such as an Obsidian vault at
  /Users/jarvs/Documents/obsidian-notes/WeeklyNotes. Primary output: a
  styled .xlsx under the current session root reports/ directory.
---

# Weekly Report

## Overview

Log short work activities into a per-week Markdown journal, then compile the journal into a styled `.xlsx` weekly report on demand. Two product surfaces: a passive logger (every message is checked) and an active generator (triggered by "写周报" / "generate weekly report").

## 开篇示例 (新会话第一屏必读)

> **重要**: 这是**示例数据**, 帮助新会话快速理解 "记录 / 写周报 / 编辑" 三类操作长啥样.
> 详细场景 + 完整对话走查见 [`references/example-week.md`](references/example-week.md).

**三种典型场景一图速览**:

| 场景 | 用户第一句 | LLM 走的流程 |
|---|---|---|
| 记录工作 | "刚跟硬件组对 X" | logging (分类 → 路由日期 → 追加) |
| 写周报 | "写周报" | generate (反问日期 → 归并 3-5 类 → 润色 → 用户确认 → xlsx) |
| 编辑/删除 | "把昨天那条 X 改成 Y" / "刚才那条删掉" | editing (搜原文 → 展示 → 确认 → 改) |

要看完整对话示例 (含时间戳、文件路径、回显格式) → 读 `references/example-week.md`.

## Data layout

### 平台默认根 (无任何覆盖时)

- **macOS / Linux**: `~/Documents/WeeklyNotes/`
- **Windows**: `%USERPROFILE%\Documents\WeeklyNotes\` (即 `C:\Users\<用户>\Documents\WeeklyNotes\`)

### 三种覆盖方式 (优先级从高到低)

1. **会话级覆盖 (推荐)**: 用户在本会话内说 `用 <路径> 当根目录` →
   后续所有 read/write/回显都走该路径。**会覆盖环境变量**。说 `切回默认` 还原。
   详见 `references/commands.md` "Set / change data root" 一节。
2. **环境变量**: `export WEEKLY_NOTES_DIR=/path/to/your/root` (macOS/Linux) 或
   `set WEEKLY_NOTES_DIR=...` (Windows)。脚本 (`scripts/paths.py`) 直接读这个。
   在没有会话级覆盖时, env 兜底。
3. **不推荐**: 改 `scripts/paths.py` 默认值 — 影响所有用户。

**"切回默认" 的语义**: 清除会话级覆盖, 回到 env (若存在) 或平台默认。
换句话说, env 仍然算一种"默认"。例如:

- `WEEKLY_NOTES_DIR=~/A/B unset` + 说过 "用 ~/C/D 当根目录" → "切回默认" → `~/A/B`
- 无 env + 说过 "用 ~/C/D 当根目录" → "切回默认" → 平台默认 `~/Documents/WeeklyNotes`
- 无 env + 从未切过 → "切回默认" 是 no-op

会话级覆盖 = 概念上的 `WEEKLY_NOTES_DIR` 临时设置, **不影响脚本默认值**, 也不持久化;
关闭会话后 env (若在) 自动恢复, 没设 env 就回到平台默认。

### 常见路径示例

- 纯周报: `~/Documents/WeeklyNotes` (默认)
- Obsidian 风格: `~/Documents/obsidian-notes/WeeklyNotes`
  (或 `~/Documents/ObsidianVault/WeeklyNotes`)
- Worktree 多项目: `~/work/project-a/notes/weekly`
- 加密目录: `~/Documents/Encrypted/WeeklyNotes`

布局 (所有 read/write 都相对**当前会话根**):

```
<root>/
├── notes/YYYY-MM-Www.md          # 流水账,每周一个文件,按"## MM/DD 周X"分小节
└── reports/YYYY-MM-Www/
    ├── 周报-YYYY-MM-Www.md
    └── 周报-YYYY-MM-Www.xlsx     # 主输出
```

`scripts/paths.py` 提供 `data_root()` / `notes_dir()` / `reports_dir()` / `ensure_dirs()`,跨平台一致。**会话级覆盖**在 LLM 这一层体现 (LLM 决定读写哪个绝对路径), 脚本本身仍读 `WEEKLY_NOTES_DIR` 环境变量。

Week boundaries: **Friday → next Thursday** (7 calendar days). The Thursday of the target week is the report's "as-of" date.

### Windows 注意事项

- Python 3.8+ (openpyxl 3.x 需要)
- 装依赖: `pip install openpyxl jinja2`
- 终端: 用 Windows Terminal / PowerShell 7+, 旧版 cmd.exe 中文输出会乱码
- 路径: `python scripts\generate_xlsx.py 周报.md 周报.xlsx --date 2026-06-18`
- Excel 字体: `Microsoft YaHei` Windows 自带, 直接可用
- 锁文件: `.~xxx.xlsx` Excel 编辑时会创建, 关闭后自动消失

## 流水账文件格式 (重要,新会话必读)

**记录工作**和**写周报**都围绕同一种文件结构。如果新会话不知道文件长啥样,先看这里。

### 文件位置与命名

- 目录: `<当前会话根>/notes/`
  - 平台默认: macOS / Linux `~/Documents/WeeklyNotes/notes/`; Windows `%USERPROFILE%\Documents\WeeklyNotes\notes\`
  - 用户切过路径时 (例如 Obsidian 风格), 读/写新根下的 `notes/`
- 命名: **`YYYY-MM-Www.md`**,其中 `YYYY-MM-Www` 是 ISO 周编号
  - 例: 2026 年 6 月第 25 周 → `2026-06-W25.md`
  - ISO 周计算: 用 `python3 -c "from datetime import date; d=date(2026,6,19); print(f'{d.isocalendar()}')"` 验证
  - **本周** (按 6/19 周五算) 对应 `2026-06-W25.md`

### 文件结构 (严格遵循,否则写周报步骤会读不到)

```markdown
# 2026 第 25 周 (6/15 ~ 6/21)             ← 文件头, 周的日历范围 (只读, 不修改)

## 6/15 周一                                ← 日期小节, 必填字段
- 10:00 跟硬件组对 FW trim 状态机问题       ← 工作条目, 必填时间戳 + 内容
- 14:30 写 fio 随机写 latency 脚本,支持顺序/随机/混合三种负载

## 6/16 周二
- 09:00 跑 3 块样品 P99 latency 回归,发现 2 个异常值
  - 进度:进行中                          ← 可选: 进度子项
  - 风险:无                              ← 可选: 风险子项
- 15:00 提 issue #412(P99 异常)、#413(回归脚本报错)

## 6/19 周五
- 21:47 测试固件 3.1 版本,新增 10 个问题,1 个问题阻塞(原因:fw init 命令不可用)
- 22:06 BIB_V1.4.3 版本适配 154 转测,新命令改动自动化适配和测试,开始 bics8 兼容性测试
  - 进度:20%
  - 风险:fw 初始化有 bug,柱塞部分测试
```

### 关键约定

1. **文件头** (第一行 `# 2026 第 X 周 (...)`): 标记本周日历范围, **LLM 写日志时不修改, 只读**
2. **日期小节** (`## MM/DD 周X`):
   - MM/DD 格式, 不补零 (用 `6/19` 不是 `06/19`)
   - 周X 必填: 周一/周二/.../周日
   - 同一天可多个小节
3. **工作条目** (`- HH:MM <内容>`):
   - 时间戳必填 (24 小时制)
   - 自由文本描述做了什么、产出了什么
   - 可以含**版本号 / issue 号 / PR 号 / 文档版本**这些 ID
4. **进度 / 风险子项** (缩进 `- 进度:` / `- 风险:`):
   - 可选, 有就写, 没有就跳过
   - 一条 entry 最多一组 (进度+风险)
5. **空白 / 注释行** 用纯文本, 不要用 HTML 或 markdown 表格 (会污染)

### 写周报时, 读哪些文件?

按报告的"本周四"反推窗口:

| 报告的本周四 | 本周窗口 | 要读的流水账文件 |
|---|---|---|
| 2026-06-11 (W24) | 2026-06-05 ~ 2026-06-11 | `2026-06-W23.md` (Fri~Sun 部分) + `2026-06-W24.md` (Mon~Thu) |
| 2026-06-18 (W25) | 2026-06-12 ~ 2026-06-18 | `2026-06-W24.md` (Fri~Sun 部分) + `2026-06-W25.md` (Mon~Thu) |
| 2026-06-25 (W26) | 2026-06-19 ~ 2026-06-25 | `2026-06-W25.md` (Fri~Sun 部分) + `2026-06-W26.md` (Mon~Thu) |

**注意跨年**: 例 W01 + W52 跨年时, 两个流水账文件都读。

**找不到文件怎么办**:

- 目标周文件不存在 → 用空模板初始化 (`# 2026 第 X 周 (...)\n\n(无记录)\n`)
- 上周五的文件不存在 → 跳过 Fri~Sun 段, 只读 Mon~Thu

## Decision tree (apply on every user message)

1. Is the message empty, pure punctuation, or pure emoji? → Reject. Reply: "消息为空,没有要记的内容"
2. Does it trigger a special command? → See `references/commands.md`
3. Otherwise treat as a **work log entry** → See `references/logging.md`

## Quick workflow — log a work entry

1. Parse the message into 1..N entries (split on `。`, `\n`, or "上午/下午" boundaries)
2. Classify each entry per `references/content-classifier.md` (work / non-work / mixed / too long / too short / duplicate)
3. Resolve the target **date** — look for "昨天 / 今天 / 上周五 / YYYY-MM-DD". If explicit date > 7 days from today, ask "要记到 N 月 N 日(超过本周),记到对应周吗?"
4. Compute the ISO week filename: `YYYY-MM-Www.md`
5. Read the file (or initialize if missing); append under `## MM/DD 周X`; atomic write via `.tmp` + `rename`
6. Echo: `📒 已记 N 条 → <当前会话根>/notes/YYYY-MM-Www.md` (例如 Obsidian 模式: `/Users/jarvs/Documents/obsidian-notes/WeeklyNotes/notes/...`)
7. After logging, run the **post-log follow-up** from `references/logging.md`

## Quick workflow — generate weekly report

Triggered by "写周报" / "出周报" / "生成本周周报" / "generate weekly report".

1. **Ask the target week first** (never assume). Default options:
   - 本周 ({本周起始} ~ {本周结束})
   - 上周 ({上周起始} ~ {上周结束}) — for Thursday-evening catch-up
   - 指定日期 (user says YYYY-MM-DD)
2. Read the previous-Friday week's file for Fri/Sat/Sun and the target week's file for Mon..Thu (cross-year: read two files)
3. Group entries by work module; merge multi-day items. **Before writing, read `references/merging.md`** — the skill enforces a merge-into-3-to-5-buckets structure: **one Excel row per module, multiple sub-items inside that row numbered `1) 2) 3)` (only when ≥2 sub-items) and separated by `<br>`; the content / progress / risk columns must contain no in-cell dates**. Bucket names are LLM-chosen based on what the user actually worked on that week. Do not reuse a fixed taxonomy across weeks if the work has shifted.
4. **Polish content per `references/polish-rules.md`**: rewrite raw 流水账 entries into professional SSD-test-engineer language. Use the domain glossary; light / medium / heavy polish by entry density. **Never invent facts** — keep issue / PR / version numbers verbatim; do not flip "进行中" to "已完成".
5. **Build next-week plan per `references/next-week-plan.md`**: infer from current-week progress and deadlines, then **show the draft to the user and wait for confirmation** before writing to MD. Default is to show 3~7 items with P0/P1/P2 priorities. Do not write the plan to disk without the user responding.
6. Write intermediate `周报-YYYY-MM-Www.md` to `reports/.../`
7. Run `scripts/generate_xlsx.py --date {thursday}` → `.xlsx` (primary deliverable)
8. Print: report directory path + first 3 lines of the Excel preview

## Quick workflow — edit or delete

See `references/editing.md`. Always show the original entry and require confirmation before mutating.

## Output style (.xlsx)

5-column "本周总结" + 3-column "下周计划". Light-blue theme per `references/style-spec.md`. Risk column stays empty when none; never write "无".

## Dependencies

Required Python packages (check at session start):

```bash
python3 -c "import openpyxl, jinja2" || pip3 install --user openpyxl jinja2
```

If `openpyxl` is missing, abort the xlsx step and tell the user the install command. Do not proceed with a half-built report.

## Failure handling

- **Existing report at same path** → **必须主动问用户**: "检测到已有周报 (路径 X), 要 (1) 覆盖 (2) 备份为 .bak 后覆盖 (3) 取消?" . Never silently overwrite. 不要替用户决定。
- **Excel 锁文件** (`.~xxx.xlsx`) → 提示 "另一个 Excel 在编辑这个文件, 关掉后重试", 不写入。脚本本身不主动处理锁文件 (要 Codex 检查)
- **重生成 ("再写一次")** → 旧版自动备份为 `.bak` (脚本可加, 或 Codex 自己 mv)
- **Excel lock file** (`.~xxx.xlsx`) → warn and wait; do not write.
- **Empty week** (no entries) → ask: "本周没记任何东西,确认要出空周报吗?" If confirmed, produce a stub with header + empty plan section.
- **Cross-year week** (e.g. W52 → W01) → read both source files; show full year in title.
- **Disk full / permission denied** → echo original input back so the user does not lose it.

## What this skill does NOT do

- No external integrations (no Feishu / Jira / Git auto-fetch)
- No scheduling, reminders, or wakeups
- Does not email anything (only generates copy/attach-ready files)
- Does not touch anything outside the **current session root** (default `~/Documents/WeeklyNotes/`, or whatever path the user set with `用 <路径> 当根目录`)

## 用户角色与润色边界

**作者身份**: SSD 测试工程师 (固件 / 老化 / 性能 / 兼容性方向)
**读者**: 项目经理 + 上下游协作同事 (开发 / 硬件 / 产品 / QA lead)

LLM 在生成周报时**默认从 SSD 测试工程师的专业视角出发**, 但**严守禁止虚构**的红线 (issue 号 / 版本号 / 进度状态 / 协作对象 不可改写或添加)。

完整词表 / 3 档润色强度 / 红线 / 自我检查 → `references/polish-rules.md` (107 行)

## Reference index (按使用时机排序)

| 触发时机 | 必读 | 用途 |
|---|---|---|
| **新会话第一件事** | `SKILL.md` 顶部 "## 流水账文件格式" 一节 | 知道 notes 文件长啥样, 命名规则, 写周报时读哪些 |
| 每次记录 | `references/logging.md` | 解析 / 分类 / 路由日期 / 追加 / 回显 |
| "写周报" 触发 | `references/commands.md` | 哪些短语算周报触发 |
| 写本周总结前 | `references/merging.md` | **mandatory** 3-5 大类归并规则 |
| 写完 MD 前 | `references/polish-rules.md` | SSD 测试工程师润色 + **禁止虚构** 红线 |
| 写下周计划前 | `references/next-week-plan.md` | 推断 + **强制用户确认** |
| 改 / 删历史 entry | `references/editing.md` | 搜原文 / 确认 / 改 |
| 记录前分类 | `references/content-classifier.md` | A~H 8 类内容判断 |
| 调 Excel 样式 | `references/style-spec.md` | 颜色 / 字体 / 合并 / 列宽 |
| 调脚本 / 跨平台 | `references/scripts.md` | CLI / 入参 / 输出 / 平台差异 |
