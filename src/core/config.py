import json
import copy
import winreg
import sys
import os
from src.core.logger import get_logger
from src.core.workflow_schema import DEFAULT_WORKFLOWS, normalize_workflows


logger = get_logger(__name__)

CONFIG_DIR = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "x-tools")
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_HOTKEYS = {
    "toggle_window": "alt+q",
    "screenshot": "alt+a",
    "pin_clipboard": "alt+v",
}

DEFAULT_CONFIG = {
    "run_on_startup": False,
    "theme": "Dark",
    "plugins_enabled": {},
    "hotkeys": DEFAULT_HOTKEYS.copy(),
    "screenshot_auto_save": False,
    "screenshot_auto_copy": False,
    "screenshot_auto_pin": False,
    "screenshot_save_dir": os.path.join(
        os.path.expanduser("~"), "Pictures", "x-tools-screenshots"
    ),
    "screenshot_filename_template": "x-tools_{date}_{time}",
    "workflows": copy.deepcopy(DEFAULT_WORKFLOWS),
}


def _deepcopy_default_config():
    return copy.deepcopy(DEFAULT_CONFIG)


THEME_FILE = os.path.join(CONFIG_DIR, "themes.json")
DEFAULT_THEMES = {
    "Dark": {
        "window_bg": "#1E1E1E",
        "input_bg": "#2D2D2D",
        "text_color": "#E0E0E0",
        "text_dim": "#909090",
        "highlight": "#007ACC",
        "border": "#3E3E3E",
        "selection_bg": "#094771",
        "selection_text": "#FFFFFF",
        "scrollbar_bg": "transparent",
        "scrollbar_handle": "#424242",
    },
    "Light": {
        "window_bg": "#F5F5F5",
        "input_bg": "#FFFFFF",
        "text_color": "#212121",
        "text_dim": "#757575",
        "highlight": "#0078D7",
        "border": "#DCDCDC",
        "selection_bg": "#CCE8FF",
        "selection_text": "#000000",
        "scrollbar_bg": "transparent",
        "scrollbar_handle": "#C1C1C1",
    },
}


class ConfigManager:
    def __init__(self):
        self.config = self.load_config()
        self.themes = self.load_themes()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "w") as f:
                json.dump(_deepcopy_default_config(), f, indent=4)
            return _deepcopy_default_config()

        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                if not isinstance(loaded, dict):
                    return _deepcopy_default_config()

                merged = _deepcopy_default_config()
                merged.update(loaded)

                if not isinstance(merged.get("hotkeys"), dict):
                    merged["hotkeys"] = DEFAULT_HOTKEYS.copy()

                if not isinstance(merged.get("plugins_enabled"), dict):
                    merged["plugins_enabled"] = {}

                merged["workflows"] = normalize_workflows(merged.get("workflows"))

                return merged
        except:
            return _deepcopy_default_config()

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.warning("Error saving config: %s", e)

    def load_themes(self):
        if not os.path.exists(THEME_FILE):
            with open(THEME_FILE, "w") as f:
                json.dump(DEFAULT_THEMES, f, indent=4)
            return DEFAULT_THEMES.copy()

        try:
            with open(THEME_FILE, "r") as f:
                themes = json.load(f)
                # Ensure all default themes and their keys exist
                for theme_name, default_theme_data in DEFAULT_THEMES.items():
                    if theme_name not in themes:
                        themes[theme_name] = default_theme_data.copy()
                    else:
                        # Merge keys for existing themes
                        for key, value in default_theme_data.items():
                            if key not in themes[theme_name]:
                                themes[theme_name][key] = value
                return themes
        except:
            return DEFAULT_THEMES.copy()

    def save_themes(self):
        try:
            with open(THEME_FILE, "w") as f:
                json.dump(self.themes, f, indent=4)
        except Exception as e:
            logger.warning("Error saving themes: %s", e)

    def get_theme_name(self):
        return self.config.get("theme", "Dark")

    def get_theme(self, theme_name=None):
        if not theme_name:
            theme_name = self.config.get("theme", "Dark")
        return self.themes.get(theme_name, self.themes.get("Dark"))

    def get_hotkey(self, action: str) -> str:
        """Get the hotkey string for an action, falling back to default."""
        hotkeys = self.config.get("hotkeys", {})
        return hotkeys.get(action, DEFAULT_HOTKEYS.get(action, ""))

    def set_hotkey(self, action: str, key_str: str):
        """Set the hotkey string for an action and save."""
        if "hotkeys" not in self.config:
            self.config["hotkeys"] = DEFAULT_HOTKEYS.copy()
        self.config["hotkeys"][action] = key_str
        self.save_config()

    def get_value(self, key: str, default=None):
        return self.config.get(key, default)

    def set_value(self, key: str, value):
        self.config[key] = value
        self.save_config()

    def get_workflows(self):
        return normalize_workflows(self.config.get("workflows"))

    def set_workflows(self, workflows):
        self.config["workflows"] = normalize_workflows(workflows)
        self.save_config()

    def set_startup(self, enable=True):
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "x-tools"
        exe_path = sys.executable  # For packaged app, sys.executable is the exe path

        # If running as script, use python exe + script path? Or just warn.
        # For development (uv run), sys.executable is python.exe.
        # We should use sys.argv[0] if possible but complex.
        # But user asked for packaged app, so let's implement for packaged mainly.
        # However, for testing, we can use the script path.
        if getattr(sys, "frozen", False):
            path_to_run = f'"{exe_path}"'
        else:
            script_path = os.path.abspath(sys.argv[0])
            path_to_run = f'"{exe_path}" "{script_path}"'  # Run via python

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS
            )
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, path_to_run)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            self.config["run_on_startup"] = enable
            self.save_config()
            return True
        except Exception as e:
            logger.warning("Registry error: %s", e)
            return False


config_manager = ConfigManager()
