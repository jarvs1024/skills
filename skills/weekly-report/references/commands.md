# Command triggers

The skill distinguishes between **passive logging** (the default) and **explicit commands**. Match the user's first words.

## Logging (default)

Anything that is not an empty message and not one of the commands below. Examples:
- "今天和 X 开了个会"
- "刚改完 issue #123 的 PR"
- "下午写了一下午文档"

## Generate weekly report

| Phrasing (zh) | Phrasing (en) |
|---|---|
| 写周报 | generate weekly report |
| 出周报 | write the weekly report |
| 生成本周周报 | produce this week's report |
| 出本周周报 | build the report |

Before doing anything, **ask which week** with three options (this week / last week / specific date).

## Edit / delete

| Phrasing | Action |
|---|---|
| 刚才那条删掉 / 撤销刚才那条 | Delete the most recent entry in this week's file; show first, confirm |
| 把昨天那条 X 改成 Y | Find the most recent entry containing X within the named date, show, confirm |
| 改成 ... | Ambiguous — ask "改哪条?改成什么内容?" |
| 删掉 N 周前的 | Backdate delete; ask for target date first |
| 再写一次 | Regenerate report; back up old to `.bak` |
| 撤销修改 | Undo the most recent edit (same session only) |
| 批量删除 / 批量修改 | Show preview list, require explicit confirmation |

For all edits: **show the original text and the proposed change, then wait for user approval**. Never mutate silently.

## Back-dated logging

Phrases like "昨天跑了样品", "上周五提了个 issue", "6/17 修了 bug" → parse the date, route to the right week file. If the date is more than 7 days from today, confirm: "这条要记到 N 月 N 日(超过本周),记到对应周吗?"

## Repeat suppression

If the user says "写周报" twice within 5 seconds, reply: "刚才已经生成了,还要再生成一次吗?" and do nothing until they confirm.
