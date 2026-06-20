---
name: weekly-report
description: Record daily work notes and generate a styled Excel weekly report on demand. Use when the user says things like "记一笔", "刚才...记一下", "写周报", "出周报", "生成本周周报", "把昨天那条改成...", or asks to delete/edit a recent entry. Maintains running notes in ~/Documents/WeeklyNotes/notes/ (one Markdown file per ISO week) and produces ~/Documents/WeeklyNotes/reports/YYYY-MM-Www/周报-YYYY-MM-Www.xlsx as the primary output. Triggers on Chinese or English; does not trigger for non-work chatter.
---

# Weekly Report

## Overview

Log short work activities into a per-week Markdown journal, then compile the journal into a styled `.xlsx` weekly report on demand. Two product surfaces: a passive logger (every message is checked) and an active generator (triggered by "写周报" / "generate weekly report").

## Data layout

数据根目录(自动按平台选择,可被 `WEEKLY_NOTES_DIR` 环境变量覆盖):

- **macOS / Linux**: `~/Documents/WeeklyNotes/`
- **Windows**: `%USERPROFILE%\Documents\WeeklyNotes\` (即 `C:\Users\<用户>\Documents\WeeklyNotes\`)
- 覆盖: `export WEEKLY_NOTES_DIR=/path/to/your/root` (macOS/Linux) 或 `set WEEKLY_NOTES_DIR=...` (Windows)

布局:

```
<root>/
├── notes/YYYY-MM-Www.md          # 流水账,每周一个文件,按"## MM/DD 周X"分小节
├── reports/YYYY-MM-Www/
│   ├── 周报-YYYY-MM-Www.md
│   ├── 周报-YYYY-MM-Www.html
│   └── 周报-YYYY-MM-Www.xlsx     # 主输出
└── logs/YYYY-MM-DD.log
```

`scripts/paths.py` 提供 `data_root()` / `notes_dir()` / `reports_dir()` / `logs_dir()` / `ensure_dirs()`,跨平台一致。

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

- 目录: `~/Documents/WeeklyNotes/notes/`
  - macOS / Linux: `~/Documents/WeeklyNotes/notes/`
  - Windows: `%USERPROFILE%\Documents\WeeklyNotes\notes\`
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
6. Echo: `📒 已记 N 条 → ~/Documents/WeeklyNotes/notes/YYYY-MM-Www.md`
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
7. Run `scripts/render_html.py` → `.html`
8. Run `scripts/generate_xlsx.py --date {thursday}` → `.xlsx` (primary deliverable)
9. Append a line to `logs/YYYY-MM-DD.log`
10. Print: report directory path + first 3 lines of the Excel preview

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

- **Existing report at same path** → offer: overwrite / backup to `.bak`. Never silently overwrite.
- **Excel lock file** (`.~xxx.xlsx`) → warn and wait; do not write.
- **Empty week** (no entries) → ask: "本周没记任何东西,确认要出空周报吗?" If confirmed, produce a stub with header + empty plan section.
- **Cross-year week** (e.g. W52 → W01) → read both source files; show full year in title.
- **Disk full / permission denied** → echo original input back so the user does not lose it.

## What this skill does NOT do

- No external integrations (no Feishu / Jira / Git auto-fetch)
- No scheduling, reminders, or wakeups
- Does not email anything (only generates copy/attach-ready files)
- Does not touch anything outside `~/Documents/WeeklyNotes/`

## 用户角色与润色边界

**作者身份**: SSD 测试工程师 (固件 / 老化 / 性能 / 兼容性方向)
**读者**: 项目经理 + 上下游协作同事 (开发 / 硬件 / 产品 / QA lead)

LLM 在生成周报时**默认从 SSD 测试工程师的专业视角出发**, 可以:

- 引用 `references/polish-rules.md` 的领域词表做术语润色
- 重写口语化 entry 为正式工程描述
- 补充技术上下文 (如"跑通" → "完成回归验证")

**红线 (写入 MD 前必查)**:

- ❌ 不编造 entry 中没有的测试数据
- ❌ 不虚构 issue / PR / 版本号 (用户写啥就啥)
- ❌ 不改写进度状态 (进行中 / 已完成 / 阻塞 不可互换)
- ❌ 不添加 entry 中没有的协作对象
- ❌ 不把"风险"自动清空或改成"无"

详见 `references/polish-rules.md` 末尾的"自我检查"清单。

## 关联点 (避免描述错位)

| 主题 | 入口 reference | 必读位置 |
|---|---|---|
| 流水账文件长啥样 | `SKILL.md` 流水账文件格式 一节 | 新会话第一件事 |
| 记录工作 | `references/logging.md` | 每次记录都走 |
| 写周报归并 | `references/merging.md` | 写本周总结前必读 |
| 下周计划 | `references/next-week-plan.md` | 写下周计划前必读, 含**用户确认**流程 |
| 润色 | `references/polish-rules.md` | 写完 MD 前自检 |
| 内容判定 | `references/content-classifier.md` | 记录前分类 (A~H) |
| 编辑 / 删除 | `references/editing.md` | 修改历史 entry |
| 触发命令 | `references/commands.md` | "写周报" 等命令识别 |
| Excel 样式 | `references/style-spec.md` | 渲染样式参考 |
| 脚本说明 | `references/scripts.md` | 跨平台 / 调参时查 |

## Reference index

- `references/commands.md` — exact phrasing that triggers each command mode
- `references/logging.md` — entry parsing, classifier, post-log follow-up
- `references/content-classifier.md` — A..H content-type rules (non-work / fuzzy / mixed / empty / duplicate / back-dated / too long / too short)
- `references/editing.md` — delete / modify / undo / batch
- `references/style-spec.md` — Excel cell colors, fonts, merges, column widths
- `references/scripts.md` — what each script does and its CLI surface
- `references/merging.md` — **mandatory** 3-bucket module taxonomy for the summary table
- `references/next-week-plan.md` — how to infer next-week plan and the **mandatory** user confirmation step
- `references/polish-rules.md` — SSD-test-engineer professional polish + **forbidden-fabrication** red lines
