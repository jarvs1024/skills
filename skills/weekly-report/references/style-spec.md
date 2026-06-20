# Excel style spec

Company-style report, light-blue theme.

## Sheets

- **Sheet 1: 本周工作总结** (the report)
- **Sheet 2: 下周计划** (the plan)

## Sheet 1 layout

| Element | Range | Format |
|---|---|---|
| 元信息行 | A1:E1 | `#F2F2F2` 浅灰底,左对齐,11pt,文本 "生成于 YYYY-MM-DD HH:MM · 本周工作日 N 天" |
| 标题行 | A2:E2 | `#8FAADC` 浅蓝底,黑色加粗 14pt,居中,文本 "本周工作总结 (YYYY-MM-DD ~ YYYY-MM-DD)" |
| 表头行 | A3:E3 | `#D9E2F3` 更浅蓝底,黑色加粗 11pt,居中,列名: 序号 / 工作模块 / 工作内容与成果 / 完成进度 / 风险点 |
| 数据行 | A4:E{n} | 白底,黑色 11pt,左对齐 + indent 1,长内容自动换行 |
| 边框 | A1:E{n} | `#D0D0D0` 细实线 |

Column widths: auto-compute from max content length per column (cap at 60 chars).

## Sheet 2 layout

| Element | Range | Format |
|---|---|---|
| 标题行 | A1:E1 | `#8FAADC` 浅蓝底,黑色加粗 14pt,居中,"下周工作计划 (YYYY-MM-DD ~ YYYY-MM-DD)" |
| 表头行 | A2:C2 | `#D9E2F3` 更浅蓝底,黑色加粗 11pt,居中,列名: 序号 / 优先级 (P0/P1/P2) / 工作计划 |
| 数据行 | A3:C{n} | 白底,黑色 11pt,左对齐 + indent 1,长内容自动换行 |

The C..E columns under "工作计划" should be merged horizontally for each row.

## Date range convention

- 本周 = 上周五 ~ 本周四 (7 calendar days, spans a weekend)
- 下周 = 本周五 ~ 下周四
- 风险点: 如果没有就**留空**,不写"无"
- 优先级: 只用 P0 / P1 / P2,不用 P3
