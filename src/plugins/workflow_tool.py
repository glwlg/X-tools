from PyQt6.QtWidgets import QApplication

from src.core.plugin_base import PluginBase
from src.core.plugin_manager import plugin_manager


class WorkflowPlugin(PluginBase):
    def __init__(self):
        self._workflows = [
            {
                "id": "clip-md5",
                "name": "剪贴板文本 -> MD5",
                "description": "读取剪贴板文本并复制其 MD5 值",
            },
            {
                "id": "clip-url-encode",
                "name": "剪贴板文本 -> URL 编码",
                "description": "读取剪贴板文本并复制 URL 编码结果",
            },
            {
                "id": "clip-base64-encode",
                "name": "剪贴板文本 -> Base64 编码",
                "description": "读取剪贴板文本并复制 Base64 编码结果",
            },
            {
                "id": "now-timestamp",
                "name": "当前时间 -> 时间戳",
                "description": "生成当前 Unix 时间戳并复制到剪贴板",
            },
        ]

    def get_name(self):
        return "工作流宏"

    def get_description(self):
        return "将多步操作合并为一个命令执行"

    def get_keywords(self):
        return ["wf", "workflow", "flow", "macro"]

    def get_command_schema(self):
        return {
            "usage": "wf <workflow-id>",
            "examples": ["wf clip-md5", "workflow now-timestamp", "flow"],
            "params": [
                {
                    "name": "workflow_id",
                    "label": "工作流标识",
                    "placeholder": "clip-md5 / clip-url-encode / now-timestamp",
                    "required": False,
                }
            ],
        }

    def is_direct_action(self):
        return True

    def execute(self, query):
        text = query.strip().lower()
        if text in self.get_keywords():
            text = ""
        if text.startswith("run "):
            text = text[4:].strip()

        matched = []
        if not text:
            matched = self._workflows
        else:
            for wf in self._workflows:
                if (
                    text in wf["id"]
                    or text in wf["name"].lower()
                    or text in wf["description"].lower()
                ):
                    matched.append(wf)

        return [
            {
                "name": f"执行工作流: {wf['name']} ({wf['id']})",
                "path": wf["id"],
                "type": "workflow_run",
                "workflow_desc": wf["description"],
            }
            for wf in matched
        ]

    @staticmethod
    def _clipboard_text():
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return ""
        return clipboard.text().strip()

    @staticmethod
    def _copy_text(value):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(str(value))
        return True

    @staticmethod
    def _require_plugin(keyword):
        plugin = plugin_manager.get_plugin_by_keyword(keyword)
        if plugin is None:
            raise RuntimeError(f"未找到插件: {keyword}")
        return plugin

    @staticmethod
    def _pick_result(results, prefix=""):
        if not isinstance(results, list):
            return None

        if prefix:
            for item in results:
                name = str(item.get("name", "")).lower()
                if name.startswith(prefix.lower()):
                    return item

        return results[0] if results else None

    def _run_clip_md5(self):
        text = self._clipboard_text()
        if not text:
            return False, "剪贴板没有可用文本"

        plugin = self._require_plugin("hash")
        results = plugin.execute(text)
        item = self._pick_result(results, prefix="md5")
        if not item:
            return False, "Hash 工作流执行失败"

        ok = self._copy_text(item.get("path", ""))
        if not ok:
            return False, "无法写入剪贴板"

        return True, "工作流完成：已复制 MD5"

    def _run_clip_url_encode(self):
        text = self._clipboard_text()
        if not text:
            return False, "剪贴板没有可用文本"

        plugin = self._require_plugin("url")
        results = plugin.execute(text)
        item = self._pick_result(results, prefix="编码结果")
        if not item:
            return False, "URL 编码工作流执行失败"

        ok = self._copy_text(item.get("path", ""))
        if not ok:
            return False, "无法写入剪贴板"

        return True, "工作流完成：已复制 URL 编码结果"

    def _run_clip_base64_encode(self):
        text = self._clipboard_text()
        if not text:
            return False, "剪贴板没有可用文本"

        plugin = self._require_plugin("base64")
        results = plugin.execute(text)
        item = self._pick_result(results, prefix="编码结果")
        if not item:
            return False, "Base64 工作流执行失败"

        ok = self._copy_text(item.get("path", ""))
        if not ok:
            return False, "无法写入剪贴板"

        return True, "工作流完成：已复制 Base64 编码结果"

    def _run_now_timestamp(self):
        plugin = self._require_plugin("timestamp")
        results = plugin.execute("now")
        item = self._pick_result(results, prefix="当前时间戳")
        if not item:
            return False, "时间戳工作流执行失败"

        ok = self._copy_text(item.get("path", ""))
        if not ok:
            return False, "无法写入剪贴板"

        return True, "工作流完成：已复制当前时间戳"

    def handle_action(self, workflow_id):
        key = str(workflow_id).strip().lower()
        runners = {
            "clip-md5": self._run_clip_md5,
            "clip-url-encode": self._run_clip_url_encode,
            "clip-base64-encode": self._run_clip_base64_encode,
            "now-timestamp": self._run_now_timestamp,
        }

        runner = runners.get(key)
        if runner is None:
            return "未找到对应工作流"

        ok, msg = runner()
        if ok:
            return msg
        return f"工作流失败: {msg}"

    def on_enter(self):
        pass

    def on_exit(self):
        pass
