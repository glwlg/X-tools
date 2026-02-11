import datetime
import time
from src.core.plugin_base import PluginBase


class TimestampPlugin(PluginBase):
    def get_name(self):
        return "时间戳转换"

    def get_description(self):
        return "Unix 时间戳与日期格式互转"

    def get_keywords(self):
        return ["t"]

    def execute(self, query):
        query = query.strip()
        if not query:
            return []

        results = []
        try:
            if query.lower() == "now":
                ts = int(time.time())
                dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                results.append(
                    {
                        "name": f"当前时间戳: {ts}",
                        "path": str(ts),
                        "type": "copy_result",
                    }
                )
                results.append(
                    {"name": f"当前日期: {dt}", "path": dt, "type": "copy_result"}
                )
            elif query.isdigit():
                # Timestamp to Date
                ts = int(query)
                dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                results.append(
                    {"name": f"日期: {dt}", "path": dt, "type": "copy_result"}
                )
            else:
                # Date to Timestamp (Try common formats)
                formats = [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y/%m/%d",
                ]
                for fmt in formats:
                    try:
                        dt = datetime.datetime.strptime(query, fmt)
                        ts = int(dt.timestamp())
                        results.append(
                            {
                                "name": f"时间戳: {ts}",
                                "path": str(ts),
                                "type": "copy_result",
                            }
                        )
                        break
                    except ValueError:
                        continue

                if not results:
                    results.append(
                        {"name": "无效的日期格式", "path": "", "type": "error"}
                    )
        except Exception as e:
            results.append({"name": f"错误: {str(e)}", "path": "", "type": "error"})

        return results

    def on_enter(self):
        pass

    def on_exit(self):
        pass
