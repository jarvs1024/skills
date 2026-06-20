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
4. Write intermediate `周报-YYYY-MM-Www.md` to `reports/.../`
5. Run `scripts/render_html.py` → `.html`
6. Run `scripts/generate_xlsx.py --date {thursday}` → `.xlsx` (primary deliverable)
7. Append a line to `logs/YYYY-MM-DD.log`
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

## Reference index

- `references/commands.md` — exact phrasing that triggers each command mode
- `references/logging.md` — entry parsing, classifier, post-log follow-up
- `references/content-classifier.md` — A..H content-type rules (non-work / fuzzy / mixed / empty / duplicate / back-dated / too long / too short)
- `references/editing.md` — delete / modify / undo / batch
- `references/style-spec.md` — Excel cell colors, fonts, merges, column widths
- `references/scripts.md` — what each script does and its CLI surface
- `references/merging.md` — **mandatory** 3-bucket module taxonomy for the summary table
