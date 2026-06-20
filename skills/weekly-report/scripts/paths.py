"""跨平台路径解析。
- macOS / Linux: ~/Documents/WeeklyNotes/
- Windows:        %USERPROFILE%\\Documents\\WeeklyNotes\\
- 可被环境变量 WEEKLY_NOTES_DIR 覆盖
"""
import os
import pathlib
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def data_root() -> pathlib.Path:
    env = os.environ.get("WEEKLY_NOTES_DIR")
    if env:
        return pathlib.Path(env).expanduser().resolve()
    if sys.platform == "win32":
        return pathlib.Path(os.environ.get("USERPROFILE", str(pathlib.Path.home()))) / "Documents" / "WeeklyNotes"
    return pathlib.Path.home() / "Documents" / "WeeklyNotes"

def notes_dir() -> pathlib.Path:
    return data_root() / "notes"

def reports_dir() -> pathlib.Path:
    return data_root() / "reports"

def logs_dir() -> pathlib.Path:
    return data_root() / "logs"

def ensure_dirs() -> pathlib.Path:
    """确保数据根 + 三个子目录都存在。返回根路径。"""
    root = data_root()
    (root / "notes").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    return root

if __name__ == "__main__":
    root = data_root()
    print(f"Platform: {sys.platform}")
    print(f"Data root: {root}")
    print(f"  notes:   {notes_dir()}")
    print(f"  reports: {reports_dir()}")
    print(f"  logs:    {logs_dir()}")
