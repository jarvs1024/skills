# Command triggers

只关注**短语匹配**: 用户第一句话说啥, 走哪个流程。**流程细节不写在这里**, 全部指向 references/ 对应文件。

## 决策顺序 (apply on first words of user message)

> **会话开场检查在前** (见本文件 "On session start" 小节). 当且仅当本会话**还没确认过**数据根时才走; 已确认过则跳过, 直接进入下面的 7 步.

1. **空消息 / 纯标点** → 拒绝 ("消息为空, 没有要记的内容")
2. **匹配 "写周报" 类命令** → 走 generate 流程 (见 SKILL.md "Quick workflow — generate weekly report")
3. **匹配 "删 / 改" 类命令** → 走 editing 流程 (见 `references/editing.md`)
4. **匹配 "换路径 / 切路径 / 用回默认" 类命令** → 走 data-root 切换流程 (见本文件 "Set / change data root" 小节)
5. **匹配 "重复" 关键字** (5 秒内重复 "写周报") → 提示并等待确认
6. **默认** → 走 logging 流程 (见 `references/logging.md`)

## On session start (新会话第一件事)

> **触发时机**: 每个新会话的**第一句话**进来时, 在上面的 6 步决策**之前**做这个检查. 一旦本会话确认过数据根, 后面所有消息都跳过此节, 直接走决策表.

**判定** (按 `WEEKLY_NOTES_DIR` 环境变量):

| env 状态 | 行动 |
|---|---|
| `WEEKLY_NOTES_DIR` 已设 | 用 env 路径 (脚本会自动 `expanduser` + `resolve` 绝对化). 主动回显一次, 让用户知道根在哪. 之后不再问. |
| `WEEKLY_NOTES_DIR` 未设 | 提示用户配置 (三平台各一行), **同时**告知"会暂时用平台默认 `~/Documents/WeeklyNotes`"; 询问用户是否继续 / 给新路径. |
| 本会话**已切过路径** (`用 X 当根目录`) | 跳过检查, 走会话级覆盖的根. |

### env 已设 → 主动回显模板

```
📂 当前数据根 (来源: 环境变量 WEEKLY_NOTES_DIR)
  /Users/jarvs/Documents/obsidian-notes/WeeklyNotes
  notes:   /Users/jarvs/Documents/obsidian-notes/WeeklyNotes/notes
  reports: /Users/jarvs/Documents/obsidian-notes/WeeklyNotes/reports
本会话所有读/写都走这里。要换路径说: 用 [path] 当根目录
```

**只回显一次**, 之后用户的任何消息都不要再重复这个块.

### env 未设 → 提示 + 默认模板

```
⚠️  未检测到环境变量 WEEKLY_NOTES_DIR, 决定本会话数据根的优先级是:
  1. 会话级覆盖 (你说 "用 <path> 当根目录" 即可)
  2. WEEKLY_NOTES_DIR 环境变量 (推荐, 一次设置长期生效)
  3. 平台默认 ~/Documents/WeeklyNotes

(1) 临时设置 (仅当前 shell):
    macOS / Linux:   export WEEKLY_NOTES_DIR=/path/to/your/root
    Windows PS:      $env:WEEKLY_NOTES_DIR = "C:\path\to\your\root"

(2) 永久设置:
    macOS / Linux:   echo 'export WEEKLY_NOTES_DIR=~/Documents/obsidian-notes/WeeklyNotes' >> ~/.zshrc && source ~/.zshrc
    Windows:         [System.Environment]::SetEnvironmentVariable("WEEKLY_NOTES_DIR", "C:\path", "User")

(3) 现在就想用 obsidian / 别的路径: 说 "用 <path> 当根目录"
(4) 先用平台默认: 说 "默认" / "好" / 直接发工作内容 (我先按默认走)

? 用哪个? (回数字, 或直接给路径/动作)
```

**用户回应分支**:

| 用户回 | 行为 |
|---|---|
| 数字 `1` / `2` / 3 / 4`, 或 `默认` / `好` / `先用默认` | 用平台默认 `~/Documents/WeeklyNotes`, 记入"已确认"状态, 回显一行 |
| `用 <path> 当根目录` | 走"Set / change data root"小节切路径, 记入"已确认" |
| 直接发工作内容 | 视为"先用默认", logging 流程处理, **echo 末尾**追加一句"本周用了默认根, 要换路径说 `用 [path] 当根目录`" |
| 路径 (无"用 X 当根目录"前缀) | 反问 "是要切到 <path> 当根目录吗? (回 OK 切换)" |
| 长时间不答 / 跳过 | 等用户下一句再决定, 不要替用户选 |

### env 设置示例: Obsidian vault

如果用户的目标是 Obsidian vault 路径 (例 `~/Documents/obsidian-notes/WeeklyNotes`), 在 env 未设提示里**默认就把这条命令写出来**, 用户复制粘贴即可:

```bash
# macOS / Linux (永久, zsh)
echo 'export WEEKLY_NOTES_DIR=~/Documents/obsidian-notes/WeeklyNotes' >> ~/.zshrc
source ~/.zshrc
# 重启 Codex / Claude 后 env 生效
```

**注意事项**:

- 这段检查**只在每个新会话第一次**做, 已确认过则本会话**永远跳过** (即使后续 env 被改了, 也不重新探测)
- 检查本身**不修改**任何状态 (不创建目录, 不写文件), 只是探测 + 回显
- 用户**第一句直接是工作内容**时, **不要先问根**, 直接 logging; 在 echo 末尾带一句"本周用了默认根"提示即可 (上面表格第 3 行)

## 触发短语表

### Session-start confirmation (仅新会话第一句)

| 短语 | 行为 |
|---|---|
| `默认` / `好` / `先用默认` / `继续` | 接受平台默认, 记入"已确认", 回显一行当前根 |
| `1` / `2` / `3` / `4` | 等同上面的对应选项 |
| `用 <path> 当根目录` | 走 "Set / change data root" 切换 |
| 任意路径 (无 "用 X" 前缀) | 反问 "是要切到 <path> 当根目录吗?" |
| 任何工作内容 | 视为"先用默认", 直接走 logging, echo 末尾追加"本周用了默认根"提示 |

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

### Set / change data root (会话级路径切换)

让本会话的所有 read/write/回显都走指定根目录。**不影响脚本默认值**, 只在本会话内覆盖 `WEEKLY_NOTES_DIR` 的等效行为。

| 短语 | 行为 |
|---|---|
| 用 <路径> 当根目录 | 解析路径 (支持 `~`, 相对/绝对, 末尾可带不带 `/`), 校验存在或可创建, 设为**当前会话根**。回显新根 + 创建/复用的子目录 (notes / reports) |
| 用 <路径> 作为路径 | 同上 (中文别称) |
| 切到 <路径> | 同上 |
| 把根目录切到 <路径> | 同上 |
| 切回默认路径 / 用回默认 | **清除会话级覆盖**, 回到 env (若存在) 或平台默认。<br>回显时明确说"当前生效的默认根是 X, 它是 env 提供的 / 平台默认" |
| 当前根目录在哪? | 回显当前会话根 + 三子目录绝对路径 + 来源 (会话覆盖 / env / 平台默认) |
| 当前根目录在哪? | 回显当前会话根 + 三子目录绝对路径 |

**解析规则**:
- `~` / `~user` → 展开
- 相对路径 → 相对当前 cwd
- 末尾的 `/` 忽略
- 不存在 → 先确认 "X 不存在, 自动创建?" 再 `mkdir -p`
- 解析后**必须绝对化** (realpath) 再回显, 避免后续歧义

**回显模板**:

```
✅ 已切换根目录: <resolved-abs-path>
  notes:   <abs>/notes
  reports: <abs>/reports
本会话所有读/写/回显都走这里。说 "切回默认" 还原。
```

**注意事项**:
- 这是**会话级**状态, 重启会话后回到系统默认
- 不持久化到磁盘, 不修改 `paths.py` 默认值
- 如果用户切到一个非空目录, **不要清理或覆盖** 现有文件; 只在缺失时建子目录
- 切完路径后, 用户接着发"刚跟硬件组对 ..."  → 直接走 logging 流程, 写到**新根**的 notes/

### Repeat suppression

| 触发 | 行为 |
|---|---|
| "写周报" 5 秒内重复 | 提示 "刚才已经生成了, 还要再生成一次吗?" |

## 不在 commands.md 的 (避免重复)

- **Logging 流程** (解析 / 分类 / 路由日期 / 追加) → `references/logging.md`
- **Edit 流程** (搜原文 / 确认 / 改 / 撤销) → `references/editing.md`
- **Generate 流程** (反问日期 / 归并 / 润色 / 写盘) → SKILL.md "Quick workflow" + `references/merging.md` + `references/next-week-plan.md` + `references/polish-rules.md`
- **内容分类** (A~H 8 类) → `references/content-classifier.md`
- **Data root 解析底层** (脚本/平台) → `references/scripts.md` 中 `scripts/paths.py` 一节
