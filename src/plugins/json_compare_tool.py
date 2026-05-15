from src.core.plugin_base import PluginBase
from src.ui.json_compare_window import JsonCompareWindow


class JsonComparePlugin(PluginBase):
    required_capabilities = ()

    def __init__(self):
        self.window = None

    def get_name(self):
        return "JSON 对比"

    def get_description(self):
        return "对比两个 JSON 的语义差异和规范化行差异"

    def get_keywords(self):
        return ["jd", "jsondiff", "jsoncompare", "json对比"]

    def get_command_schema(self):
        return {
            "usage": "jsondiff",
            "examples": ["jsondiff", "jd", "json对比"],
            "params": [],
        }

    def is_direct_action(self):
        return True

    def execute(self, query):
        return [
            {
                "name": "打开 JSON 对比工具",
                "path": "open_json_compare",
                "type": "json_compare_cmd",
            }
        ]

    def handle_action(self, action):
        if str(action).strip() != "open_json_compare":
            return ""

        if self.window is None:
            self.window = JsonCompareWindow()
        else:
            self.window.update_style()

        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        return "已打开 JSON 对比工具"

    def on_enter(self):
        pass

    def on_exit(self):
        pass
