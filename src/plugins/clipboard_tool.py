from src.core.clipboard_history import clipboard_history_manager
from src.core.plugin_base import PluginBase
from src.ui.clipboard_window import ClipboardWindow


class ClipboardPlugin(PluginBase):
    def __init__(self):
        self.window = None

    def get_name(self):
        return "剪贴板历史"

    def get_description(self):
        return "查看、搜索、置顶并复用历史剪贴板内容"

    def get_keywords(self):
        return ["clip", "clipboard"]

    def get_command_schema(self):
        return {
            "usage": "clip [query|clear]",
            "examples": ["clip", "clip token", "clipboard clear"],
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
                "name": "打开剪贴板历史中心",
                "path": "open_center",
                "type": "clipboard_center",
            }
        ]

        if q_lower in {"clear", "clean", "清空"}:
            results.insert(
                0,
                {
                    "name": "清空未置顶剪贴板历史",
                    "path": "clear_unpinned",
                    "type": "clipboard_cmd",
                },
            )
            return results

        results.extend(clipboard_history_manager.as_search_results(query=q, limit=25))
        return results

    def _ensure_window(self):
        if self.window is None:
            self.window = ClipboardWindow(manager=clipboard_history_manager)

    def handle_action(self, action):
        action_key = str(action).strip()
        if action_key == "open_center":
            self._ensure_window()
            self.window.refresh_list()
            self.window.show()
            self.window.raise_()
            self.window.activateWindow()
            return "已打开剪贴板历史中心"

        if action_key == "clear_unpinned":
            removed = clipboard_history_manager.clear_unpinned()
            return f"已清理 {removed} 条未置顶记录"

        if action_key.startswith("copy:"):
            entry_id = action_key.split(":", 1)[1].strip()
            if clipboard_history_manager.copy_entry_to_clipboard(entry_id):
                return "已复制到剪贴板"
            return "复制失败，条目可能已失效"

        if action_key.startswith("pin:"):
            entry_id = action_key.split(":", 1)[1].strip()
            pinned = clipboard_history_manager.toggle_pin(entry_id)
            return "已置顶" if pinned else "已取消置顶"

        return ""

    def on_enter(self):
        pass

    def on_exit(self):
        pass
