#!/usr/bin/env python3
"""Markdown 周报 → 自包含 HTML(内联 CSS,公司风)。
兼容 Windows / macOS / Linux。
- 输出文件强制 UTF-8 (含 BOM 由浏览器兼容)
- cell 内容 HTML escape, 防止 <script> 等注入
- <br> 在 escape 后还原为 HTML 换行标签
"""
import sys
import io
import os
import re
import pathlib
from html import escape as _html_escape

try:
    from jinja2 import Template
except ImportError:
    sys.stderr.write(
        "[ERROR] 缺 jinja2: pip3 install --user jinja2\n"
    )
    sys.exit(2)

# Windows 终端默认 GBK, print 中文会崩
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>{{ title }}</title>
<style>
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "微软雅黑", sans-serif;
         margin: 24px; color: #1a1a1a; background: #fff; }
  h1 { color: #1F4E78; font-size: 22px; border-bottom: 3px solid #1F4E78; padding-bottom: 8px; }
  h2 { color: #1F4E78; font-size: 16px; margin-top: 28px; }
  .meta { background: #F2F2F2; padding: 8px 12px; border-left: 4px solid #1F4E78;
          font-size: 12px; color: #555; margin: 8px 0 20px; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 16px;
          font-size: 13px; table-layout: fixed; }
  th { background: #1F4E78; color: #fff; font-weight: 600;
       padding: 8px 10px; text-align: left; border: 1px solid #1F4E78;
       word-break: break-all; }
  td { padding: 6px 10px; border: 1px solid #D0D0D0; vertical-align: middle;
       word-break: break-all; }
  tr:nth-child(even) td { background: #F9F9F9; }
</style></head><body>
{{ body }}
</body></html>
"""

def _render_cell(text: str) -> str:
    """escape 后再把 \\n / <br> 还原成 HTML 换行。"""
    s = _html_escape(str(text or ""), quote=False)
    s = re.sub(r"&lt;br\s*/?&gt;", "<br>", s)
    s = s.replace("\n", "<br>")
    return s

def md_to_html(md_path: pathlib.Path, html_path: pathlib.Path):
    md_path = pathlib.Path(md_path)
    html_path = pathlib.Path(html_path)
    md_text = md_path.read_text(encoding="utf-8")
    title = "周报"
    for ln in md_text.splitlines():
        if ln.strip().startswith("# "):
            title = ln.strip()[2:].strip()
            break
    lines = []
    for ln in md_text.splitlines():
        s = ln.strip()
        if s.startswith("# "):
            lines.append(f"<h1>{_html_escape(s[2:].strip())}</h1>")
        elif s.startswith("## "):
            lines.append(f"<h2>{_html_escape(s[3:].strip())}</h2>")
        elif s.startswith("> "):
            lines.append(f'<div class="meta">{_html_escape(s[2:].strip())}</div>')
        elif s.startswith("|"):
            lines.append(ln)
        else:
            lines.append(f"<p>{_html_escape(ln)}</p>")
    rendered = "\n".join(lines)
    def wrap_table(m):
        rows = [r for r in m.group(0).splitlines() if r.strip()]
        if len(rows) < 2:
            return m.group(0)
        out = ["<table>"]
        cells = [c.strip() for c in rows[0].strip("|").split("|")]
        out.append("<thead><tr>" + "".join(f"<th>{_render_cell(c)}</th>" for c in cells) + "</tr></thead>")
        body_rows = [r for r in rows[2:]]
        out.append("<tbody>")
        for r in body_rows:
            cells = [c.strip() for c in r.strip("|").split("|")]
            out.append("<tr>" + "".join(f"<td>{_render_cell(c)}</td>" for c in cells) + "</tr>")
        out.append("</tbody></table>")
        return "\n".join(out)
    rendered = re.sub(r"((?:^\|.*\n?)+)", wrap_table, rendered, flags=re.MULTILINE)
    html = Template(HTML_TEMPLATE).render(title=_html_escape(title), body=rendered)
    # Windows / macOS / Linux 都用 utf-8 写
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML -> {html_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.stderr.write("usage: render_html.py <md_path> <html_path>\n")
        sys.exit(1)
    md_to_html(sys.argv[1], sys.argv[2])
