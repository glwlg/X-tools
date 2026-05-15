import os
import subprocess
import sys
import webbrowser


def open_path(target: str) -> bool:
    value = str(target or "").strip()
    if not value:
        return False

    try:
        if sys.platform.startswith("win"):
            os.startfile(value)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", value])
        else:
            subprocess.Popen(["xdg-open", value])
        return True
    except Exception:
        try:
            return bool(webbrowser.open(value))
        except Exception:
            return False


def open_parent(path: str) -> bool:
    value = str(path or "").strip()
    if not value:
        return False
    folder = value if os.path.isdir(value) else os.path.dirname(value)
    if not folder or not os.path.exists(folder):
        return False
    return open_path(folder)

