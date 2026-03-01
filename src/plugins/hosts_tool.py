from src.core.plugin_base import PluginBase
from src.ui.hosts_window import HostsWindow


class HostsPlugin(PluginBase):
    def __init__(self):
        self.hosts_window = None

    def get_name(self):
        return "Hosts 管理"

    def get_description(self):
        return "快速切换和编辑系统 Hosts"

    def get_keywords(self):
        return ["hosts", "host"]

    def get_command_schema(self):
        return {
            "usage": "hosts",
            "examples": ["hosts", "host"],
            "params": [],
        }

    def is_direct_action(self):
        return True

    def execute(self, query):
        return [
            {
                "name": "打开 Hosts 管理",
                "path": "open_hosts",
                "type": "hosts_cmd",
            }
        ]

    def handle_action(self, query):
        if query == "open_hosts":
            if not self.hosts_window:
                self.hosts_window = HostsWindow()
            else:
                self.hosts_window.update_style()
                self.hosts_window.load_profiles()  # Refresh any system hosts changes outside
            if self.hosts_window.isHidden():
                self.hosts_window.show()

            def safe_activate():
                try:
                    self.hosts_window.activateWindow()
                    self.hosts_window.raise_()
                except RuntimeError:
                    self.hosts_window = HostsWindow()
                    self.hosts_window.show()
                    self.hosts_window.activateWindow()
                    self.hosts_window.raise_()

            safe_activate()

    def on_enter(self):
        pass

    def on_exit(self):
        pass
