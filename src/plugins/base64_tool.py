import base64
from src.core.plugin_base import PluginBase


class Base64Plugin(PluginBase):
    def get_name(self):
        return "Base64 编码/解码"

    def get_description(self):
        return "对文本进行 Base64 编码或解码"

    def get_keywords(self):
        return ["b"]

    def execute(self, query):
        query = query.strip()
        if not query:
            return []

        results = []
        try:
            # Try decoding first
            try:
                decoded = base64.b64decode(query).decode("utf-8")
                results.append(
                    {
                        "name": f"解码结果: {decoded}",
                        "path": decoded,
                        "type": "copy_result",
                    }
                )
            except Exception:
                pass

            # Always offer encoding
            encoded = base64.b64encode(query.encode("utf-8")).decode("utf-8")
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
