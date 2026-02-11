from urllib.parse import quote, unquote
from src.core.plugin_base import PluginBase


class UrlPlugin(PluginBase):
    def get_name(self):
        return "URL 编码/解码"

    def get_description(self):
        return "对 URL 进行编码或解码"

    def get_keywords(self):
        return ["u"]

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
