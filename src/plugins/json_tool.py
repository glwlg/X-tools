import json
from src.core.plugin_base import PluginBase


class JsonPlugin(PluginBase):
    def get_name(self):
        return "JSON 格式化"

    def get_description(self):
        return "格式化或压缩 JSON 字符串"

    def get_keywords(self):
        return ["j"]

    def execute(self, query):
        query = query.strip()
        if not query:
            return []

        results = []
        try:
            parsed = json.loads(query)

            # Formatted
            formatted = json.dumps(parsed, indent=4, ensure_ascii=False)
            results.append(
                {
                    "name": "格式化结果 (已复制到剪贴板预览部分): "
                    + (formatted[:100] + "..." if len(formatted) > 100 else formatted),
                    "path": formatted,
                    "type": "copy_result",
                }
            )

            # Minified
            minified = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
            results.append(
                {
                    "name": "压缩结果: "
                    + (minified[:100] + "..." if len(minified) > 100 else minified),
                    "path": minified,
                    "type": "copy_result",
                }
            )

        except Exception as e:
            results.append(
                {"name": f"JSON 解析错误: {str(e)}", "path": "", "type": "error"}
            )

        return results

    def on_enter(self):
        pass

    def on_exit(self):
        pass
