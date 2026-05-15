import os

from PyQt6.QtGui import QPixmap

from src.core.capture_history import capture_history_manager
from src.core.plugin_base import PluginBase
from src.platform.shell import open_parent, open_path
from src.ui.capture_history_window import CaptureHistoryWindow
from src.ui.pinned_image_window import PinnedImageWindow


class CaptureHistoryPlugin(PluginBase):
    required_capabilities = ("clipboard", "open_path", "pinned_image")

    def __init__(self):
        self.window = None
        self._pinned_windows = []

    def get_name(self):
        return "捕获历史"

    def get_description(self):
        return "查看、搜索、复制并复用截图捕获历史"

    def get_keywords(self):
        return ["cap", "capture", "shot", "截图历史", "捕获历史"]

    def get_command_schema(self):
        return {
            "usage": "cap [query|clear]",
            "examples": ["cap", "cap 1920x1080", "capture clear"],
            "params": [
                {
                    "name": "query",
                    "label": "关键词",
                    "placeholder": "留空打开中心；输入 clear 清空未置顶",
                    "required": False,
                }
            ],
        }

    def is_direct_action(self):
        return True

    def execute(self, query):
        q = query.strip()
        q_lower = q.lower()
        if q_lower in self.get_keywords():
            q = ""
            q_lower = ""

        results = [
            {
                "name": "打开捕获历史中心",
                "path": "open_center",
                "type": "capture_center",
            }
        ]

        if q_lower in {"clear", "clean", "清空"}:
            results.insert(
                0,
                {
                    "name": "清空未置顶捕获历史",
                    "path": "clear_unpinned",
                    "type": "capture_cmd",
                },
            )
            return results

        results.extend(capture_history_manager.as_search_results(query=q, limit=25))
        return results

    def _ensure_window(self):
        if self.window is None:
            self.window = CaptureHistoryWindow(manager=capture_history_manager)

    def _entry_path(self, entry):
        saved_path = str(entry.get("saved_path", "")).strip()
        if saved_path and os.path.exists(saved_path):
            return saved_path
        return str(entry.get("image_path", "")).strip()

    def handle_action(self, action):
        action_key = str(action).strip()
        if action_key == "open_center":
            self._ensure_window()
            self.window.refresh_list()
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
            return "已打开捕获历史中心"

        if action_key == "clear_unpinned":
            removed = capture_history_manager.clear_unpinned()
            return f"已清理 {removed} 条未置顶记录"

        if action_key.startswith("copy:"):
            entry_id = action_key.split(":", 1)[1].strip()
            if capture_history_manager.copy_entry_to_clipboard(entry_id):
                return "已复制捕获图片"
            return "复制失败，捕获记录可能已失效"

        if action_key.startswith("pin-image:"):
            entry_id = action_key.split(":", 1)[1].strip()
            entry = capture_history_manager.get_entry(entry_id)
            if not entry:
                return "贴图失败，捕获记录可能已失效"
            pixmap = QPixmap(str(entry.get("image_path", "")))
            if pixmap.isNull():
                return "贴图失败，捕获记录可能已失效"
            window = PinnedImageWindow(pixmap)
            window.show()
            self._pinned_windows.append(window)
            return "已创建贴图"

        if action_key.startswith("pin:"):
            entry_id = action_key.split(":", 1)[1].strip()
            pinned = capture_history_manager.toggle_pin(entry_id)
            return "已置顶" if pinned else "已取消置顶"

        if action_key.startswith("open:"):
            entry_id = action_key.split(":", 1)[1].strip()
            entry = capture_history_manager.get_entry(entry_id)
            if not entry:
                return "打开失败，捕获记录可能已失效"
            path = self._entry_path(entry)
            if path and open_path(path):
                return "已打开捕获图片"
            return "打开失败，捕获记录可能已失效"

        if action_key.startswith("folder:"):
            entry_id = action_key.split(":", 1)[1].strip()
            entry = capture_history_manager.get_entry(entry_id)
            if not entry:
                return "打开失败，捕获记录可能已失效"
            path = self._entry_path(entry)
            if open_parent(path):
                return "已打开捕获目录"
            return "打开失败，捕获记录可能已失效"

        return ""

    def on_enter(self):
        pass

    def on_exit(self):
        pass
