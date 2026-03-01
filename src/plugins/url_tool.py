from urllib.parse import quote, unquote
from src.core.plugin_base import PluginBase


class UrlPlugin(PluginBase):
    def get_name(self):
        return "URL 编码/解码"

    def get_description(self):
        return "对 URL 进行编码或解码"

    def get_keywords(self):
        return ["u", "url"]

    def get_command_schema(self):
        return {
            "usage": "url <text-or-url>",
            "examples": ["url https://a.com?q=中文", "u hello world"],
            "params": [
                {
                    "name": "value",
                    "label": "文本或 URL",
                    "placeholder": "输入待编码/解码内容",
                    "required": True,
                }
            ],
        }

    def execute(self, query):
        query = query.strip()
        if not query:
            return []

        results = []
        try:
            # Decode
            decoded = unquote(query)
            if decoded != query:
                results.append(
                    {
                        "name": f"解码结果: {decoded}",
                        "path": decoded,
                        "type": "copy_result",
                    }
                )

            # Encode
            encoded = quote(query)
            results.append(
                {"name": f"编码结果: {encoded}", "path": encoded, "type": "copy_result"}
            )

        except Exception as e:
            results.append({"name": f"错误: {str(e)}", "path": "", "type": "error"})

        return results

    def on_enter(self):
        pass

    def on_exit(self):
        pass
