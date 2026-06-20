# Content classifier

Apply these rules in order. Stop at the first match.

## A. 明确非工作 — 反问,不归档

Reject-list keywords (any match): 家人 / 看病 / 体检 / 摸鱼 / 摆烂 / 划水 / 躺平 / 偷懒 / 看剧 / 刷剧 / 刷视频 / 玩游戏 / 约会 / 聚餐 / 喝酒 / 休息 / 睡懒觉 / 请假 / 旅游 / 逛街

Reply: "这条没记(疑似非工作内容),要记吗?"

## B. 模糊词 — 反问,不归档

Keywords: 放空 / 发呆 / 懈怠 / 走神 / 闲聊 / 瞎逛

Reply: "这是工作记录还是私事?"

## C. 私事+工作混合 — 拆分,只记工作部分

Example: "今天跟老婆吃饭,顺便想了一下 FW 优化" → archive "顺便想了一下 FW 优化"; discard the rest.

Reply: "私事部分不记,工作部分已记:N 条,确认?"

## D. 空消息 / 纯标点 — 拒绝

Examples: "。" / "" / "  " / "😀"

Reply: "消息为空,没有要记的内容"

## E. 重复输入 — 智能去重

Compare the new entry against existing entries in the same date section. If identical, skip. If similar, reply: "已有类似记录:'...',还要记吗?"

## F. 补记历史 — 日期识别

Phrases: "昨天跑了样品" / "上周五提了个 issue" / "6/17 修了 bug".

Resolve the date (see `logging.md`), route to the right week file. If the resolved date is more than 7 days from today: "这条要记到 N 月 N 日(超过本周),记到对应周吗?"

## G. 超长 (>500 字) — 确认

Echo the full content, then: "这条有点长(>500 字),确认是工作记录吗?" Wait for confirmation before archiving.

## H. 超短 (< 5 字) — 归档但提示

Examples: "开会" / "修 bug"

Archive it, but after the echo: "这条很短,要不要补充点细节?"
