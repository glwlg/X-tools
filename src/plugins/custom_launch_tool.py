from src.core.custom_launch import custom_launch_manager
from src.core.plugin_base import PluginBase


class CustomLaunchPlugin(PluginBase):
    required_capabilities = ("custom_launch", "open_path")

    def get_name(self):
        return "自定义启动项"

    def get_description(self):
        return "搜索并启动用户配置的程序、文件夹、文件或 URL"

    def get_keywords(self):
        return ["launch", "start", "启动项"]

    def get_command_schema(self):
        return {
            "usage": "launch [query]",
            "examples": ["launch", "launch code", "start docs"],
            "params": [
                {
                    "name": "query",
                    "label": "关键词",
                    "placeholder": "留空列出全部自定义启动项",
                    "required": False,
                }
            ],
        }

    def is_direct_action(self):
        return True

    def execute(self, query):
        q = query.strip()
        if q.lower() in self.get_keywords():
            q = ""

        results = custom_launch_manager.search(q, limit=50)
        if results:
            return results

        return [
            {
                "type": "error",
                "name": "没有匹配的自定义启动项",
                "path": "请在设置中添加自定义启动项",
            }
        ]

    def on_enter(self):
        pass

    def on_exit(self):
        pass
