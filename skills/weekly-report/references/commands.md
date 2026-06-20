# Command triggers

只关注**短语匹配**: 用户第一句话说啥, 走哪个流程。**流程细节不写在这里**, 全部指向 references/ 对应文件。

## 决策顺序 (apply on first words of user message)

1. **空消息 / 纯标点** → 拒绝 ("消息为空, 没有要记的内容")
2. **匹配 "写周报" 类命令** → 走 generate 流程 (见 SKILL.md "Quick workflow — generate weekly report")
3. **匹配 "删 / 改" 类命令** → 走 editing 流程 (见 `references/editing.md`)
4. **匹配 "重复" 关键字** (5 秒内重复 "写周报") → 提示并等待确认
5. **默认** → 走 logging 流程 (见 `references/logging.md`)

## 触发短语表

### Generate weekly report

| 中文 | 英文 |
|---|---|
| 写周报 | generate weekly report |
| 出周报 | write the weekly report |
| 生成本周周报 | produce this week's report |
| 出本周周报 | build the report |
| 帮我出周报 | help me write the report |

### Edit / delete

| 短语 | 动作 (具体流程见 editing.md) |
|---|---|
| 刚才那条删掉 / 撤销刚才那条 | 删本周最后一条 |
| 把昨天那条 X 改成 Y | 按日期 + 关键词定位, 改值 |
| 把那条改完 | 用户回答修改内容后, 只改值不改时间戳 |
| 改成 ... (无主语) | 反问 "改哪条? 改成什么?" |
| 删掉 N 周前的 | 反问日期, 接受任意历史周 |
| 批量删除 / 批量修改 | 预览列表, 等确认 |
| 撤销修改 | 仅本次会话内可撤销, 跨会话手动从 .bak 恢复 |
| 再写一次 | 重生成, 旧版备份为 .bak |

### Repeat suppression

| 触发 | 行为 |
|---|---|
| "写周报" 5 秒内重复 | 提示 "刚才已经生成了, 还要再生成一次吗?" |

## 不在 commands.md 的 (避免重复)

- **Logging 流程** (解析 / 分类 / 路由日期 / 追加) → `references/logging.md`
- **Edit 流程** (搜原文 / 确认 / 改 / 撤销) → `references/editing.md`
- **Generate 流程** (反问日期 / 归并 / 润色 / 写盘) → SKILL.md "Quick workflow" + `references/merging.md` + `references/next-week-plan.md` + `references/polish-rules.md`
- **内容分类** (A~H 8 类) → `references/content-classifier.md`
