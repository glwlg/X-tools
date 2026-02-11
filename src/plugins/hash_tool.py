import hashlib
from src.core.plugin_base import PluginBase


class HashPlugin(PluginBase):
    def get_name(self):
        return "Hash 生成器"

    def get_description(self):
        return "生成 MD5, SHA1, SHA256 哈希值"

    def get_keywords(self):
        return ["h"]

    def execute(self, query):
        query = query.strip()
        if not query:
            return []

        results = []
        try:
            data = query.encode("utf-8")

            # MD5
            md5_val = hashlib.md5(data).hexdigest()
            results.append(
                {"name": f"MD5: {md5_val}", "path": md5_val, "type": "copy_result"}
            )

            # SHA1
            sha1_val = hashlib.sha1(data).hexdigest()
            results.append(
                {"name": f"SHA1: {sha1_val}", "path": sha1_val, "type": "copy_result"}
            )

            # SHA256
            sha256_val = hashlib.sha256(data).hexdigest()
            results.append(
                {
                    "name": f"SHA256: {sha256_val}",
                    "path": sha256_val,
                    "type": "copy_result",
                }
            )

        except Exception as e:
            results.append({"name": f"错误: {str(e)}", "path": "", "type": "error"})

        return results

    def on_enter(self):
        pass

    def on_exit(self):
        pass
