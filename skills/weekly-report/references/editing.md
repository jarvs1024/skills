# Edit / delete / undo

## Delete the most recent entry ("刚才那条删掉")

1. Find the latest entry in the current week's file
2. Show it back to the user: "最后一条是:'{原文}',确认删除?"
3. On confirm, remove the bullet block and re-save the file atomically
4. If the user is editing a different week's file, ask: "本周没有这条,搜全周文件吗?"

## Modify by keyword ("把昨天那条 X 改成 Y")

1. Parse X (the search key) and Y (the replacement value)
2. Find the most recent entry in the named date containing X
3. Show: "找到:'{原文}',改成 '{Y}'?"
4. On confirm, replace the value (keep the timestamp and bullet structure)
5. If no match: "没找到包含 X 的记录,要不要列出本周所有记录?"

## Backdate delete ("删掉 N 周前的")

Ask for the target date first if not given. Then proceed as above against the resolved week's file.

## Regenerate report ("再写一次")

If a `.xlsx` already exists at the target path, back it up to `.bak` first, then regenerate. Never overwrite silently.

## Undo edit ("撤销修改")

Only the most recent edit can be undone, and only in the same session. Restore the value from the in-memory pre-edit snapshot. Cross-session undo: instruct the user to manually restore from `.bak`.

## Batch operations

For multi-entry delete or modify, always:
1. List the affected entries in a preview
2. Wait for explicit "确认" / "go" / "yes"
3. Then apply atomically
