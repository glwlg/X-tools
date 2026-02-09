from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QCheckBox,
    QLabel,
    QComboBox,
    QPushButton,
)
from PyQt6.QtCore import pyqtSignal


class SettingsWindow(QWidget):
    settings_changed = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__()
        self.config_manager = config_manager
        self.setWindowTitle("X-Tools Settings")
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Appearance
        layout.addWidget(QLabel("Appearance:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(
            ["Dark", "Light"]
            + [
                k
                for k in self.config_manager.themes.keys()
                if k not in ["Dark", "Light"]
            ]
        )
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        layout.addWidget(self.theme_combo)

        # General
        layout.addWidget(QLabel("General:"))
        self.startup_check = QCheckBox("Run on Startup")
        self.startup_check.stateChanged.connect(self.on_startup_changed)
        layout.addWidget(self.startup_check)

        self.resize(300, 200)

    def load_settings(self):
        config = self.config_manager.config

        # Theme
        current_theme = config.get("theme", "Dark")
        index = self.theme_combo.findText(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)

        # Startup
        self.startup_check.setChecked(config.get("run_on_startup", False))

    def on_theme_changed(self, text):
        self.config_manager.config["theme"] = text
        self.config_manager.save_config()
        self.settings_changed.emit()

    def on_startup_changed(self, state):
        enable = state == 2  # Qt.CheckState.Checked
        success = self.config_manager.set_startup(enable)
        if not success:
            # Revert if failed (e.g. permission error, though usually fine via HKCU)
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(not enable)
            self.startup_check.blockSignals(False)
            pass
