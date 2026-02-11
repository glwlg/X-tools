import uuid
from src.core.plugin_base import PluginBase


class UuidPlugin(PluginBase):
    def get_name(self):
        return "UUID 生成器"

    def get_description(self):
        return "生成随机 UUID (v4)"

    def get_keywords(self):
        return ["uuid"]

    def execute(self, query):
        # Even without query, we can offer to generate some
        results = []
        try:
            # Generate 5 by default or N if specified
            count = 5
            if query.strip().isdigit():
                count = min(int(query.strip()), 50)  # Limit to 50

            for _ in range(count):
                u = str(uuid.uuid4())
                results.append({"name": u, "path": u, "type": "copy_result"})
        except Exception as e:
            results.append({"name": f"错误: {str(e)}", "path": "", "type": "error"})

        return results

    def on_enter(self):
        pass

    def on_exit(self):
        pass
