# Logging workflow

## Current session root (读这节再写)

所有 read/write/回显的根 = **当前会话根**。判定顺序:

1. 用户本会话内说过 `用 <路径> 当根目录` → 用该路径 (覆盖 env)
2. 否则看 env: `WEEKLY_NOTES_DIR` 设了 → 用 env (脚本会 `expanduser` + `resolve`)
3. 否则 = 平台默认 (`~/Documents/WeeklyNotes/` 或 `%USERPROFILE%\Documents\WeeklyNotes\`)

`切回默认` 会清除第 1 项, 不清除 env; 然后按 2 → 3 顺序回退。

`notes/`, `reports/` 两个子目录都在会话根下。回显路径用 **绝对路径**,
别再用 `~/...`, 避免切过路径后用户认不出来。

如果用户切了路径后**接着发工作记录**, 静默使用新根; **不需要再问一次**。
切路径触发见 `references/commands.md` "Set / change data root"。

## Parse the message

Split the user message into entries using these delimiters (in order):
1. `。` (Chinese period) or `. ` (English period + space)
2. `\n` (explicit line break)
3. `上午` / `下午` (time-of-day markers, for diary-style entries)

Cap at 1..N entries; ignore empty fragments.

## Classify each entry

Apply the rules in `content-classifier.md`. For each entry, decide one of:
- **A. 明确非工作** — do not archive; ask the user
- **B. 模糊词** — ask the user; do not archive
- **C. 私事+工作混合** — split, archive only the work part, confirm with user
- **D. 空消息/纯标点** — reject
- **E. 重复输入** — compare against existing entries in the same date; skip or prompt
- **F. 补记历史** — route to the right date; warn if outside this week
- **G. 超长 (>500 字)** — confirm before archiving
- **H. 超短 (< 5 字)** — archive but prompt for more detail

## Resolve the target date

- No date word → today
- "今天" / "刚" / "刚才" → today
- "昨天" → today − 1
- "前天" → today − 2
- "上周X" / "上X" → resolve from named weekday
- "MM-DD" or "M月D日" → that date in the current year
- "YYYY-MM-DD" → exact date
- Ambiguous → ask

If the resolved date is more than 7 days from today, confirm before writing to a different week's file.

## Append to file

Path: `<当前会话根>/notes/YYYY-MM-Www.md` (绝对路径, 例: Obsidian 模式 `/Users/jarvs/Documents/obsidian-notes/WeeklyNotes/notes/2026-06-W25.md`)

Format inside the file:

```markdown
## 6/19 周五
- 22:06 BIB_V1.4.3 适配 154 转测,新命令自动化适配和测试
  - 进度:BIB 100%,自动化 80%
  - 风险:无
```

Atomic write: write to `YYYY-MM-Www.md.tmp` first, then `os.rename` to final. Never edit in place.

## Echo to user

```
📒 已记 N 条 → <当前会话根>/notes/YYYY-MM-Www.md
```

(实际回显用绝对路径, 例如 `📒 已记 2 条 → /Users/jarvs/Documents/obsidian-notes/WeeklyNotes/notes/2026-06-W25.md`)

If classifier flagged anything, list the flagged items separately and ask.

## Post-log follow-up (重要)

After every successful archive, **if the user did not mention 进度 and 风险 in the original message**, ask once:

> "刚才记的那 N 条要不要补一下进度和风险?(示例:已完成 / 进行中 / 阻塞 — 风险示例:无 / 有 1 个:XXX / 等 XX 回复。回 `无` 跳过全部)"

**Rules for the follow-up:**
- Ask **per work item**, not a generic "how's progress?" — the user should be able to copy-paste answers.
- Provide example answers to lower the cost of responding.
- Separate progress and risk into two questions.
- "回 `无`" is the explicit skip signal; honor it.
- Once the user says "别问了" / "先这样,不用问" in the current session, stop asking.
- **必问 (must ask)** when the entry contains deadline words: 明天 / 周五 / 本周 / 马上 / 周五前.
- **选问 (may ask)** for ordinary entries.
- The follow-up is **async** — the entry is already saved; the follow-up just collects metadata.

## Store the follow-up answer

Append the answer to the entry as sub-bullets:

```markdown
- 22:06 BIB_V1.4.3 适配 154 转测
  - 进度:已完成
  - 风险:无
```

When generating a report, the "完成进度" column takes the longest-stated progress; the "风险点" column takes the risk note. If the user skipped, leave the cell empty (not "未指定").
