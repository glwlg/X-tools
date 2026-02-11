import json
import winreg
import sys
import os

CONFIG_DIR = os.path.join(os.getenv("APPDATA"), "x-tools")
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_CONFIG = {"run_on_startup": False, "theme": "Dark", "plugins_enabled": {}}

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
                json.dump(DEFAULT_CONFIG, f, indent=4)
            return DEFAULT_CONFIG.copy()

        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return DEFAULT_CONFIG.copy()

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

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
            print(f"Error saving themes: {e}")

    def get_theme(self, theme_name=None):
        if not theme_name:
            theme_name = self.config.get("theme", "Dark")
        return self.themes.get(theme_name, self.themes.get("Dark"))

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
            print(f"Registry error: {e}")
            return False


config_manager = ConfigManager()
