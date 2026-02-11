import os
import ctypes
from src.core.plugin_base import PluginBase


class SystemCommandsPlugin(PluginBase):
    def get_name(self):
        return "系统命令"

    def get_description(self):
        return "系统快捷控制 (锁屏、休眠等)"

    def get_keywords(self):
        return ["sys"]

    def execute(self, query):
        query = query.strip().lower()
        commands = {
            "lock": "锁定工作站",
            "sleep": "进入睡眠模式",
            "empty": "清空回收站",
            "shutdown": "关闭系统",
            "restart": "重启系统",
        }

        if not query:
            return [
                {"name": f"{k}: {v}", "path": k, "type": "sys_cmd"}
                for k, v in commands.items()
            ]

        results = []
        for k, v in commands.items():
            if query in k:
                results.append({"name": v, "path": k, "type": "sys_cmd"})

        return results

    def handle_action(self, cmd):
        if cmd == "lock":
            ctypes.windll.user32.LockWorkStation()
        elif cmd == "sleep":
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        elif cmd == "empty":
            # SHEmptyRecycleBinW
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 1 | 2 | 4)
        elif cmd == "shutdown":
            os.system("shutdown /s /t 0")
        elif cmd == "restart":
            os.system("shutdown /r /t 0")

    def on_enter(self):
        pass

    def on_exit(self):
        pass
