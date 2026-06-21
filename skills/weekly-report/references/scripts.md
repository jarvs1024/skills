# Scripts reference

所有脚本跨 Windows / macOS / Linux, 路径用 `pathlib`, 输出强制 UTF-8。Windows 终端会自动 `reconfigure` 到 UTF-8 避免中文 print 报错。

## scripts/paths.py

跨平台数据目录解析。

```python
from paths import data_root, notes_dir, reports_dir, ensure_dirs
root = ensure_dirs()  # 不存在会自动建 (notes/ + reports/)
```

优先级: `WEEKLY_NOTES_DIR` 环境变量 > 系统默认 (`~/Documents/WeeklyNotes/` 或 `%USERPROFILE%\Documents\WeeklyNotes\`)。

## scripts/generate_xlsx.py

Convert `周报-YYYY-MM-Www.md` → `周报-YYYY-MM-Www.xlsx` (primary deliverable).

Usage:
```bash
python3 scripts/generate_xlsx.py --date YYYY-MM-DD \
    --md <path> --out <path-to-xlsx>
```

`--date` is the Thursday of the report's target week (it determines the report's filename and date range).

Behavior:
- Reads the markdown, parses the 5-column + 3-column tables
- Applies the styling in `style-spec.md`
- Creates `<current-root>/reports/YYYY-MM-Www/` if missing
- Returns 0 on success; non-zero on openpyxl / parse error
- If the output `.xlsx` already exists, **refuses to overwrite** — caller must handle `.bak` first

## Adding new scripts

When you find yourself rewriting the same Python snippet for a second time, promote it into `scripts/` so the next invocation does not pay that cost.

## scripts/smoke_test.py

无依赖的回归测试 (只用标准库 + openpyxl)。合成一份 MD, 跑 xlsx pipeline, 断言关键行为:

- parse_md 解析出正确表格数
- `<br>` 转成真换行
- xlsx 列宽按最长单行算

跑法:

```bash
python3 scripts/smoke_test.py
# 或 Windows
python scripts\\smoke_test.py
```

退出码: 0 = 全部通过, 1 = 有失败。建议在改完 parse_md / 列宽算法 / generate_xlsx 后跑一次。
