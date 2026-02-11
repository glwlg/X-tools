import os
import sys
import importlib.util
import inspect
from src.core.plugin_base import PluginBase


class PluginManager:
    def __init__(self):
        self.plugins = []
        self.plugin_dir = self._resolve_plugin_dir()

    def _resolve_plugin_dir(self):
        """Resolve plugin directory for both dev and frozen (PyInstaller) environments."""
        if getattr(sys, "frozen", False):
            # PyInstaller onedir mode: exe is in dist/x-tools/
            # Collected data goes to dist/x-tools/_internal/src/plugins/
            base = os.path.dirname(sys.executable)
            candidates = [
                os.path.join(base, "_internal", "src", "plugins"),
                os.path.join(base, "src", "plugins"),
            ]
            for path in candidates:
                if os.path.isdir(path):
                    print(f"[PluginManager] Found plugin dir (frozen): {path}")
                    return path
            print(
                f"[PluginManager] WARNING: No plugin dir found in frozen mode. Searched: {candidates}"
            )
            return candidates[0]  # Return first candidate for logging purposes
        else:
            # Dev mode: relative to this file (src/core/plugin_manager.py -> src/plugins/)
            path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "plugins")
            print(f"[PluginManager] Plugin dir (dev): {path}")
            return path

    def load_plugins(self):
        self.plugins = []
        if not os.path.exists(self.plugin_dir):
            print(f"[PluginManager] Plugin directory does not exist: {self.plugin_dir}")
            return

        print(f"[PluginManager] Scanning plugins in: {self.plugin_dir}")
        for filename in os.listdir(self.plugin_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_path = os.path.join(self.plugin_dir, filename)
                module_name = f"plugin_{filename[:-3]}"

                try:
                    spec = importlib.util.spec_from_file_location(
                        module_name, module_path
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for name, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and issubclass(obj, PluginBase)
                            and obj is not PluginBase
                        ):
                            self.plugins.append(obj())
                            print(f"[PluginManager] Loaded plugin: {obj.__name__}")
                except Exception as e:
                    print(f"[PluginManager] Failed to load plugin {filename}: {e}")

    def get_plugins(self, enabled_only=True):
        if not enabled_only:
            return self.plugins

        from src.core.config import config_manager

        enabled_map = config_manager.config.get("plugins_enabled", {})
        return [p for p in self.plugins if enabled_map.get(p.get_name(), True)]

    def is_plugin_enabled(self, plugin_name):
        from src.core.config import config_manager

        return config_manager.config.get("plugins_enabled", {}).get(plugin_name, True)

    def set_plugin_enabled(self, plugin_name, enabled):
        from src.core.config import config_manager

        if "plugins_enabled" not in config_manager.config:
            config_manager.config["plugins_enabled"] = {}
        config_manager.config["plugins_enabled"][plugin_name] = enabled
        config_manager.save_config()

    def get_plugin_by_keyword(self, keyword):
        for plugin in self.get_plugins(enabled_only=True):
            if keyword in plugin.get_keywords():
                return plugin
        return None


plugin_manager = PluginManager()
plugin_manager.load_plugins()
