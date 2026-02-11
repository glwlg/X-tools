from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QCheckBox,
    QLabel,
    QComboBox,
    QScrollArea,
    QFrame,
    QHBoxLayout,
    QStackedWidget,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QFont
import os
import json
import sys


class SettingsWindow(QWidget):
    settings_changed = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__()
        self.config_manager = config_manager
        self.check_icon_path = self.resolve_resource_path("check.svg").replace(
            "\\", "/"
        )
        self.setWindowTitle("X-Tools 设置")
        self.init_ui()
        self.load_settings()

    def resolve_resource_path(self, filename):
        if getattr(sys, "frozen", False):
            # If packaged with PyInstaller, use the internal temp folder
            base_path = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
            possible_paths = [
                os.path.join(base_path, filename),
                os.path.join(base_path, "src", "ui", filename),
                os.path.join(base_path, "_internal", "src", "ui", filename),
            ]
        else:
            # In development, look relative to this file
            base_path = os.path.dirname(__file__)
            possible_paths = [os.path.join(base_path, filename)]

        for p in possible_paths:
            if os.path.exists(p):
                return p
        return filename  # Fallback

    def init_ui(self):
        self.setMinimumSize(880, 600)
        self.update_style()

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)

        self.add_sidebar_item("通用设置", "⚙️")
        self.add_sidebar_item("外观样式", "🎨")
        self.add_sidebar_item("插件管理", "🔌")

        self.sidebar.currentRowChanged.connect(self.display_page)
        main_layout.addWidget(self.sidebar)

        # 2. Right Content Area
        self.pages = QStackedWidget()
        self.pages.setObjectName("contentArea")

        # --- Page 0: General ---
        page_gen = self.create_page("通用设置", "管理应用的基本运行方式")
        self.startup_check = QCheckBox("系统启动时自动运行")
        self.startup_check.stateChanged.connect(self.on_startup_changed)
        page_gen.layout().addWidget(self.wrap_in_card(self.startup_check))
        page_gen.layout().addStretch()
        self.pages.addWidget(page_gen)

        # --- Page 1: Appearance ---
        page_app = self.create_page("外观样式", "自定义应用的主题和视觉效果")
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("选择界面主题:"))
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
        theme_row.addWidget(self.theme_combo)
        page_app.layout().addWidget(self.wrap_in_card(theme_row))

        # Theme Editor
        editor_label = QLabel("主题 JSON 配置 (小心编辑):")
        editor_label.setObjectName("editorLabel")
        page_app.layout().addWidget(editor_label)

        self.theme_editor = QPlainTextEdit()
        self.theme_editor.setObjectName("themeEditor")
        self.theme_editor.setPlaceholderText(
            '{\n  "Custom": {\n    "window_bg": "#...", ...\n  }\n}'
        )
        page_app.layout().addWidget(self.theme_editor)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_theme_btn = QPushButton("应用并保存主题")
        self.save_theme_btn.setObjectName("saveBtn")
        self.save_theme_btn.clicked.connect(self.on_save_themes)
        btn_row.addWidget(self.save_theme_btn)
        page_app.layout().addLayout(btn_row)

        page_app.layout().addStretch()
        self.pages.addWidget(page_app)

        # --- Page 2: Plugins ---
        page_plugins = self.create_page("插件管理", "启用或禁用功能扩展插件")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setObjectName("pluginScroll")

        self.scroll_content = QWidget()
        self.plugin_list_layout = QVBoxLayout(self.scroll_content)
        self.plugin_list_layout.setSpacing(15)
        self.plugin_list_layout.setContentsMargins(0, 0, 15, 0)

        from src.core.plugin_manager import plugin_manager

        for plugin in plugin_manager.get_plugins(enabled_only=False):
            p_card = QFrame()
            p_card.setObjectName("pluginCard")
            p_layout = QHBoxLayout(p_card)
            p_layout.setContentsMargins(20, 15, 20, 15)

            # Left: Toggle + Info
            info_v_layout = QVBoxLayout()
            info_h_layout = QHBoxLayout()
            cb = QCheckBox(plugin.get_name())
            cb.setProperty("class", "pluginTitle")
            cb.setChecked(plugin_manager.is_plugin_enabled(plugin.get_name()))
            cb.stateChanged.connect(
                lambda state, name=plugin.get_name(): plugin_manager.set_plugin_enabled(
                    name, state == 2
                )
            )
            info_h_layout.addWidget(cb)

            # Keywords next to title
            for kw in plugin.get_keywords():
                kw_label = QLabel(kw)
                kw_label.setProperty("class", "pluginKeyword")
                info_h_layout.addWidget(kw_label)
            info_h_layout.addStretch()
            info_v_layout.addLayout(info_h_layout)

            desc = QLabel(plugin.get_description())
            desc.setProperty("class", "pluginDesc")
            info_v_layout.addWidget(desc)
            p_layout.addLayout(info_v_layout)

            self.plugin_list_layout.addWidget(p_card)

        self.plugin_list_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        page_plugins.layout().addWidget(self.scroll)
        self.pages.addWidget(page_plugins)

        main_layout.addWidget(self.pages)
        self.sidebar.setCurrentRow(0)

    def create_page(self, title, subtitle):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(10)

        header = QLabel(title)
        header.setObjectName("pageHeader")
        layout.addWidget(header)

        sub = QLabel(subtitle)
        sub.setObjectName("pageSubtitle")
        layout.addWidget(sub)

        return page

    def wrap_in_card(self, content):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        if isinstance(content, QHBoxLayout):
            layout.addLayout(content)
        else:
            layout.addWidget(content)
        return card

    def add_sidebar_item(self, text, icon_char):
        item = QListWidgetItem(f"  {icon_char}  {text}")
        item.setSizeHint(QSize(0, 50))
        self.sidebar.addItem(item)

    def display_page(self, index):
        self.pages.setCurrentIndex(index)

    def load_settings(self):
        config = self.config_manager.config
        current_theme = config.get("theme", "Dark")
        index = self.theme_combo.findText(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        self.startup_check.setChecked(config.get("run_on_startup", False))
        self.refresh_theme_editor()

    def refresh_theme_editor(self):
        json_str = json.dumps(self.config_manager.themes, indent=4, ensure_ascii=False)
        self.theme_editor.setPlainText(json_str)

    def on_save_themes(self):
        try:
            new_themes = json.loads(self.theme_editor.toPlainText())
            if not isinstance(new_themes, dict):
                raise ValueError("JSON must be an object/dict")

            # Validate basic structure for current theme at least
            current = self.config_manager.config.get("theme", "Dark")
            if current not in new_themes:
                # If they renamed/removed current, fallback to first available or Dark
                if new_themes:
                    current = list(new_themes.keys())[0]
                    self.config_manager.config["theme"] = current
                else:
                    raise ValueError("At least one theme must be defined")

            self.config_manager.themes = new_themes
            self.config_manager.save_themes()

            # Update combo
            self.theme_combo.blockSignals(True)
            self.theme_combo.clear()
            self.theme_combo.addItems(list(new_themes.keys()))
            index = self.theme_combo.findText(current)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)
            self.theme_combo.blockSignals(False)

            self.update_style()
            self.settings_changed.emit()
            QMessageBox.information(self, "成功", "主题配置已应用并保存！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"JSON 格式无效: {str(e)}")

    def update_style(self):
        theme = self.config_manager.get_theme()
        qss = f"""
            QWidget {{
                background-color: transparent;
                color: {theme["text_color"]};
                font-family: "Microsoft YaHei UI", sans-serif;
            }}
            SettingsWindow, #sidebar, #contentArea, QStackedWidget {{
                background-color: {theme["window_bg"]};
            }}
            #sidebar {{
                background-color: {theme["input_bg"]};
                border: none;
                border-right: 1px solid {theme["border"]};
                padding-top: 15px;
                outline: none;
            }}
            #sidebar::item {{
                height: 50px;
                padding-left: 20px;
                border-left: 4px solid transparent;
                color: {theme["text_color"]};
                font-size: 14px;
            }}
            #sidebar::item:selected {{
                background-color: {theme["selection_bg"]};
                color: {theme["selection_text"]};
                border-left: 4px solid {theme["highlight"]};
                font-weight: bold;
            }}
            #sidebar::item:hover:!selected {{
                background-color: {theme["selection_bg"]}40;
            }}
            #pageHeader {{
                font-size: 32px;
                font-weight: bold;
                color: {theme["text_color"]};
                margin-bottom: 5px;
            }}
            #pageSubtitle {{
                font-size: 14px;
                color: {theme["text_dim"]};
                margin-bottom: 20px;
            }}
            #card, #pluginCard {{
                background-color: {theme["input_bg"]};
                border: 1px solid {theme["border"]};
                border-radius: 12px;
            }}
            #pluginCard:hover {{
                border: 1px solid {theme["highlight"]}80;
            }}
            .pluginTitle {{
                font-size: 16px;
                font-weight: bold;
                color: {theme["text_color"]};
            }}
            .pluginDesc {{
                font-size: 13px;
                color: {theme["text_dim"]};
                margin-left: 32px;
            }}
            .pluginKeyword {{
                background-color: {theme["highlight"]}33;
                color: {theme["highlight"]};
                border: 1px solid {theme["highlight"]}66;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 12px;
                font-weight: bold;
                font-family: 'Consolas', 'Courier New', monospace;
                margin-left: 5px;
            }}
            QComboBox {{
                background-color: {theme["input_bg"]};
                border: 1px solid {theme["border"]};
                border-radius: 6px;
                padding: 8px 12px;
                min-width: 160px;
                color: {theme["text_color"]};
            }}
            QComboBox:hover {{
                border: 1px solid {theme["highlight"]};
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme["input_bg"]};
                border: 1px solid {theme["border"]};
                selection-background-color: {theme["selection_bg"]};
                selection-color: {theme["selection_text"]};
                color: {theme["text_color"]};
                outline: none;
            }}
            #themeEditor {{
                background-color: {theme["input_bg"]};
                border: 1px solid {theme["border"]};
                border-radius: 8px;
                color: {theme["text_color"]};
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                padding: 10px;
                min-height: 250px;
            }}
            #editorLabel {{
                font-size: 14px;
                font-weight: bold;
                margin-top: 20px;
                color: {theme["text_color"]};
            }}
            #saveBtn {{
                background-color: {theme["highlight"]};
                color: {theme["selection_text"]};
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 14px;
            }}
            #saveBtn:hover {{
                background-color: {theme["highlight"]}EE;
            }}
            #saveBtn:pressed {{
                background-color: {theme["highlight"]}CC;
            }}
            QCheckBox {{
                spacing: 12px;
                font-size: 14px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {theme["border"]};
                border-radius: 6px;
                background-color: {theme["input_bg"]};
                padding: 2px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {theme["highlight"]};
                border: 2px solid {theme["highlight"]};
                image: url({self.check_icon_path});
            }}
            QCheckBox::indicator:hover {{
                border-color: {theme["highlight"]};
            }}
            QCheckBox::indicator:unchecked:hover {{
                background-color: {theme["highlight"]}1A;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 10px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme["scrollbar_handle"]};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {theme["highlight"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """
        self.setStyleSheet(qss)

    def on_theme_changed(self, text):
        self.config_manager.config["theme"] = text
        self.config_manager.save_config()
        self.update_style()
        self.settings_changed.emit()

    def on_startup_changed(self, state):
        enable = state == 2
        success = self.config_manager.set_startup(enable)
        if not success:
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(not enable)
            self.startup_check.blockSignals(False)
