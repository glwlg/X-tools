import re
from src.core.plugin_base import PluginBase


class CalculatorPlugin(PluginBase):
    def get_name(self):
        return "计算器"

    def get_description(self):
        return "执行数学运算"

    def get_keywords(self):
        return ["c"]

    def execute(self, query):
        if not query.strip():
            return []

        try:
            # Replace common math symbols
            expr = query.replace("^", "**").replace("x", "*")
            # Simple sanitization - only allow digits, operations, parens
            if not re.match(r"^[\d\s\+\-\*\/\(\)\.\%]+$", expr):
                return [{"name": "无效的表达式", "path": "", "type": "calc_error"}]

            result = str(eval(expr))
            return [{"name": f"= {result}", "path": result, "type": "calc_result"}]
        except Exception:
            return [{"name": "计算错误", "path": "", "type": "calc_error"}]

    def on_enter(self):
        pass  # UI handled by main window

    def on_exit(self):
        pass
