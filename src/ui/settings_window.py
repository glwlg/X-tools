from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QMessageBox,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QColorDialog,
    QFrame,
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
    NavigationItemPosition,
    LargeTitleLabel,
)
from src.core.hotkey_manager import VK_MAP
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeyEvent, QIcon, QColor
from datetime import datetime
import os
import sys

from src.core.metrics import metrics_store
from src.core.workflow_schema import validate_workflow_id
from src.core.workflow_steps_codec import (
    extract_placeholders,
    find_unknown_placeholders,
    format_workflow_steps_text as _format_workflow_steps_text,
    parse_workflow_steps_text as _parse_workflow_steps_text,
)


ALLOWED_WORKFLOW_VARS = {"clipboard", "prev", "input"}

HOTKEY_ACTIONS = [
    ("toggle_window", "主窗口", "显示 / 隐藏搜索窗口"),
    ("screenshot", "截图", "唤起截图与标注工具"),
    ("pin_clipboard", "贴图", "将剪贴板图片固定到桌面"),
]

THEME_COLOR_FIELDS = [
    ("window_bg", "窗口背景", "主窗口、搜索面板和大面积容器的背景色"),
    ("input_bg", "输入背景", "搜索框、预览面板和输入区域背景"),
    ("text_color", "正文文字", "主要文字、搜索结果和正文内容颜色"),
    ("text_dim", "弱化文字", "说明文字、占位提示和次要信息颜色"),
    ("highlight", "强调色", "按钮、选中态、悬停态的品牌强调色"),
    ("border", "边框", "卡片、输入框和预览区域边框颜色"),
    ("selection_bg", "选中背景", "搜索结果或文本选中时的背景色"),
    ("selection_text", "选中文字", "选中状态下的文字颜色"),
    ("scrollbar_bg", "滚动条轨道", "支持输入 transparent 表示透明"),
    ("scrollbar_handle", "滚动条滑块", "滚动条可拖动部分颜色"),
]


def normalize_theme_color(value: str, fallback: str = "#FFFFFF") -> str:
    value = str(value or "").strip()
    if value.lower() == "transparent":
        return "transparent"

    color = QColor(value)
    if not color.isValid():
        return fallback
    return color.name().upper()


def is_valid_theme_color(value: str) -> bool:
    value = str(value or "").strip()
    return value.lower() == "transparent" or QColor(value).isValid()


def build_screenshot_filename_preview(template: str, now: datetime | None = None) -> str:
    template = str(template or "").strip() or "x-tools_{date}_{time}"
    now = now or datetime.now()
    safe_name = (
        template.replace("{date}", now.strftime("%Y%m%d"))
        .replace("{time}", now.strftime("%H%M%S"))
        .replace("{datetime}", now.strftime("%Y%m%d_%H%M%S"))
    )
    for ch in '<>:"/\\|?*':
        safe_name = safe_name.replace(ch, "_")
    safe_name = safe_name.strip().strip(".")
    if not safe_name:
        safe_name = f"x-tools_{now.strftime('%Y%m%d_%H%M%S')}"
    return safe_name + ".png"


def format_hotkey_display(hotkey_str: str) -> str:
    if not hotkey_str:
        return "未设置"
    parts = str(hotkey_str).lower().split("+")
    return " + ".join(p.strip().capitalize() for p in parts)


def parse_workflow_steps_text(text) -> list[dict]:
    return _parse_workflow_steps_text(text)


def format_workflow_steps_text(steps) -> str:
    return _format_workflow_steps_text(steps)


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
        return format_hotkey_display(hotkey_str)

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


class ThemeColorCard(SettingCard):
    value_changed = pyqtSignal(str, str)

    def __init__(self, key, title, description, parent=None):
        super().__init__(FI.BRUSH, title, description, parent)
        self.key = key
        self._value = "#FFFFFF"
        self._color_dialog = None

        self.value_edit = QLineEdit(self)
        self.value_edit.setMinimumWidth(112)
        self.value_edit.setMaximumWidth(132)
        self.value_edit.setPlaceholderText("#RRGGBB")
        self.value_edit.textChanged.connect(self._on_text_changed)

        self.pick_button = QPushButton(self)
        self.pick_button.setMinimumWidth(84)
        self.pick_button.clicked.connect(self.open_color_dialog)

        self.hBoxLayout.addWidget(self.value_edit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addWidget(self.pick_button, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def set_value(self, value, emit=False):
        normalized = normalize_theme_color(value, self._value)
        self._value = normalized

        self.value_edit.blockSignals(True)
        self.value_edit.setText(normalized)
        self.value_edit.blockSignals(False)
        self._refresh_button()

        if emit:
            self.value_changed.emit(self.key, normalized)

    def _on_text_changed(self, text):
        if is_valid_theme_color(text):
            self.set_value(text, emit=True)

    def _refresh_button(self):
        if self._value.lower() == "transparent":
            self.pick_button.setText("透明")
            self.pick_button.setStyleSheet(
                """
                QPushButton {
                    color: #555;
                    border: 1px dashed #8A8A8A;
                    border-radius: 6px;
                    background: transparent;
                    padding: 4px 10px;
                }
                """
            )
            return

        color = QColor(self._value)
        text_color = "#FFFFFF" if color.lightness() < 128 else "#202020"
        self.pick_button.setText("选色")
        self.pick_button.setStyleSheet(
            f"""
            QPushButton {{
                color: {text_color};
                border: 1px solid rgba(0, 0, 0, 36);
                border-radius: 6px;
                background-color: {self._value};
                padding: 4px 10px;
            }}
            """
        )

    def open_color_dialog(self):
        old_value = self._value
        initial = QColor(self._value)
        if not initial.isValid():
            initial = QColor("#FFFFFF")

        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle("选择颜色")
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.currentColorChanged.connect(
            lambda color: self.set_value(color.name().upper(), emit=True)
        )
        dialog.colorSelected.connect(
            lambda color: self.set_value(color.name().upper(), emit=True)
        )
        dialog.rejected.connect(lambda: self.set_value(old_value, emit=True))
        dialog.finished.connect(lambda _result: setattr(self, "_color_dialog", None))
        self._color_dialog = dialog
        dialog.open()


class ThemePreviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.preview_frame = QFrame(self)
        self.preview_frame.setObjectName("ThemePreviewFrame")
        frame_layout = QVBoxLayout(self.preview_frame)
        frame_layout.setContentsMargins(18, 16, 18, 16)
        frame_layout.setSpacing(12)

        self.title_label = QLabel("实时预览", self.preview_frame)
        self.title_label.setObjectName("ThemePreviewTitle")
        frame_layout.addWidget(self.title_label)

        self.input_frame = QFrame(self.preview_frame)
        self.input_frame.setObjectName("ThemePreviewInput")
        input_layout = QHBoxLayout(self.input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)
        self.input_label = QLabel("搜索应用、文件或命令...", self.input_frame)
        self.input_label.setObjectName("ThemePreviewInputText")
        input_layout.addWidget(self.input_label)
        frame_layout.addWidget(self.input_frame)

        self.result_item = QFrame(self.preview_frame)
        self.result_item.setObjectName("ThemePreviewResult")
        result_layout = QVBoxLayout(self.result_item)
        result_layout.setContentsMargins(12, 8, 12, 8)
        result_layout.setSpacing(2)
        self.result_title = QLabel("X-Tools 搜索结果", self.result_item)
        self.result_title.setObjectName("ThemePreviewResultTitle")
        self.result_desc = QLabel("选中态、边框、弱化文字会在这里同步变化", self.result_item)
        self.result_desc.setObjectName("ThemePreviewResultDesc")
        result_layout.addWidget(self.result_title)
        result_layout.addWidget(self.result_desc)
        frame_layout.addWidget(self.result_item)

        layout.addWidget(self.preview_frame)

    def apply_theme(self, theme):
        window_bg = normalize_theme_color(theme.get("window_bg"), "#F5F5F5")
        input_bg = normalize_theme_color(theme.get("input_bg"), "#FFFFFF")
        text_color = normalize_theme_color(theme.get("text_color"), "#202020")
        text_dim = normalize_theme_color(theme.get("text_dim"), "#707070")
        highlight = normalize_theme_color(theme.get("highlight"), "#0078D7")
        border = normalize_theme_color(theme.get("border"), "#DCDCDC")
        selection_bg = normalize_theme_color(theme.get("selection_bg"), "#CCE8FF")
        selection_text = normalize_theme_color(theme.get("selection_text"), "#000000")

        self.setStyleSheet(
            f"""
            QFrame#ThemePreviewFrame {{
                background-color: {window_bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QLabel#ThemePreviewTitle {{
                color: {text_color};
                font-size: 16px;
                font-weight: 700;
            }}
            QFrame#ThemePreviewInput {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            QLabel#ThemePreviewInputText {{
                color: {text_dim};
                font-size: 13px;
            }}
            QFrame#ThemePreviewResult {{
                background-color: {selection_bg};
                border: 1px solid {highlight};
                border-radius: 10px;
            }}
            QLabel#ThemePreviewResultTitle {{
                color: {selection_text};
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#ThemePreviewResultDesc {{
                color: {selection_text};
                font-size: 12px;
            }}
            """
        )


class SettingsInfoTile(QFrame):
    def __init__(self, title, value="", description="", parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsInfoTile")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("SettingsInfoTileTitle")
        self.value_label = QLabel(value, self)
        self.value_label.setObjectName("SettingsInfoTileValue")
        self.desc_label = QLabel(description, self)
        self.desc_label.setObjectName("SettingsInfoTileDesc")
        self.desc_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.desc_label)

    def set_value(self, value, description=None):
        self.value_label.setText(str(value))
        if description is not None:
            self.desc_label.setText(str(description))


class SettingsOverviewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame(self)
        self.panel.setObjectName("SettingsOverviewPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(14)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_text = QVBoxLayout()
        title_text.setContentsMargins(0, 0, 0, 0)
        title_text.setSpacing(2)
        title = QLabel("配置总览", self.panel)
        title.setObjectName("SettingsOverviewTitle")
        subtitle = QLabel("常用配置状态集中展示，不需要再翻 JSON 确认。", self.panel)
        subtitle.setObjectName("SettingsOverviewSubtitle")
        title_text.addWidget(title)
        title_text.addWidget(subtitle)
        title_row.addLayout(title_text, 1)
        panel_layout.addLayout(title_row)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.theme_tile = SettingsInfoTile("主题", parent=self.panel)
        self.startup_tile = SettingsInfoTile("开机启动", parent=self.panel)
        self.screenshot_tile = SettingsInfoTile("截图动作", parent=self.panel)
        self.hotkey_tile = SettingsInfoTile("快捷键", parent=self.panel)
        self.workflow_tile = SettingsInfoTile("工作流宏", parent=self.panel)
        self.plugin_tile = SettingsInfoTile("插件", parent=self.panel)
        tiles = [
            self.startup_tile,
            self.theme_tile,
            self.screenshot_tile,
            self.hotkey_tile,
            self.workflow_tile,
            self.plugin_tile,
        ]
        for index, tile in enumerate(tiles):
            grid.addWidget(tile, index // 2, index % 2)
        panel_layout.addLayout(grid)
        layout.addWidget(self.panel)

        self.setStyleSheet(
            """
            QFrame#SettingsOverviewPanel {
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(38, 48, 68, 205),
                    stop: 1 rgba(18, 24, 34, 230)
                );
                border: 1px solid rgba(120, 145, 190, 90);
                border-radius: 18px;
            }
            QLabel#SettingsOverviewTitle {
                color: #F5F8FF;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#SettingsOverviewSubtitle {
                color: rgba(235, 241, 250, 160);
                font-size: 12px;
            }
            QFrame#SettingsInfoTile {
                background-color: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 34);
                border-radius: 14px;
            }
            QLabel#SettingsInfoTileTitle {
                color: rgba(235, 241, 250, 165);
                font-size: 12px;
            }
            QLabel#SettingsInfoTileValue {
                color: #FFFFFF;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#SettingsInfoTileDesc {
                color: rgba(235, 241, 250, 140);
                font-size: 12px;
            }
            """
        )

    def set_state(
        self,
        startup_state,
        theme_name,
        screenshot_actions,
        hotkey_state,
        workflow_count,
        enabled_plugins,
        total_plugins,
    ):
        self.startup_tile.set_value(startup_state, "是否随 Windows 自动启动")
        self.theme_tile.set_value(theme_name, "当前设置页和搜索窗的主视觉风格")
        self.screenshot_tile.set_value(
            screenshot_actions or "手动处理", "截图完成后的自动化动作"
        )
        self.hotkey_tile.set_value(hotkey_state, "录制后点击保存即可生效")
        self.workflow_tile.set_value(f"{workflow_count} 个", "可通过 wf / workflow 触发")
        self.plugin_tile.set_value(f"{enabled_plugins}/{total_plugins}", "已启用 / 全部插件")


class ScreenshotSavePreviewPanel(QWidget):
    token_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame(self)
        self.panel.setObjectName("ScreenshotSavePreviewPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("保存预览", self.panel)
        title.setObjectName("ScreenshotPreviewTitle")
        self.status_label = QLabel("", self.panel)
        self.status_label.setObjectName("ScreenshotPreviewStatus")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header.addWidget(title)
        header.addWidget(self.status_label, 1)
        panel_layout.addLayout(header)

        self.filename_label = QLabel("", self.panel)
        self.filename_label.setObjectName("ScreenshotPreviewFilename")
        self.filename_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        panel_layout.addWidget(self.filename_label)

        self.path_label = QLabel("", self.panel)
        self.path_label.setObjectName("ScreenshotPreviewPath")
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        panel_layout.addWidget(self.path_label)

        token_row = QHBoxLayout()
        token_row.setContentsMargins(0, 0, 0, 0)
        token_row.setSpacing(8)
        token_label = QLabel("插入变量", self.panel)
        token_label.setObjectName("ScreenshotPreviewTokenLabel")
        token_row.addWidget(token_label)
        for token in ("{date}", "{time}", "{datetime}"):
            button = QPushButton(token, self.panel)
            button.setObjectName("ScreenshotTokenButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, value=token: self.token_requested.emit(value)
            )
            token_row.addWidget(button)
        token_row.addStretch(1)
        panel_layout.addLayout(token_row)

        layout.addWidget(self.panel)
        self.setStyleSheet(
            """
            QFrame#ScreenshotSavePreviewPanel {
                background-color: rgba(47, 125, 255, 18);
                border: 1px solid rgba(47, 125, 255, 85);
                border-radius: 16px;
            }
            QLabel#ScreenshotPreviewTitle {
                color: #F5F8FF;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#ScreenshotPreviewStatus {
                color: rgba(235, 241, 250, 160);
                font-size: 12px;
            }
            QLabel#ScreenshotPreviewFilename {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: 700;
                padding: 8px 10px;
                border-radius: 10px;
                background-color: rgba(255, 255, 255, 14);
            }
            QLabel#ScreenshotPreviewPath,
            QLabel#ScreenshotPreviewTokenLabel {
                color: rgba(235, 241, 250, 150);
                font-size: 12px;
            }
            QPushButton#ScreenshotTokenButton {
                min-height: 26px;
                padding: 2px 10px;
                border-radius: 13px;
                border: 1px solid rgba(255, 255, 255, 55);
                background-color: rgba(255, 255, 255, 16);
                color: #EAF1FF;
                font-family: Consolas;
            }
            QPushButton#ScreenshotTokenButton:hover {
                background-color: rgba(47, 125, 255, 80);
                border-color: rgba(120, 180, 255, 140);
            }
            """
        )

    def set_state(self, auto_save, save_dir, template):
        filename = build_screenshot_filename_preview(template)
        save_dir = str(save_dir or "").strip()
        output_path = os.path.join(save_dir, filename) if save_dir else filename
        self.filename_label.setText(filename)
        self.path_label.setText(output_path)
        self.status_label.setText("自动保存开启" if auto_save else "仅手动保存")


class MetricTile(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("MetricTileTitle")
        self.value_label = QLabel("0.0 ms", self)
        self.value_label.setObjectName("MetricTileValue")
        self.desc_label = QLabel("p95 0.0 ms · 0 次", self)
        self.desc_label.setObjectName("MetricTileDesc")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.desc_label)

    def set_summary(self, summary):
        self.value_label.setText(f"{summary['last_ms']:.1f} ms")
        self.desc_label.setText(
            f"平均 {summary['avg_ms']:.1f} ms · "
            f"p95 {summary['p95_ms']:.1f} ms · {summary['count']} 次"
        )


class MetricsDashboardPanel(QWidget):
    METRICS = [
        ("startup.total", "启动总耗时"),
        ("search.global", "全局搜索"),
        ("search.inline_plugin", "命令直输"),
        ("ocr.inference", "OCR 识别"),
        ("screenshot.save", "截图保存"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        for index, (metric, title) in enumerate(self.METRICS):
            tile = MetricTile(title, self)
            self.tiles[metric] = tile
            layout.addWidget(tile, index // 2, index % 2)

        self.setStyleSheet(
            """
            QFrame#MetricTile {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(120, 130, 150, 70);
                border-radius: 14px;
            }
            QLabel#MetricTileTitle {
                color: rgba(235, 241, 250, 165);
                font-size: 12px;
            }
            QLabel#MetricTileValue {
                color: #F5F8FF;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#MetricTileDesc {
                color: rgba(235, 241, 250, 135);
                font-size: 11px;
            }
            """
        )

    def refresh(self):
        for metric, _title in self.METRICS:
            self.tiles[metric].set_summary(metrics_store.get_summary(metric))


class HotkeySummaryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame(self)
        self.panel.setObjectName("HotkeySummaryPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(16, 14, 16, 16)
        panel_layout.setSpacing(12)

        title = QLabel("快捷键看板", self.panel)
        title.setObjectName("HotkeySummaryTitle")
        subtitle = QLabel("录制结果会先显示在这里，保存后全局快捷键才会生效。", self.panel)
        subtitle.setObjectName("HotkeySummarySubtitle")
        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.tiles = {}
        for index, (action_key, title_text, description) in enumerate(HOTKEY_ACTIONS):
            tile = SettingsInfoTile(title_text, "未设置", description, self.panel)
            self.tiles[action_key] = tile
            grid.addWidget(tile, 0, index)
        panel_layout.addLayout(grid)

        layout.addWidget(self.panel)
        self.setStyleSheet(
            """
            QFrame#HotkeySummaryPanel {
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(32, 46, 58, 210),
                    stop: 1 rgba(14, 22, 31, 230)
                );
                border: 1px solid rgba(110, 150, 170, 85);
                border-radius: 18px;
            }
            QLabel#HotkeySummaryTitle {
                color: #F7FBFF;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#HotkeySummarySubtitle {
                color: rgba(232, 240, 248, 155);
                font-size: 12px;
            }
            QFrame#SettingsInfoTile {
                background-color: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 34);
                border-radius: 14px;
            }
            QLabel#SettingsInfoTileTitle {
                color: rgba(235, 241, 250, 165);
                font-size: 12px;
            }
            QLabel#SettingsInfoTileValue {
                color: #FFFFFF;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#SettingsInfoTileDesc {
                color: rgba(235, 241, 250, 140);
                font-size: 12px;
            }
            """
        )

    def set_hotkeys(self, hotkeys):
        for action_key, _title, description in HOTKEY_ACTIONS:
            tile = self.tiles.get(action_key)
            if tile is not None:
                tile.set_value(format_hotkey_display(hotkeys.get(action_key)), description)


class WorkflowStepCard(QFrame):
    changed = pyqtSignal()
    move_requested = pyqtSignal(object, int)
    delete_requested = pyqtSignal(object)

    def __init__(self, index, command="", pick="", parent=None):
        super().__init__(parent)
        self.setObjectName("WorkflowStepCard")

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        self.badge = QLabel(str(index), self)
        self.badge.setObjectName("WorkflowStepBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connector = QLabel("↓", self)
        self.connector.setObjectName("WorkflowStepConnector")
        self.connector.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.badge)
        left.addWidget(self.connector)
        left.addStretch(1)
        root.addLayout(left)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.title_label = QLabel("执行命令", self)
        self.title_label.setObjectName("WorkflowStepTitle")
        self.meta_label = QLabel("", self)
        self.meta_label.setObjectName("WorkflowStepMeta")
        self.meta_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        title_row.addWidget(self.title_label)
        title_row.addWidget(self.meta_label, 1)
        body.addLayout(title_row)

        self.command_edit = QLineEdit(self)
        self.command_edit.setPlaceholderText("例如：url {clipboard}")
        self.command_edit.setText(str(command or ""))
        body.addWidget(self.command_edit)

        pick_row = QHBoxLayout()
        pick_row.setContentsMargins(0, 0, 0, 0)
        pick_row.setSpacing(8)
        pick_label = QLabel("选择结果", self)
        pick_label.setObjectName("WorkflowStepFieldLabel")
        self.pick_edit = QLineEdit(self)
        self.pick_edit.setPlaceholderText("可选：按结果名称前缀匹配，例如 MD5")
        self.pick_edit.setText(str(pick or ""))
        pick_row.addWidget(pick_label)
        pick_row.addWidget(self.pick_edit, 1)
        body.addLayout(pick_row)
        root.addLayout(body, 1)

        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.up_btn = QPushButton("↑", self)
        self.down_btn = QPushButton("↓", self)
        self.delete_btn = QPushButton("删", self)
        for button in (self.up_btn, self.down_btn, self.delete_btn):
            button.setObjectName("WorkflowStepButton")
            button.setFixedSize(34, 28)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_btn.setObjectName("WorkflowStepDeleteButton")
        actions.addWidget(self.up_btn)
        actions.addWidget(self.down_btn)
        actions.addWidget(self.delete_btn)
        root.addLayout(actions)

        self.command_edit.textChanged.connect(self._on_changed)
        self.pick_edit.textChanged.connect(self._on_changed)
        self.up_btn.clicked.connect(lambda: self.move_requested.emit(self, -1))
        self.down_btn.clicked.connect(lambda: self.move_requested.emit(self, 1))
        self.delete_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        self._refresh_meta()

        self.setStyleSheet(
            """
            QFrame#WorkflowStepCard {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(120, 130, 150, 80);
                border-radius: 14px;
            }
            QLabel#WorkflowStepBadge {
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                border-radius: 15px;
                background-color: #2F7DFF;
                color: white;
                font-weight: 700;
            }
            QLabel#WorkflowStepConnector {
                color: rgba(47, 125, 255, 180);
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#WorkflowStepTitle {
                color: #F2F5FA;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#WorkflowStepMeta, QLabel#WorkflowStepFieldLabel {
                color: rgba(225, 231, 240, 165);
                font-size: 12px;
            }
            QLineEdit {
                min-height: 32px;
                padding: 4px 10px;
                border-radius: 8px;
                border: 1px solid rgba(130, 145, 170, 90);
                background-color: rgba(12, 16, 24, 120);
                color: #F4F7FB;
                selection-background-color: #2F7DFF;
            }
            QLineEdit:focus {
                border: 1px solid #4E95FF;
                background-color: rgba(18, 25, 38, 150);
            }
            QPushButton#WorkflowStepButton,
            QPushButton#WorkflowStepDeleteButton {
                border: 1px solid rgba(255, 255, 255, 38);
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 20);
                color: #E9EEF7;
                font-weight: 700;
            }
            QPushButton#WorkflowStepButton:hover {
                background-color: rgba(47, 125, 255, 80);
                border-color: rgba(96, 165, 255, 130);
            }
            QPushButton#WorkflowStepDeleteButton:hover {
                background-color: rgba(255, 75, 95, 90);
                border-color: rgba(255, 140, 150, 150);
            }
            """
        )

    def set_index(self, index, is_last=False):
        self.badge.setText(str(index))
        self.connector.setVisible(not is_last)

    def command(self):
        return self.command_edit.text().strip()

    def pick(self):
        return self.pick_edit.text().strip()

    def to_step(self):
        command = self.command()
        pick = self.pick()
        step = {"command": command}
        if pick:
            step["pick"] = pick
        return step

    def _on_changed(self):
        self._refresh_meta()
        self.changed.emit()

    def _refresh_meta(self):
        text = " ".join([self.command_edit.text(), self.pick_edit.text()])
        variables = sorted(set(extract_placeholders(text)))
        parts = []
        if variables:
            parts.append("变量 " + " ".join("{" + item + "}" for item in variables))
        parts.append("结果 " + (self.pick() or "自动取首项"))
        self.meta_label.setText("  ·  ".join(parts))


class WorkflowVisualEditor(QWidget):
    stepsChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.panel = QFrame(self)
        self.panel.setObjectName("WorkflowVisualPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("可视化步骤链", self.panel)
        title.setObjectName("WorkflowVisualTitle")
        subtitle = QLabel("每一步执行一个插件命令，输出会作为下一步的 {prev}", self.panel)
        subtitle.setObjectName("WorkflowVisualSubtitle")
        header_text = QVBoxLayout()
        header_text.setContentsMargins(0, 0, 0, 0)
        header_text.setSpacing(2)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header.addLayout(header_text, 1)

        self.add_btn = QPushButton("+ 添加步骤", self.panel)
        self.add_btn.setObjectName("WorkflowVisualPrimaryButton")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(lambda: self.add_step())
        header.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignRight)
        panel_layout.addLayout(header)

        self.empty_label = QLabel("还没有步骤，点击右上角添加第一步。", self.panel)
        self.empty_label.setObjectName("WorkflowVisualEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(76)
        panel_layout.addWidget(self.empty_label)

        self.rows_widget = QWidget(self.panel)
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        panel_layout.addWidget(self.rows_widget)
        layout.addWidget(self.panel)

        self.setStyleSheet(
            """
            QFrame#WorkflowVisualPanel {
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(32, 39, 54, 210),
                    stop: 1 rgba(17, 22, 32, 225)
                );
                border: 1px solid rgba(120, 140, 170, 80);
                border-radius: 18px;
            }
            QLabel#WorkflowVisualTitle {
                color: #F5F8FF;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#WorkflowVisualSubtitle {
                color: rgba(230, 236, 247, 165);
                font-size: 12px;
            }
            QLabel#WorkflowVisualEmpty {
                color: rgba(230, 236, 247, 145);
                border: 1px dashed rgba(160, 175, 205, 90);
                border-radius: 14px;
                background-color: rgba(255, 255, 255, 8);
            }
            QPushButton#WorkflowVisualPrimaryButton {
                min-height: 32px;
                padding: 4px 14px;
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 70);
                background-color: #2F7DFF;
                color: white;
                font-weight: 700;
            }
            QPushButton#WorkflowVisualPrimaryButton:hover {
                background-color: #4E95FF;
            }
            """
        )

    def set_steps(self, steps, emit=False):
        self._syncing = True
        try:
            self._clear_rows()
            if isinstance(steps, list):
                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    self.add_step(
                        step.get("command", ""),
                        step.get("pick", ""),
                        emit=False,
                    )
            self._refresh_rows()
        finally:
            self._syncing = False
        if emit:
            self.stepsChanged.emit()

    def add_step(self, command="", pick="", emit=True):
        row = WorkflowStepCard(len(self._rows) + 1, command, pick, self.rows_widget)
        row.changed.connect(self._on_row_changed)
        row.move_requested.connect(self._on_move_requested)
        row.delete_requested.connect(self._on_delete_requested)
        self._rows.append(row)
        self.rows_layout.addWidget(row)
        self._refresh_rows()
        if emit and not self._syncing:
            self.stepsChanged.emit()

    def steps(self):
        return [row.to_step() for row in self._rows if row.command()]

    def _clear_rows(self):
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = []

    def _refresh_rows(self):
        self.empty_label.setVisible(not self._rows)
        self.rows_widget.setVisible(bool(self._rows))
        total = len(self._rows)
        for index, row in enumerate(self._rows, start=1):
            row.set_index(index, is_last=index == total)
            row.up_btn.setEnabled(index > 1)
            row.down_btn.setEnabled(index < total)

    def _on_row_changed(self):
        if not self._syncing:
            self.stepsChanged.emit()

    def _on_move_requested(self, row, delta):
        try:
            index = self._rows.index(row)
        except ValueError:
            return

        new_index = index + delta
        if new_index < 0 or new_index >= len(self._rows):
            return

        self._rows[index], self._rows[new_index] = (
            self._rows[new_index],
            self._rows[index],
        )
        while self.rows_layout.count():
            self.rows_layout.takeAt(0)
        for item in self._rows:
            self.rows_layout.addWidget(item)
        self._refresh_rows()
        self.stepsChanged.emit()

    def _on_delete_requested(self, row):
        if row not in self._rows:
            return
        self._rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh_rows()
        self.stepsChanged.emit()


class SettingsWindow(FluentWindow):
    settings_changed = pyqtSignal()
    hotkeys_changed = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._syncing_theme_colors = False
        self._syncing_workflow_steps = False

        logo_path = self._resolve_resource_path("logo.png")
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        self.setWindowTitle("X-Tools 设置")
        self.setMinimumSize(960, 680)

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
        overview_group = SettingCardGroup("应用控制台", self.page_gen)
        self.settings_overview = SettingsOverviewPanel(self.page_gen.view)
        overview_layout = overview_group.layout()
        if overview_layout is not None:
            overview_layout.addWidget(self.settings_overview)
        self.page_gen.addGroup(overview_group)

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

        screenshot_group = SettingCardGroup("截图自动化", self.page_gen)

        self.screenshot_auto_copy_card = SwitchSettingCard(
            FI.COPY,
            "自动复制截图",
            "完成截图动作后自动写入剪贴板",
            parent=screenshot_group,
        )
        self.screenshot_auto_copy_card.checkedChanged.connect(
            lambda state: self.on_config_switch_changed("screenshot_auto_copy", state)
        )
        screenshot_group.addSettingCard(self.screenshot_auto_copy_card)

        self.screenshot_auto_pin_card = SwitchSettingCard(
            FI.PIN,
            "自动贴图",
            "完成截图动作后自动创建贴图窗口",
            parent=screenshot_group,
        )
        self.screenshot_auto_pin_card.checkedChanged.connect(
            lambda state: self.on_config_switch_changed("screenshot_auto_pin", state)
        )
        screenshot_group.addSettingCard(self.screenshot_auto_pin_card)

        self.screenshot_auto_save_card = SwitchSettingCard(
            FI.SAVE,
            "自动保存截图",
            "完成截图动作后自动保存 PNG 文件",
            parent=screenshot_group,
        )
        self.screenshot_auto_save_card.checkedChanged.connect(
            lambda state: self.on_config_switch_changed("screenshot_auto_save", state)
        )
        screenshot_group.addSettingCard(self.screenshot_auto_save_card)

        self.screenshot_dir_card = SettingCard(
            FI.FOLDER,
            "保存目录",
            "自动保存截图的输出目录",
            screenshot_group,
        )
        self.screenshot_dir_edit = QLineEdit(self.screenshot_dir_card)
        self.screenshot_dir_edit.setReadOnly(True)
        self.screenshot_dir_edit.setMinimumWidth(280)
        self.screenshot_dir_edit.setMaximumWidth(380)
        self.screenshot_dir_btn = QPushButton("选择")
        self.screenshot_dir_btn.clicked.connect(self.on_pick_screenshot_dir)
        self.screenshot_dir_card.hBoxLayout.addWidget(
            self.screenshot_dir_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_dir_card.hBoxLayout.addWidget(
            self.screenshot_dir_btn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_dir_card.hBoxLayout.addSpacing(16)
        screenshot_group.addSettingCard(self.screenshot_dir_card)

        self.screenshot_tpl_card = SettingCard(
            FI.TAG,
            "文件名模板",
            "支持 {date} {time} {datetime} 占位符",
            screenshot_group,
        )
        self.screenshot_tpl_edit = QLineEdit(self.screenshot_tpl_card)
        self.screenshot_tpl_edit.setMinimumWidth(220)
        self.screenshot_tpl_edit.setMaximumWidth(320)
        self.screenshot_tpl_edit.textChanged.connect(
            self.refresh_screenshot_save_preview
        )
        self.screenshot_tpl_save_btn = QPushButton("保存")
        self.screenshot_tpl_save_btn.clicked.connect(self.on_save_screenshot_template)
        self.screenshot_tpl_card.hBoxLayout.addWidget(
            self.screenshot_tpl_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_tpl_card.hBoxLayout.addWidget(
            self.screenshot_tpl_save_btn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_tpl_card.hBoxLayout.addSpacing(16)
        screenshot_group.addSettingCard(self.screenshot_tpl_card)

        screenshot_preview_group = SettingCardGroup("截图保存预览", self.page_gen)
        self.screenshot_save_preview = ScreenshotSavePreviewPanel(self.page_gen.view)
        self.screenshot_save_preview.token_requested.connect(
            self.insert_screenshot_template_token
        )
        screenshot_preview_layout = screenshot_preview_group.layout()
        if screenshot_preview_layout is not None:
            screenshot_preview_layout.addWidget(self.screenshot_save_preview)

        self.page_gen.addGroup(screenshot_group)
        self.page_gen.addGroup(screenshot_preview_group)
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

        preview_group = SettingCardGroup("实时预览", self.page_app)
        self.theme_preview = ThemePreviewPanel(self.page_app.view)
        preview_layout = preview_group.layout()
        if preview_layout is not None:
            preview_layout.addWidget(self.theme_preview)

        color_group = SettingCardGroup("颜色配置", self.page_app)
        self.theme_color_cards = {}
        for key, title, description in THEME_COLOR_FIELDS:
            card = ThemeColorCard(key, title, description, color_group)
            card.value_changed.connect(self.on_theme_color_changed)
            self.theme_color_cards[key] = card
            color_group.addSettingCard(card)

        theme_action_group = SettingCardGroup("操作", self.page_app)
        reset_theme_btn = PushSettingCard(
            "重置",
            FI.SYNC,
            "恢复当前主题默认色",
            "仅重置当前选中的主题，颜色会立即刷新",
            parent=theme_action_group,
        )
        reset_theme_btn.clicked.connect(self.on_reset_current_theme)
        theme_action_group.addSettingCard(reset_theme_btn)

        self.page_app.addGroup(app_group)
        self.page_app.addGroup(preview_group)
        self.page_app.addGroup(color_group)
        self.page_app.addGroup(theme_action_group)
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
                lambda state, name=plugin.get_name(): self.on_plugin_enabled_changed(
                    name, state
                )
            )
            plugins_group.addSettingCard(card)

        self.page_plugins.addGroup(plugins_group)
        self.page_plugins.addStretch()

        # ─── Page 3: Hotkeys ───
        self.page_hotkeys = ScrollWidget("快捷键", "page_hotkeys", self)
        hotkey_summary_group = SettingCardGroup("快捷键概览", self.page_hotkeys)
        self.hotkey_summary = HotkeySummaryPanel(self.page_hotkeys.view)
        hotkey_summary_layout = hotkey_summary_group.layout()
        if hotkey_summary_layout is not None:
            hotkey_summary_layout.addWidget(self.hotkey_summary)

        hotkeys_group = SettingCardGroup("全局操作快捷键", self.page_hotkeys)

        self._hotkey_cards = {}
        action_icons = {
            "toggle_window": FI.SEARCH,
            "screenshot": FI.PHOTO,
            "pin_clipboard": FI.PIN,
        }

        for action_key, label_text, _description in HOTKEY_ACTIONS:
            card = HotkeyRecordCard(
                label_text,
                action_key,
                self.config_manager,
                icon=action_icons.get(action_key, FI.COMMAND_PROMPT),
                parent=hotkeys_group,
            )
            card.hotkey_changed.connect(lambda _value: self.refresh_hotkey_summary())
            self._hotkey_cards[action_key] = card
            hotkeys_group.addSettingCard(card)

        self.page_hotkeys.addGroup(hotkey_summary_group)
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
            "回填初始快捷键，点击保存后生效",
            parent=action_group,
        )
        reset_btn.clicked.connect(self.on_reset_hotkeys)
        action_group.addSettingCard(reset_btn)

        self.page_hotkeys.addGroup(action_group)
        self.page_hotkeys.addStretch()

        # ─── Page 4: Workflows ───
        self.page_workflows = ScrollWidget("宏", "page_workflows", self)

        workflow_list_group = SettingCardGroup("工作流列表", self.page_workflows)

        self.workflow_selector_card = SettingCard(
            FI.ROBOT,
            "选择工作流",
            "从已有宏中选择并编辑",
            workflow_list_group,
        )
        self.workflow_selector = ComboBox(self.workflow_selector_card)
        self.workflow_selector.setMinimumWidth(220)
        self.workflow_selector.currentTextChanged.connect(self.on_workflow_selected)
        self.workflow_selector_card.hBoxLayout.addWidget(
            self.workflow_selector, 0, Qt.AlignmentFlag.AlignRight
        )

        self.workflow_new_btn = QPushButton("新建")
        self.workflow_new_btn.clicked.connect(self.on_new_workflow)
        self.workflow_selector_card.hBoxLayout.addWidget(
            self.workflow_new_btn, 0, Qt.AlignmentFlag.AlignRight
        )

        self.workflow_delete_btn = QPushButton("删除")
        self.workflow_delete_btn.clicked.connect(self.on_delete_workflow)
        self.workflow_selector_card.hBoxLayout.addWidget(
            self.workflow_delete_btn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_selector_card.hBoxLayout.addSpacing(16)
        workflow_list_group.addSettingCard(self.workflow_selector_card)

        workflow_form_group = SettingCardGroup("工作流编辑", self.page_workflows)

        self.workflow_id_card = SettingCard(
            FI.TAG,
            "ID",
            "仅支持小写字母、数字和连字符（-）",
            workflow_form_group,
        )
        self.workflow_id_edit = QLineEdit(self.workflow_id_card)
        self.workflow_id_edit.setMinimumWidth(280)
        self.workflow_id_edit.setMaximumWidth(420)
        self.workflow_id_card.hBoxLayout.addWidget(
            self.workflow_id_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_id_card.hBoxLayout.addSpacing(16)
        workflow_form_group.addSettingCard(self.workflow_id_card)

        self.workflow_name_card = SettingCard(
            FI.EDIT,
            "名称",
            "用于在搜索结果中显示",
            workflow_form_group,
        )
        self.workflow_name_edit = QLineEdit(self.workflow_name_card)
        self.workflow_name_edit.setMinimumWidth(280)
        self.workflow_name_edit.setMaximumWidth(420)
        self.workflow_name_card.hBoxLayout.addWidget(
            self.workflow_name_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_name_card.hBoxLayout.addSpacing(16)
        workflow_form_group.addSettingCard(self.workflow_name_card)

        self.workflow_desc_card = SettingCard(
            FI.INFO,
            "描述",
            "可选，帮助说明宏用途",
            workflow_form_group,
        )
        self.workflow_desc_edit = QLineEdit(self.workflow_desc_card)
        self.workflow_desc_edit.setMinimumWidth(280)
        self.workflow_desc_edit.setMaximumWidth(420)
        self.workflow_desc_card.hBoxLayout.addWidget(
            self.workflow_desc_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_desc_card.hBoxLayout.addSpacing(16)
        workflow_form_group.addSettingCard(self.workflow_desc_card)

        workflow_steps_group = SettingCardGroup("步骤可视化", self.page_workflows)
        self.workflow_visual_editor = WorkflowVisualEditor(self.page_workflows.view)
        self.workflow_visual_editor.stepsChanged.connect(
            self.on_workflow_visual_steps_changed
        )
        workflow_steps_layout = workflow_steps_group.layout()
        if workflow_steps_layout is not None:
            workflow_steps_layout.addWidget(self.workflow_visual_editor)

        workflow_steps_text_group = SettingCardGroup(
            "命令文本预览", self.page_workflows
        )
        self.workflow_steps_edit = PlainTextEdit(self.page_workflows.view)
        self.workflow_steps_edit.setPlaceholderText(
            "这里会实时生成兼容配置的 command | pick 文本"
        )
        self.workflow_steps_edit.setReadOnly(True)
        self.workflow_steps_edit.setMinimumHeight(96)
        self.workflow_steps_edit.setMaximumHeight(140)
        self.workflow_steps_edit.setStyleSheet("font-family: 'Consolas', monospace;")
        workflow_steps_text_layout = workflow_steps_text_group.layout()
        if workflow_steps_text_layout is not None:
            workflow_steps_text_layout.addWidget(self.workflow_steps_edit)

        workflow_actions_group = SettingCardGroup("操作", self.page_workflows)
        save_workflow_btn = PrimaryPushSettingCard(
            "保存",
            FI.SAVE,
            "保存当前宏",
            "保存后立即写入配置文件",
            parent=workflow_actions_group,
        )
        save_workflow_btn.clicked.connect(self.on_save_workflow)
        workflow_actions_group.addSettingCard(save_workflow_btn)

        self.page_workflows.addGroup(workflow_list_group)
        self.page_workflows.addGroup(workflow_form_group)
        self.page_workflows.addGroup(workflow_steps_group)
        self.page_workflows.addGroup(workflow_steps_text_group)
        self.page_workflows.addGroup(workflow_actions_group)
        self.page_workflows.addStretch()

        self._workflows_cache = []
        self._selected_workflow_id = ""
        self._syncing_workflow_selector = False

        # ─── Page 5: Diagnostics ───
        self.page_metrics = ScrollWidget("性能诊断", "page_metrics", self)
        metrics_group = SettingCardGroup("运行指标", self.page_metrics)

        self.metrics_dashboard = MetricsDashboardPanel(self.page_metrics.view)
        metrics_layout = metrics_group.layout()
        if metrics_layout is not None:
            metrics_layout.addWidget(self.metrics_dashboard)

        self.metrics_text = PlainTextEdit(self.page_metrics.view)
        self.metrics_text.setReadOnly(True)
        self.metrics_text.setMinimumHeight(300)
        self.metrics_text.setStyleSheet("font-family: 'Consolas', monospace;")
        if metrics_layout is not None:
            metrics_layout.addWidget(self.metrics_text)

        refresh_metrics_btn = PrimaryPushSettingCard(
            "刷新",
            FI.SYNC,
            "刷新统计数据",
            "查看启动、搜索、OCR 耗时分布",
            parent=metrics_group,
        )
        refresh_metrics_btn.clicked.connect(self.refresh_metrics)
        metrics_group.addSettingCard(refresh_metrics_btn)

        clear_metrics_btn = PushSettingCard(
            "清空",
            FI.CANCEL,
            "清空统计数据",
            "删除本地性能统计记录",
            parent=metrics_group,
        )
        clear_metrics_btn.clicked.connect(self.on_clear_metrics)
        metrics_group.addSettingCard(clear_metrics_btn)

        self.page_metrics.addGroup(metrics_group)
        self.page_metrics.addStretch()

        # ─── Add Interfaces ───
        self.addSubInterface(self.page_gen, FI.SETTING, "通用")
        self.addSubInterface(self.page_app, FI.BRUSH, "外观")
        self.addSubInterface(self.page_plugins, FI.APPLICATION, "插件")
        self.addSubInterface(self.page_hotkeys, FI.COMMAND_PROMPT, "快捷键")
        self.addSubInterface(self.page_workflows, FI.ROBOT, "宏")
        self.addSubInterface(self.page_metrics, FI.SYNC, "诊断")

    def load_settings(self):
        config = self.config_manager.config

        self.startup_check.setChecked(config.get("run_on_startup", False))
        self.screenshot_auto_copy_card.setChecked(
            config.get("screenshot_auto_copy", False)
        )
        self.screenshot_auto_pin_card.setChecked(
            config.get("screenshot_auto_pin", False)
        )
        self.screenshot_auto_save_card.setChecked(
            config.get("screenshot_auto_save", False)
        )
        self.screenshot_dir_edit.setText(
            config.get("screenshot_save_dir", os.path.expanduser("~"))
        )
        self.screenshot_tpl_edit.setText(
            config.get("screenshot_filename_template", "x-tools_{date}_{time}")
        )

        self.sync_theme_color_cards()
        self.load_workflow_settings()
        self.refresh_hotkey_summary()
        self.refresh_settings_overview()
        self.refresh_screenshot_save_preview()
        self.refresh_metrics()

    def on_config_switch_changed(self, key, state):
        self.config_manager.set_value(key, bool(state))
        if str(key).startswith("screenshot_"):
            self.refresh_screenshot_save_preview()
        self.refresh_settings_overview()

    def on_plugin_enabled_changed(self, plugin_name, state):
        from src.core.plugin_manager import plugin_manager

        plugin_manager.set_plugin_enabled(plugin_name, state)
        self.refresh_settings_overview()

    def _screenshot_action_summary(self, config=None):
        config = config or self.config_manager.config
        actions = []
        if config.get("screenshot_auto_copy", False):
            actions.append("复制")
        if config.get("screenshot_auto_pin", False):
            actions.append("贴图")
        if config.get("screenshot_auto_save", False):
            actions.append("保存")
        return " + ".join(actions)

    def refresh_settings_overview(self):
        from src.core.plugin_manager import plugin_manager

        plugins = plugin_manager.get_plugins(enabled_only=False)
        enabled_count = sum(
            1 for plugin in plugins if plugin_manager.is_plugin_enabled(plugin.get_name())
        )
        self.settings_overview.set_state(
            "已开启" if self.startup_check.isChecked() else "未开启",
            self._current_theme_name(),
            self._screenshot_action_summary(),
            self._hotkey_action_summary(),
            len(self.config_manager.get_workflows()),
            enabled_count,
            len(plugins),
        )

    def _current_hotkey_values(self):
        cards = getattr(self, "_hotkey_cards", {})
        if cards:
            return {
                action_key: card.get_hotkey()
                for action_key, card in cards.items()
            }
        return {
            action_key: self.config_manager.get_hotkey(action_key)
            for action_key, _title, _description in HOTKEY_ACTIONS
        }

    def _hotkey_action_summary(self):
        hotkeys = [value for value in self._current_hotkey_values().values() if value]
        duplicate_count = len(hotkeys) - len(set(hotkeys))
        configured_count = len(hotkeys)
        total_count = len(HOTKEY_ACTIONS)
        if duplicate_count:
            return f"{configured_count}/{total_count} 个，有冲突"
        return f"{configured_count}/{total_count} 个"

    def refresh_hotkey_summary(self):
        if hasattr(self, "hotkey_summary"):
            self.hotkey_summary.set_hotkeys(self._current_hotkey_values())
        if hasattr(self, "settings_overview"):
            self.refresh_settings_overview()

    def refresh_screenshot_save_preview(self):
        if not hasattr(self, "screenshot_save_preview"):
            return
        self.screenshot_save_preview.set_state(
            self.screenshot_auto_save_card.isChecked(),
            self.screenshot_dir_edit.text(),
            self.screenshot_tpl_edit.text(),
        )

    def insert_screenshot_template_token(self, token):
        self.screenshot_tpl_edit.insert(str(token))
        self.refresh_screenshot_save_preview()

    def on_pick_screenshot_dir(self):
        current = self.config_manager.get_value(
            "screenshot_save_dir", os.path.expanduser("~")
        )
        folder = QFileDialog.getExistingDirectory(self, "选择截图保存目录", current)
        if not folder:
            return
        self.screenshot_dir_edit.setText(folder)
        self.config_manager.set_value("screenshot_save_dir", folder)
        self.refresh_screenshot_save_preview()

    def on_save_screenshot_template(self):
        template = self.screenshot_tpl_edit.text().strip()
        if not template:
            QMessageBox.warning(self, "提示", "文件名模板不能为空")
            return
        self.config_manager.set_value("screenshot_filename_template", template)
        self.refresh_screenshot_save_preview()
        QMessageBox.information(self, "成功", "截图文件名模板已保存")

    def refresh_metrics(self):
        self.metrics_dashboard.refresh()
        text = metrics_store.format_summary(
            [
                "startup.total",
                "search.global",
                "search.inline_plugin",
                "ocr.inference",
                "screenshot.save",
            ]
        )
        self.metrics_text.setPlainText(text)

    def on_clear_metrics(self):
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确认清空所有性能统计数据吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            metrics_store.clear()
            self.refresh_metrics()

    def load_workflow_settings(self):
        self._workflows_cache = self.config_manager.get_workflows()
        workflow_ids = [str(w.get("id", "")).strip() for w in self._workflows_cache]

        self._syncing_workflow_selector = True
        self.workflow_selector.clear()
        self.workflow_selector.addItems([wid for wid in workflow_ids if wid])
        self._syncing_workflow_selector = False

        if workflow_ids:
            self.workflow_selector.setCurrentText(workflow_ids[0])
            self.on_workflow_selected(workflow_ids[0])
        else:
            self.on_new_workflow()

    def _set_workflow_steps(self, steps):
        self._syncing_workflow_steps = True
        try:
            self.workflow_visual_editor.set_steps(steps)
            self.workflow_steps_edit.setPlainText(format_workflow_steps_text(steps))
        finally:
            self._syncing_workflow_steps = False

    def on_workflow_visual_steps_changed(self):
        if self._syncing_workflow_steps:
            return
        self.workflow_steps_edit.setPlainText(
            format_workflow_steps_text(self.workflow_visual_editor.steps())
        )

    def on_workflow_selected(self, workflow_id):
        if self._syncing_workflow_selector:
            return

        workflow_id = str(workflow_id).strip()
        current = None
        for workflow in self._workflows_cache:
            if str(workflow.get("id", "")).strip() == workflow_id:
                current = workflow
                break

        if current is None:
            return

        self._selected_workflow_id = str(current.get("id", "")).strip()
        self.workflow_id_edit.setText(self._selected_workflow_id)
        self.workflow_name_edit.setText(str(current.get("name", "")).strip())
        self.workflow_desc_edit.setText(str(current.get("description", "")).strip())
        self._set_workflow_steps(current.get("steps", []))

    def on_new_workflow(self):
        self._selected_workflow_id = ""
        self.workflow_id_edit.clear()
        self.workflow_name_edit.clear()
        self.workflow_desc_edit.clear()
        self._set_workflow_steps([{"command": "", "pick": ""}])
        self.workflow_id_edit.setFocus()

    def on_delete_workflow(self):
        target_id = self._selected_workflow_id or str(
            self.workflow_selector.currentText()
        )
        target_id = str(target_id).strip()
        if not target_id:
            QMessageBox.warning(self, "提示", "请先选择要删除的宏")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除宏 '{target_id}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        workflows = self.config_manager.get_workflows()
        workflows = [
            w
            for w in workflows
            if str(w.get("id", "")).strip().lower() != target_id.lower()
        ]
        self.config_manager.set_workflows(workflows)
        self.load_workflow_settings()
        self.refresh_settings_overview()
        QMessageBox.information(self, "成功", "宏已删除")

    def on_save_workflow(self):
        workflow_id = self.workflow_id_edit.text().strip().lower()
        name = self.workflow_name_edit.text().strip()
        description = self.workflow_desc_edit.text().strip()
        steps = self.workflow_visual_editor.steps()

        if not validate_workflow_id(workflow_id):
            QMessageBox.warning(
                self, "提示", "宏 ID 格式无效，请使用小写字母、数字和连字符"
            )
            return
        if not name:
            QMessageBox.warning(self, "提示", "宏名称不能为空")
            return

        seen_ids = {
            str(w.get("id", "")).strip().lower()
            for w in self._workflows_cache
            if isinstance(w, dict)
        }
        selected_id = str(self._selected_workflow_id).strip().lower()
        if workflow_id in seen_ids and workflow_id != selected_id:
            QMessageBox.warning(self, "提示", f"宏 ID '{workflow_id}' 已存在")
            return

        cleaned_steps = []
        for index, step in enumerate(steps, start=1):
            command = str(step.get("command", "")).strip()
            pick = str(step.get("pick", "")).strip()
            if not command:
                continue

            unsupported = sorted(
                set(find_unknown_placeholders(command, ALLOWED_WORKFLOW_VARS)).union(
                    find_unknown_placeholders(pick, ALLOWED_WORKFLOW_VARS)
                )
            )
            if unsupported:
                bad = ", ".join("{" + v + "}" for v in unsupported)
                QMessageBox.warning(
                    self,
                    "提示",
                    f"第 {index} 步包含不支持的变量: {bad}\n仅允许 {{clipboard}} / {{prev}} / {{input}}",
                )
                return

            step_payload = {"command": command}
            if pick:
                step_payload["pick"] = pick
            cleaned_steps.append(step_payload)

        if not cleaned_steps:
            QMessageBox.warning(self, "提示", "至少需要一条有效步骤")
            return

        payload = {
            "id": workflow_id,
            "name": name,
            "description": description,
            "steps": cleaned_steps,
        }

        workflows = self.config_manager.get_workflows()
        replaced = False
        for i, item in enumerate(workflows):
            current_id = str(item.get("id", "")).strip().lower()
            if current_id == selected_id:
                workflows[i] = payload
                replaced = True
                break

        if not replaced:
            workflows.append(payload)

        self.config_manager.set_workflows(workflows)
        self.load_workflow_settings()
        self.workflow_selector.setCurrentText(workflow_id)
        self.on_workflow_selected(workflow_id)
        self.refresh_settings_overview()
        QMessageBox.information(self, "成功", "宏已保存")

    def _current_theme_name(self):
        theme_name = str(self.theme_combo.currentText()).strip()
        return theme_name or self.config_manager.get_theme_name()

    def _theme_fallbacks(self, theme_name):
        from src.core.config import DEFAULT_THEMES

        return DEFAULT_THEMES.get(theme_name, DEFAULT_THEMES.get("Dark", {}))

    def _current_theme(self):
        theme_name = self._current_theme_name()
        fallback = self._theme_fallbacks(theme_name)
        theme = self.config_manager.themes.setdefault(theme_name, fallback.copy())
        for key, value in fallback.items():
            theme.setdefault(key, value)
        return theme

    def sync_theme_color_cards(self):
        theme = self._current_theme()
        self._syncing_theme_colors = True
        try:
            for key, _title, _description in THEME_COLOR_FIELDS:
                card = self.theme_color_cards.get(key)
                if card is not None:
                    fallback = self._theme_fallbacks("Dark").get(key, "#FFFFFF")
                    card.set_value(theme.get(key, fallback))
        finally:
            self._syncing_theme_colors = False
        self.theme_preview.apply_theme(theme)

    def _is_current_theme_dark(self):
        theme_name = self._current_theme_name()
        if theme_name == "Dark":
            return True
        if theme_name == "Light":
            return False

        color = QColor(
            normalize_theme_color(self._current_theme().get("window_bg"), "#FFFFFF")
        )
        return color.isValid() and color.lightness() < 128

    def on_theme_changed(self, text):
        if not text:
            return

        self.config_manager.config["theme"] = text
        self.config_manager.save_config()
        self.windowEffect.setMicaEffect(
            self.winId(), isDarkMode=self._is_current_theme_dark()
        )
        self.sync_theme_color_cards()
        self.refresh_settings_overview()
        self.settings_changed.emit()

    def on_theme_color_changed(self, key, value):
        if self._syncing_theme_colors:
            return

        theme = self._current_theme()
        theme[key] = normalize_theme_color(value, theme.get(key, "#FFFFFF"))
        self.config_manager.save_themes()
        self.theme_preview.apply_theme(theme)
        self.windowEffect.setMicaEffect(
            self.winId(), isDarkMode=self._is_current_theme_dark()
        )
        self.settings_changed.emit()

    def on_reset_current_theme(self):
        from src.core.config import DEFAULT_THEMES

        theme_name = self._current_theme_name()
        if theme_name not in DEFAULT_THEMES:
            QMessageBox.information(self, "提示", "当前是自定义主题，没有内置默认色可恢复。")
            return

        self.config_manager.themes[theme_name] = DEFAULT_THEMES[theme_name].copy()
        self.config_manager.save_themes()
        self.sync_theme_color_cards()
        self.refresh_settings_overview()
        self.settings_changed.emit()

    def on_startup_changed(self, state):
        success = self.config_manager.set_startup(state)
        if not success:
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(not state)
            self.startup_check.blockSignals(False)
        self.refresh_settings_overview()

    def on_save_themes(self):
        self.config_manager.save_themes()
        self.settings_changed.emit()

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

        self.refresh_hotkey_summary()
        self.hotkeys_changed.emit()
        QMessageBox.information(self, "成功", "快捷键已保存并生效。")

    def on_reset_hotkeys(self):
        from src.core.config import DEFAULT_HOTKEYS

        for action_key, card in self._hotkey_cards.items():
            default_val = DEFAULT_HOTKEYS.get(action_key, "")
            card.set_hotkey(default_val)
        self.refresh_hotkey_summary()
