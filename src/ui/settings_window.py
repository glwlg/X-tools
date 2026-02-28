from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QMessageBox,
)
from qfluentwidgets import (
    FluentWindow,
    SettingCardGroup,
    SwitchSettingCard,
    PrimaryPushSettingCard,
    PushSettingCard,
    PlainTextEdit,
    ScrollArea,
    FluentIcon as FI,
    SettingCard,
    ComboBox,
    setThemeColor,
    NavigationItemPosition,
    LargeTitleLabel,
)
from src.core.hotkey_manager import VK_MAP
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeyEvent, QIcon
import os
import json
import sys


class HotkeyRecordCard(PushSettingCard):
    hotkey_changed = pyqtSignal(str)

    def __init__(
        self, title, action_key, config_manager, icon=FI.COMMAND_PROMPT, parent=None
    ):
        super().__init__("未设置", icon, title, "点击右侧按钮开始录制快捷键", parent)
        self.config_manager = config_manager
        self.action_key = action_key
        self._recording = False

        self.button.clicked.connect(self.start_recording)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.load_hotkey()

    def load_hotkey(self):
        hk = self.config_manager.get_hotkey(self.action_key)
        self._hotkey = hk
        self._update_display()

    def _update_display(self):
        if self._recording:
            self.button.setText("⏺ 录制中...")
        elif self._hotkey:
            self.button.setText(self._format_hotkey(self._hotkey))
        else:
            self.button.setText("未设置")

    @staticmethod
    def _format_hotkey(hotkey_str: str) -> str:
        if not hotkey_str:
            return ""
        parts = hotkey_str.lower().split("+")
        return " + ".join(p.strip().capitalize() for p in parts)

    def start_recording(self):
        self._recording = True
        self._update_display()
        self.setFocus()

    def get_hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, hotkey_str: str):
        self._hotkey = hotkey_str
        self._update_display()

    def keyPressEvent(self, event: QKeyEvent):
        if not self._recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Meta,
        ):
            return

        if key == Qt.Key.Key_Escape:
            self._recording = False
            self._update_display()
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("win")

        key_char = event.text().lower()
        key_name = None

        if key_char and key_char in VK_MAP:
            key_name = key_char
        else:
            for name, vk in VK_MAP.items():
                qt_key_name = f"Key_{name.capitalize()}"
                if hasattr(Qt.Key, qt_key_name) and getattr(Qt.Key, qt_key_name) == key:
                    key_name = name
                    break
            if key_name is None:
                for i in range(1, 13):
                    if key == getattr(Qt.Key, f"Key_F{i}"):
                        key_name = f"f{i}"
                        break

        if key_name is None:
            return

        if not parts and not key_name.startswith("f"):
            return

        parts.append(key_name)
        new_hotkey = "+".join(parts)

        self._hotkey = new_hotkey
        self._recording = False
        self._update_display()
        self.hotkey_changed.emit(new_hotkey)

    def focusOutEvent(self, event):
        if self._recording:
            self._recording = False
            self._update_display()
        super().focusOutEvent(event)


class ScrollWidget(ScrollArea):
    """A generic scrollable widget page for Settings"""

    def __init__(self, title, obj_name, parent=None):
        super().__init__(parent)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)

        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)
        self.vBoxLayout.setSpacing(16)

        self.titleLabel = LargeTitleLabel(title, self.view)
        self.titleLabel.setObjectName("pageTitle")
        # Give it a nice bold appearance and space below
        font = self.titleLabel.font()
        font.setPixelSize(28)
        font.setBold(True)
        self.titleLabel.setFont(font)
        self.titleLabel.setStyleSheet("margin-bottom: 12px;")

        self.vBoxLayout.addWidget(self.titleLabel)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName(obj_name)

        self.setStyleSheet(
            "ScrollWidget { background-color: transparent; border: none; } "
            "QScrollArea { border: none; background-color: transparent; }"
        )
        self.view.setStyleSheet("QWidget { background-color: transparent; }")

    def addGroup(self, group):
        self.vBoxLayout.addWidget(group)

    def addStretch(self):
        self.vBoxLayout.addStretch(1)


class SettingsWindow(FluentWindow):
    settings_changed = pyqtSignal()
    hotkeys_changed = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager

        logo_path = self._resolve_resource_path("logo.png")
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        self.setWindowTitle("X-Tools 设置")
        self.setMinimumSize(960, 680)

        # Apply vibrant modern accent color instead of default blue
        if self.config_manager.get_theme_name() == "Dark":
            setThemeColor("#4CC2FF")  # Icy modern blue for dark mode
        else:
            setThemeColor("#4455EE")

        # Enable acrylic/mica effect natively via FluentWindow
        self.windowEffect.setMicaEffect(
            self.winId(), isDarkMode=self.config_manager.get_theme_name() == "Dark"
        )

        self.init_pages()
        self.load_settings()

    def _resolve_resource_path(self, filename):
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
            possible_paths = [
                os.path.join(base_path, filename),
                os.path.join(base_path, "_internal", filename),
            ]
        else:
            possible_paths = [
                os.path.join(os.path.dirname(__file__), filename),
                os.path.join(os.getcwd(), filename),
            ]
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return None

    def init_pages(self):
        # ─── Page 0: General ───
        self.page_gen = ScrollWidget("通用设置", "page_general", self)
        gen_group = SettingCardGroup("应用启动行为", self.page_gen)

        self.startup_check = SwitchSettingCard(
            FI.POWER_BUTTON,
            "开机自动启动",
            "在 Windows 启动时自动运行 X-Tools 并在后台驻留",
            parent=gen_group,
        )
        self.startup_check.checkedChanged.connect(self.on_startup_changed)
        gen_group.addSettingCard(self.startup_check)
        self.page_gen.addGroup(gen_group)
        self.page_gen.addStretch()

        # ─── Page 1: Appearance ───
        self.page_app = ScrollWidget("外观样式", "page_appearance", self)
        app_group = SettingCardGroup("界面与视觉", self.page_app)

        self.theme_combo_card = SettingCard(
            FI.BRUSH, "界面主题", "选择全量界面的配色风格", app_group
        )
        self.theme_combo = ComboBox(self.theme_combo_card)
        self.theme_combo.addItems(
            ["Dark", "Light"]
            + [
                k
                for k in self.config_manager.themes.keys()
                if k not in ["Dark", "Light"]
            ]
        )
        self.theme_combo.setCurrentText(self.config_manager.get_theme_name())
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        self.theme_combo_card.hBoxLayout.addWidget(
            self.theme_combo, 0, Qt.AlignmentFlag.AlignRight
        )
        self.theme_combo_card.hBoxLayout.addSpacing(16)

        app_group.addSettingCard(self.theme_combo_card)

        # Editor for raw JSON themes underneath
        raw_theme_group = SettingCardGroup("主题 JSON 配置 (高级)", self.page_app)
        # Using a layout to add PlainTextEdit
        self.theme_editor = PlainTextEdit(self.page_app.view)
        self.theme_editor.setMinimumHeight(200)
        self.theme_editor.setStyleSheet("font-family: 'Consolas', monospace;")
        raw_theme_group.layout().addWidget(self.theme_editor)

        save_btn = PrimaryPushSettingCard(
            "应用保存",
            FI.SAVE,
            "保存高级主题配置",
            "编辑上方的 JSON 后点击此按钮生效",
            parent=raw_theme_group,
        )
        save_btn.clicked.connect(self.on_save_themes)
        raw_theme_group.addSettingCard(save_btn)

        self.page_app.addGroup(app_group)
        self.page_app.addGroup(raw_theme_group)
        self.page_app.addStretch()

        # ─── Page 2: Plugins ───
        self.page_plugins = ScrollWidget("插件管理", "page_plugins", self)
        plugins_group = SettingCardGroup("启用的扩展功能", self.page_plugins)

        from src.core.plugin_manager import plugin_manager

        for plugin in plugin_manager.get_plugins(enabled_only=False):
            desc = (
                plugin.get_description()
                + f" (触发词: {', '.join(plugin.get_keywords())})"
            )
            card = SwitchSettingCard(
                FI.APPLICATION, plugin.get_name(), desc, parent=plugins_group
            )
            card.setChecked(plugin_manager.is_plugin_enabled(plugin.get_name()))
            card.checkedChanged.connect(
                lambda state, name=plugin.get_name(): plugin_manager.set_plugin_enabled(
                    name, state
                )
            )
            plugins_group.addSettingCard(card)

        self.page_plugins.addGroup(plugins_group)
        self.page_plugins.addStretch()

        # ─── Page 3: Hotkeys ───
        self.page_hotkeys = ScrollWidget("快捷键", "page_hotkeys", self)
        hotkeys_group = SettingCardGroup("全局操作快捷键", self.page_hotkeys)

        self._hotkey_cards = {}
        actions = [
            ("toggle_window", "唤起 / 隐藏主搜索窗口", FI.SEARCH),
            ("screenshot", "立即进行屏幕截图并在编辑后复制", FI.PHOTO),
            ("pin_clipboard", "将目前系统剪切板贴在屏幕最上层", FI.PIN),
        ]

        for action_key, label_text, icon in actions:
            card = HotkeyRecordCard(
                label_text,
                action_key,
                self.config_manager,
                icon=icon,
                parent=hotkeys_group,
            )
            self._hotkey_cards[action_key] = card
            hotkeys_group.addSettingCard(card)

        self.page_hotkeys.addGroup(hotkeys_group)

        action_group = SettingCardGroup("操作", self.page_hotkeys)

        save_hk_btn = PrimaryPushSettingCard(
            "保存",
            FI.ACCEPT,
            "保存快捷键配置",
            "录制完毕后，点击保存使全局热键生效",
            parent=action_group,
        )
        save_hk_btn.clicked.connect(self.on_save_hotkeys)
        action_group.addSettingCard(save_hk_btn)

        reset_btn = PushSettingCard(
            "恢复",
            FI.SYNC,
            "恢复默认值",
            "清空现有设置，恢复回初始快捷键",
            parent=action_group,
        )
        reset_btn.clicked.connect(self.on_reset_hotkeys)
        action_group.addSettingCard(reset_btn)

        self.page_hotkeys.addGroup(action_group)
        self.page_hotkeys.addStretch()

        # ─── Add Interfaces ───
        self.addSubInterface(self.page_gen, FI.SETTING, "通用")
        self.addSubInterface(self.page_app, FI.BRUSH, "外观")
        self.addSubInterface(self.page_plugins, FI.APPLICATION, "插件")
        self.addSubInterface(self.page_hotkeys, FI.COMMAND_PROMPT, "快捷键")

    def load_settings(self):
        config = self.config_manager.config

        self.startup_check.setChecked(config.get("run_on_startup", False))

        json_str = json.dumps(self.config_manager.themes, indent=4, ensure_ascii=False)
        self.theme_editor.setPlainText(json_str)

    def on_theme_changed(self, text):
        self.config_manager.config["theme"] = text
        self.config_manager.save_config()
        # The app style will reload
        self.settings_changed.emit()

    def on_startup_changed(self, state):
        success = self.config_manager.set_startup(state)
        if not success:
            self.startup_check.setChecked(not state)

    def on_save_themes(self):
        try:
            new_themes = json.loads(self.theme_editor.toPlainText())
            if not isinstance(new_themes, dict):
                raise ValueError("JSON must be an object/dict")

            current = self.config_manager.config.get("theme", "Dark")
            if current not in new_themes:
                current = list(new_themes.keys())[0] if new_themes else "Dark"
                self.config_manager.config["theme"] = current

            self.config_manager.themes = new_themes
            self.config_manager.save_themes()

            # Refresh Options manually if needed, simplified here
            self.settings_changed.emit()
            QMessageBox.information(self, "成功", "主题配置已应用并保存！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"JSON 格式无效: {str(e)}")

    def on_save_hotkeys(self):
        values = []
        for action_key, card in self._hotkey_cards.items():
            hk = card.get_hotkey()
            if hk:
                if hk in values:
                    QMessageBox.warning(self, "冲突", f"快捷键 '{hk}' 被多次使用。")
                    return
                values.append(hk)

        for action_key, card in self._hotkey_cards.items():
            self.config_manager.set_hotkey(action_key, card.get_hotkey())

        self.hotkeys_changed.emit()
        QMessageBox.information(self, "成功", "快捷键已保存并生效。")

    def on_reset_hotkeys(self):
        from src.core.config import DEFAULT_HOTKEYS

        for action_key, card in self._hotkey_cards.items():
            default_val = DEFAULT_HOTKEYS.get(action_key, "")
            card.set_hotkey(default_val)
