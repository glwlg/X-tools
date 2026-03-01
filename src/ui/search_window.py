import sys
import os
import threading
import ctypes
import json
import time
import difflib
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QEvent, QTimer, QSettings, QPoint
from PyQt6.QtGui import QAction, QIcon, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QListWidgetItem,
    QSystemTrayIcon,
    QMenu,
    QGraphicsDropShadowEffect,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)
from qfluentwidgets import SearchLineEdit, ListWidget, setTheme, Theme, isDarkTheme
from qframelesswindow import AcrylicWindow

from src.core.everything import everything_client
from src.core.app_scanner import app_scanner
from src.core.config import config_manager
from src.ui.settings_window import SettingsWindow
from src.core.plugin_manager import plugin_manager
from src.ui.screenshot_overlay import ScreenshotOverlay
from src.ui.pinned_image_window import PinnedImageWindow
from src.core.hotkey_manager import HotkeyManager
from src.ui.network_monitor import NetworkMonitorWidget
from src.core.clipboard_history import clipboard_history_manager
from src.core.logger import get_logger, export_diagnostics, get_log_dir
from src.core.metrics import metrics_store


logger = get_logger(__name__)


class SearchThread(QThread):
    results_found = pyqtSignal(int, str, list)

    def __init__(self, query, request_id):
        super().__init__()
        self.query = query
        self.request_id = request_id

    def run(self):
        app_results = app_scanner.search(self.query)
        file_results = []
        if everything_client:
            file_results = everything_client.search(self.query)
        results = app_results + file_results
        self.results_found.emit(self.request_id, self.query, results)


class SearchWindow(AcrylicWindow):
    toggle_signal = pyqtSignal()
    screenshot_signal = pyqtSignal()
    pin_clipboard_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.plugin_mode = None
        self.network_monitor = None
        self._has_positioned_once = False
        self._needs_initial_render_sync = True
        self._search_request_id = 0
        self._pending_query = ""
        self._search_started_at = {}
        self._search_query_snapshot = {}
        self._search_drag_candidate = False
        self._search_dragging_window = False
        self._search_drag_start_global = QPoint()
        self._search_drag_start_pos = QPoint()

        self.logo_path = self.resolve_resource_path("logo.png")

        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.titleBar.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.init_ui()
        self.init_tray()
        self.init_hotkey()

        self.toggle_signal.connect(self.toggle_visibility)
        self.screenshot_signal.connect(self.trigger_screenshot)
        self.pin_clipboard_signal.connect(self.pin_clipboard)
        self.screenshot_overlay = None
        self._pinned_windows = []

        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(120)
        self._search_debounce_timer.timeout.connect(self._perform_debounced_search)

        self._usage_settings = QSettings("x-tools", "search_usage")
        self._usage_counter = {}
        self._favorites = set()
        self._load_usage_data()

        self._command_settings = QSettings("x-tools", "command_memory")
        self._command_history = []
        self._plugin_last_args = {}
        self._load_command_memory()

        self.clipboard_history = clipboard_history_manager
        self.clipboard_history.start(QApplication.clipboard())

        threading.Thread(target=app_scanner.scan, daemon=True).start()

    def _load_usage_data(self):
        raw = self._usage_settings.value("data", defaultValue="")
        data = {}
        if isinstance(raw, str) and raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        elif isinstance(raw, dict):
            data = raw

        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        favorites = data.get("favorites", []) if isinstance(data, dict) else []

        if isinstance(usage, dict):
            self._usage_counter = {
                str(k): int(v) for k, v in usage.items() if isinstance(v, (int, float))
            }
        else:
            self._usage_counter = {}

        if isinstance(favorites, list):
            self._favorites = {str(i) for i in favorites}
        else:
            self._favorites = set()

    def _save_usage_data(self):
        payload = {
            "usage": self._usage_counter,
            "favorites": sorted(self._favorites),
        }
        self._usage_settings.setValue("data", json.dumps(payload, ensure_ascii=False))

    def _load_command_memory(self):
        raw = self._command_settings.value("data", defaultValue="")
        data = {}

        if isinstance(raw, str) and raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        elif isinstance(raw, dict):
            data = raw

        history = data.get("history", []) if isinstance(data, dict) else []
        last_args = data.get("last_args", {}) if isinstance(data, dict) else {}

        if isinstance(history, list):
            self._command_history = [str(i).strip() for i in history if str(i).strip()][
                :80
            ]
        else:
            self._command_history = []

        if isinstance(last_args, dict):
            self._plugin_last_args = {
                str(k): str(v) for k, v in last_args.items() if str(v).strip()
            }
        else:
            self._plugin_last_args = {}

    def _save_command_memory(self):
        payload = {
            "history": self._command_history[:80],
            "last_args": self._plugin_last_args,
        }
        self._command_settings.setValue("data", json.dumps(payload, ensure_ascii=False))

    def _record_command_usage(self, raw_query, plugin=None, plugin_query=""):
        command = str(raw_query).strip()
        if not command:
            return

        self._command_history = [cmd for cmd in self._command_history if cmd != command]
        self._command_history.insert(0, command)
        self._command_history = self._command_history[:80]

        if plugin is not None and str(plugin_query).strip():
            try:
                self._plugin_last_args[plugin.get_name()] = str(plugin_query).strip()
            except Exception:
                pass

        self._save_command_memory()

    @staticmethod
    def _normalize_keywords(plugin):
        return [str(k).strip().lower() for k in plugin.get_keywords() if str(k).strip()]

    def _item_key(self, data):
        if not isinstance(data, dict):
            return ""

        item_type = str(data.get("type", "")).strip().lower()
        path = data.get("path")

        if path:
            return f"{item_type}:{str(path).strip().lower()}"

        plugin = data.get("plugin")
        if item_type == "plugin_trigger" and plugin is not None:
            try:
                return f"plugin:{plugin.get_name().strip().lower()}"
            except Exception:
                return ""

        name = str(data.get("name", "")).strip().lower()
        if name:
            return f"{item_type}:{name}"

        return ""

    def _record_item_usage(self, data):
        key = self._item_key(data)
        if not key:
            return

        self._usage_counter[key] = int(self._usage_counter.get(key, 0)) + 1
        self._save_usage_data()

    def _is_favorite(self, data):
        key = self._item_key(data)
        return bool(key) and key in self._favorites

    def _toggle_favorite_by_key(self, key):
        if not key:
            return
        if key in self._favorites:
            self._favorites.remove(key)
        else:
            self._favorites.add(key)
        self._save_usage_data()
        if self.search_bar.text().strip():
            self.on_search_query(self.search_bar.text())

    def _result_sort_key(self, item):
        key = self._item_key(item)
        fav = 0 if key and key in self._favorites else 1
        usage = -int(self._usage_counter.get(key, 0)) if key else 0
        name = str(item.get("name", "")).lower()
        return (fav, usage, name)

    def _find_plugin_by_keyword(self, keyword):
        word = keyword.strip().lower()
        if not word:
            return None

        for plugin in plugin_manager.get_plugins(enabled_only=True):
            if word in self._normalize_keywords(plugin):
                return plugin
        return None

    def _parse_inline_plugin_command(self, text):
        parts = text.strip().split(None, 1)
        if len(parts) < 2:
            return None, ""

        plugin = self._find_plugin_by_keyword(parts[0])
        if not plugin:
            return None, ""

        return plugin, parts[1].strip()

    @staticmethod
    def _first_keyword(plugin):
        keywords = plugin.get_keywords()
        if not keywords:
            return ""
        return str(keywords[0]).strip().lower()

    @staticmethod
    def _schema_from_plugin(plugin):
        schema = (
            plugin.get_command_schema() if hasattr(plugin, "get_command_schema") else {}
        )
        if not isinstance(schema, dict):
            schema = {}
        schema.setdefault("usage", "")
        schema.setdefault("examples", [])
        schema.setdefault("params", [])
        return schema

    def _format_schema_text(self, plugin):
        schema = self._schema_from_plugin(plugin)
        lines = [f"插件: {plugin.get_name()}", plugin.get_description(), ""]

        usage = str(schema.get("usage", "")).strip()
        if usage:
            lines.append(f"用法: {usage}")

        params = schema.get("params", [])
        if isinstance(params, list) and params:
            lines.append("参数:")
            for param in params:
                if not isinstance(param, dict):
                    continue
                label = str(param.get("label") or param.get("name") or "参数")
                placeholder = str(param.get("placeholder", "")).strip()
                required = "必填" if bool(param.get("required", False)) else "可选"
                if placeholder:
                    lines.append(f"- {label} ({required}): {placeholder}")
                else:
                    lines.append(f"- {label} ({required})")

        examples = schema.get("examples", [])
        if isinstance(examples, list) and examples:
            lines.append("示例:")
            for example in examples[:6]:
                lines.append(f"- {example}")

        return "\n".join(lines).strip()

    def _build_command_hint_items(self, text):
        value = text.lower()
        stripped = value.strip()
        if not stripped:
            return []

        items = []
        seen_templates = set()

        head, _, tail = value.partition(" ")

        has_space = " " in value

        if not has_space and len(stripped) >= 2:
            for command in self._command_history[:24]:
                cmd_lower = command.lower()
                if stripped in cmd_lower or cmd_lower.startswith(stripped):
                    items.append(
                        {
                            "type": "command_recent",
                            "name": f"最近: {command}",
                            "path": command,
                            "hint": "历史命令",
                        }
                    )
                    break

        for plugin in plugin_manager.get_plugins(enabled_only=True):
            keywords = self._normalize_keywords(plugin)
            if not keywords:
                continue

            first = self._first_keyword(plugin)
            schema = self._schema_from_plugin(plugin)

            if not has_space:
                keyword_match = None
                for keyword in keywords:
                    if keyword.startswith(stripped) or stripped in keyword:
                        keyword_match = keyword
                        break

                if keyword_match:
                    template = f"{keyword_match} "
                    if template not in seen_templates:
                        seen_templates.add(template)
                        items.append(
                            {
                                "type": "command_hint",
                                "name": f"命令: {keyword_match}",
                                "path": template,
                                "hint": plugin.get_description(),
                                "plugin": plugin,
                            }
                        )
            elif head.strip() in keywords and (not tail.strip()):
                if first:
                    form_key = f"form:{plugin.get_name()}"
                    if form_key not in seen_templates:
                        seen_templates.add(form_key)
                        items.append(
                            {
                                "type": "command_form",
                                "name": f"参数面板: {plugin.get_name()}",
                                "path": form_key,
                                "hint": "通过表单自动生成命令",
                                "plugin": plugin,
                            }
                        )

                examples = schema.get("examples", [])
                if isinstance(examples, list):
                    for example in examples:
                        if not isinstance(example, str):
                            continue
                        if example in seen_templates:
                            continue
                        seen_templates.add(example)
                        items.append(
                            {
                                "type": "command_template",
                                "name": f"示例: {example}",
                                "path": example,
                                "hint": plugin.get_name(),
                                "plugin": plugin,
                            }
                        )
                        break

        if not has_space and len(stripped) >= 3:
            keyword_pool = []
            for plugin in plugin_manager.get_plugins(enabled_only=True):
                keyword_pool.extend(self._normalize_keywords(plugin))

            unique_keywords = sorted(set(keyword_pool))
            if stripped not in unique_keywords:
                corrections = difflib.get_close_matches(
                    stripped, unique_keywords, n=1, cutoff=0.72
                )
                for kw in corrections:
                    template = f"{kw} "
                    if template in seen_templates:
                        continue
                    seen_templates.add(template)
                    items.append(
                        {
                            "type": "command_correction",
                            "name": f"纠正: {kw}",
                            "path": template,
                            "hint": "拼写纠正",
                        }
                    )

        return items[:4]

    def _preview_text_for_item(self, data):
        if not isinstance(data, dict):
            return ""

        item_type = data.get("type", "")
        plugin = data.get("plugin")

        if item_type in {"command_hint", "command_template", "command_form"} and plugin:
            return self._format_schema_text(plugin)

        if item_type in {"command_recent", "command_correction"}:
            return f"命令建议:\n{data.get('path', '')}"

        if item_type == "plugin_trigger" and plugin:
            return self._format_schema_text(plugin)

        if item_type == "workflow_run":
            return str(data.get("workflow_desc", "执行预设工作流"))

        if item_type in {"clipboard_entry", "clipboard_center", "clipboard_cmd"}:
            if item_type == "clipboard_entry":
                if data.get("clipboard_type") == "text":
                    return str(data.get("clipboard_text", ""))
                image_path = str(data.get("clipboard_image_path", ""))
                size = str(data.get("clipboard_size", ""))
                return f"剪贴板图片\n尺寸: {size}\n路径: {image_path}"

            if item_type == "clipboard_center":
                return "打开剪贴板历史中心，可搜索、置顶、删除并复用历史内容。"

            return "清空所有未置顶的剪贴板历史记录。"

        if item_type in {"copy_result", "calc_result", "calc_error", "error"}:
            value = str(data.get("path", "")).strip()
            if value:
                return value
            return str(data.get("name", ""))

        if item_type == "sys_cmd":
            cmd = str(data.get("path", ""))
            warn = "\n\n注意: shutdown/restart 为高风险命令，会二次确认。"
            return f"系统命令: {cmd}{warn}"

        if item_type in {"file", "app"}:
            path = str(data.get("path", ""))
            lines = [f"名称: {data.get('name', '')}", f"路径: {path}"]

            if path and os.path.isfile(path):
                try:
                    size = os.path.getsize(path)
                    lines.append(f"大小: {size} bytes")
                except Exception:
                    pass

                ext = os.path.splitext(path)[1].lower()
                if ext in {
                    ".txt",
                    ".md",
                    ".json",
                    ".py",
                    ".log",
                    ".ini",
                    ".yaml",
                    ".yml",
                    ".toml",
                }:
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            preview = f.read(2000).strip()
                        if preview:
                            lines.append("\n文件预览:\n" + preview)
                    except Exception:
                        pass
            return "\n".join(lines).strip()

        if item_type == "hosts_cmd":
            return "打开 Hosts 管理中心，可编辑方案、拉取远程配置并应用到系统。"

        if item_type == "qr_generate":
            return f"将根据以下内容生成二维码:\n{data.get('path', '')}"

        return str(data.get("name", ""))

    def on_result_item_changed(self, current, previous):
        del previous
        if current is None:
            self.preview_text.clear()
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        self.preview_text.setPlainText(self._preview_text_for_item(data))

    def _show_plugin_form_dialog(self, plugin):
        schema = self._schema_from_plugin(plugin)
        params = schema.get("params", [])
        if not isinstance(params, list) or not params:
            keyword = self._first_keyword(plugin)
            if keyword:
                self.search_bar.setText(f"{keyword} ")
                self.search_bar.setFocus()
                self.search_bar.end(False)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{plugin.get_name()} 参数输入")
        dialog.setMinimumWidth(420)

        root_layout = QVBoxLayout(dialog)
        form = QFormLayout()
        editors = []

        for param in params:
            if not isinstance(param, dict):
                continue
            label = str(param.get("label") or param.get("name") or "参数")
            placeholder = str(param.get("placeholder", ""))
            default = str(param.get("default", ""))

            editor = QLineEdit(dialog)
            editor.setPlaceholderText(placeholder)
            editor.setText(default)
            form.addRow(label, editor)
            editors.append((param, editor))

        last_arg = self._plugin_last_args.get(plugin.get_name(), "")
        if last_arg and editors:
            editors[0][1].setText(last_arg)

        root_layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        root_layout.addWidget(button_box)

        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        arg_values = []
        for param, editor in editors:
            value = editor.text().strip()
            if bool(param.get("required", False)) and not value:
                QMessageBox.warning(
                    self, "参数缺失", f"参数 '{param.get('label', '参数')}' 为必填"
                )
                return
            if value:
                arg_values.append(value)

        keyword = self._first_keyword(plugin)
        command = keyword
        if arg_values:
            command = f"{keyword} {' '.join(arg_values)}"

        self.search_bar.setText(command)
        self.search_bar.setFocus()
        self.search_bar.end(False)

    def resolve_resource_path(self, filename):
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
            possible_paths = [
                os.path.join(base_path, filename),
                os.path.join(base_path, "_internal", filename),
            ]
        else:
            possible_paths = [os.path.join(os.getcwd(), filename)]
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return None

    def init_ui(self):
        self.container = QWidget(self)
        self.container.setObjectName("searchContainer")

        # Frame our custom container inside the window without the titlebar gap
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        self._apply_fluent_theme()

        if self.logo_path:
            self.setWindowIcon(QIcon(self.logo_path))

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.search_bar = SearchLineEdit()
        self.search_bar.setPlaceholderText("唤起各类高级工具、本地搜索与系统功能...")
        self.search_bar.setFixedHeight(48)
        self.search_bar.textChanged.connect(self.on_search_query)
        self.search_bar.returnPressed.connect(self.on_enter_pressed)
        self.search_bar.installEventFilter(self)
        self.search_bar.clearButton.setStyleSheet("QToolButton { border-radius: 4px; }")

        self._style_search_bar()
        layout.addWidget(self.search_bar)

        self.result_list = ListWidget()
        self.result_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.result_list.itemClicked.connect(self.on_item_clicked)
        self.result_list.currentItemChanged.connect(self.on_result_item_changed)
        self._style_result_list()

        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(10, 4, 0, 4)
        preview_layout.setSpacing(6)

        self.preview_title = QLabel("结果预览")
        self.preview_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        preview_layout.addWidget(self.preview_title)

        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("选中结果后显示详细预览")
        self.preview_text.setObjectName("previewText")
        self.preview_text.setStyleSheet(
            "QPlainTextEdit#previewText { border-radius: 8px; padding: 8px; }"
        )
        preview_layout.addWidget(self.preview_text)

        self.results_container = QWidget()
        results_layout = QHBoxLayout(self.results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(8)
        results_layout.addWidget(self.result_list, 3)
        results_layout.addWidget(self.preview_panel, 2)

        self.results_container.hide()
        layout.addWidget(self.results_container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 50))
        self.container.setGraphicsEffect(shadow)

    def _apply_fluent_theme(self):
        theme_name = config_manager.get_theme_name()
        if theme_name == "Dark":
            setTheme(Theme.DARK)
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=True)
            self.setStyleSheet(
                "#searchContainer { background-color: rgba(30, 30, 34, 180); border-radius: 12px; }"
            )
        else:
            setTheme(Theme.LIGHT)
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=False)
            self.setStyleSheet(
                "#searchContainer { background-color: rgba(250, 250, 252, 220); border-radius: 12px; }"
            )

    def _style_search_bar(self):
        # Rely primarily on qfluentwidgets native drawing, just increase font size and remove border artifacts
        self.search_bar.setStyleSheet("""
            SearchLineEdit {
                font-size: 18px;
                border: none;
                background: transparent;
                border-bottom: none;
            }
            SearchLineEdit:focus {
                border: none;
                background: transparent;
                border-bottom: none;
            }
        """)

    def _style_result_list(self):
        dark = isDarkTheme()
        if dark:
            qss = """
                ListWidget {
                    background-color: transparent; border: none; outline: none;
                }
                ListWidget::item {
                    padding: 12px 16px;
                    border-radius: 8px;
                    color: #E2E4EB;
                    font-size: 15px;
                }
                ListWidget::item:selected {
                    background-color: rgba(76, 194, 255, 45);
                    color: #FFFFFF;
                }
                ListWidget::item:hover:!selected {
                    background-color: rgba(255, 255, 255, 15);
                }
            """
            preview_qss = (
                "QPlainTextEdit#previewText {"
                "background-color: rgba(255,255,255,18);"
                "color: #E2E4EB;"
                "border: 1px solid rgba(255,255,255,22);"
                "}"
            )
            title_qss = "color: #E2E4EB; font-size: 13px; font-weight: bold;"
        else:
            qss = """
                ListWidget {
                    background-color: transparent; border: none; outline: none;
                }
                ListWidget::item {
                    padding: 12px 16px;
                    border-radius: 8px;
                    color: #2C2C3A;
                    font-size: 15px;
                }
                ListWidget::item:selected {
                    background-color: rgba(68, 85, 238, 35);
                    color: #1A1A2E;
                }
                ListWidget::item:hover:!selected {
                    background-color: rgba(0, 0, 0, 10);
                }
            """
            preview_qss = (
                "QPlainTextEdit#previewText {"
                "background-color: rgba(255,255,255,176);"
                "color: #2C2C3A;"
                "border: 1px solid rgba(0,0,0,12);"
                "}"
            )
            title_qss = "color: #2C2C3A; font-size: 13px; font-weight: bold;"
        self.result_list.setStyleSheet(qss)
        if hasattr(self, "preview_text"):
            self.preview_text.setStyleSheet(preview_qss)
        if hasattr(self, "preview_title"):
            self.preview_title.setStyleSheet(title_qss)

    def update_style(self):
        self._apply_fluent_theme()
        self._style_search_bar()
        self._style_result_list()

        effect = self.container.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setColor(
                QColor(0, 0, 0, 80) if isDarkTheme() else QColor(0, 0, 0, 40)
            )

    def eventFilter(self, obj, event):
        if obj == self.search_bar:
            et = event.type()

            if et == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Down:
                    self.navigate_list(1)
                    return True
                elif key == Qt.Key.Key_Up:
                    self.navigate_list(-1)
                    return True

            elif et == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._search_drag_candidate = True
                    self._search_dragging_window = False
                    self._search_drag_start_global = event.globalPosition().toPoint()
                    self._search_drag_start_pos = self.frameGeometry().topLeft()

            elif et == QEvent.Type.MouseMove:
                if self._search_drag_candidate and (
                    event.buttons() & Qt.MouseButton.LeftButton
                ):
                    delta = (
                        event.globalPosition().toPoint()
                        - self._search_drag_start_global
                    )
                    if (
                        not self._search_dragging_window
                        and delta.manhattanLength() >= QApplication.startDragDistance()
                    ):
                        self._search_dragging_window = True
                        self.search_bar.setCursor(Qt.CursorShape.SizeAllCursor)

                    if self._search_dragging_window:
                        self.move(self._search_drag_start_pos + delta)
                        self._has_positioned_once = True
                        return True

            elif et == QEvent.Type.MouseButtonRelease:
                was_dragging = self._search_dragging_window
                self._search_drag_candidate = False
                self._search_dragging_window = False
                if was_dragging:
                    self.search_bar.setCursor(Qt.CursorShape.IBeamCursor)
                    return True
                self.search_bar.setCursor(Qt.CursorShape.IBeamCursor)

            elif et == QEvent.Type.Leave:
                self._search_drag_candidate = False
                self._search_dragging_window = False
                self.search_bar.setCursor(Qt.CursorShape.IBeamCursor)

        return super().eventFilter(obj, event)

    def navigate_list(self, direction):
        count = self.result_list.count()
        if count == 0:
            return
        next_row = self.result_list.currentRow() + direction
        if next_row < 0:
            next_row = 0
        elif next_row >= count:
            next_row = count - 1
        self.result_list.setCurrentRow(next_row)

    def center_window(self):
        screen_obj = QApplication.primaryScreen()
        if screen_obj is None:
            return
        screen = screen_obj.geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - 600) // 4
        self.move(x, y)

    def adjust_size(self, expanded=True):
        if expanded:
            width = 980
            screen_obj = QApplication.primaryScreen()
            if screen_obj is not None:
                screen_w = screen_obj.geometry().width()
                width = min(980, max(760, screen_w - 80))
            self.setFixedSize(width, 560)
            self.results_container.show()
        else:
            self.setFixedSize(700, 86)
            self.results_container.hide()

    def _sync_initial_render_rect(self):
        width, height = self.width(), self.height()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.resize(width, height + 1)
        self.setFixedSize(width, height)
        self.windowEffect.setMicaEffect(self.winId(), isDarkMode=isDarkTheme())

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = (
            QIcon(self.logo_path)
            if self.logo_path
            else self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        )
        self.tray_icon.setIcon(icon)

        menu = QMenu()

        self.monitor_action = QAction("网络监控", self)
        self.monitor_action.setCheckable(True)
        self.monitor_action.triggered.connect(self.toggle_network_monitor)
        menu.addAction(self.monitor_action)
        menu.addSeparator()

        export_logs_action = QAction("导出诊断日志", self)
        export_logs_action.triggered.connect(self.export_diagnostics_package)
        menu.addAction(export_logs_action)

        open_log_dir_action = QAction("打开日志目录", self)
        open_log_dir_action.triggered.connect(self.open_log_directory)
        menu.addAction(open_log_dir_action)
        menu.addSeparator()

        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        quit_action = QAction("退出", self)
        app = QApplication.instance()
        if app is not None:
            quit_action.triggered.connect(app.quit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

        # Load network monitor state
        settings = QSettings("x-tools", "network_monitor")
        is_visible = settings.value("is_visible", type=bool, defaultValue=False)
        if is_visible:
            self.monitor_action.setChecked(True)
            self.toggle_network_monitor(True)

    def toggle_network_monitor(self, checked):
        if not self.network_monitor:
            self.network_monitor = NetworkMonitorWidget()
            # If hiding from monitor's context menu, uncheck the tray action
            self.network_monitor.hidden_signal = lambda: self.monitor_action.setChecked(
                False
            )

        if checked:
            self.network_monitor.show()
        else:
            self.network_monitor.hide()

        QSettings("x-tools", "network_monitor").setValue("is_visible", checked)

    def open_log_directory(self):
        try:
            os.startfile(get_log_dir())
        except Exception as e:
            logger.warning("Failed to open log directory: %s", e)

    def export_diagnostics_package(self):
        try:
            output = export_diagnostics()
            QMessageBox.information(self, "导出成功", f"诊断包已生成:\n{output}")
        except Exception as e:
            logger.exception("Failed to export diagnostics package: %s", e)
            QMessageBox.warning(self, "导出失败", f"无法导出诊断包: {e}")

    def open_settings(self):
        self.settings_window = SettingsWindow(config_manager)
        self.settings_window.settings_changed.connect(self.update_style)
        self.settings_window.hotkeys_changed.connect(self.reload_hotkeys)
        self.settings_window.show()

    def init_hotkey(self):
        self.hotkey_manager = HotkeyManager()
        self._register_hotkeys_from_config()
        self.hotkey_manager.start()

    def _register_hotkeys_from_config(self):
        from src.core.config import config_manager

        toggle_key = config_manager.get_hotkey("toggle_window")
        if toggle_key:
            self.hotkey_manager.register(toggle_key, self.toggle_signal.emit)

        screenshot_key = config_manager.get_hotkey("screenshot")
        if screenshot_key:
            self.hotkey_manager.register(screenshot_key, self.screenshot_signal.emit)

        pin_key = config_manager.get_hotkey("pin_clipboard")
        if pin_key:
            self.hotkey_manager.register(pin_key, self.pin_clipboard_signal.emit)

    def reload_hotkeys(self):
        self.hotkey_manager.restart()
        self._register_hotkeys_from_config()
        self.hotkey_manager.start()

    def trigger_screenshot(self):
        # Track if monitor was visible so we can restore it later
        self._monitor_was_visible = (
            self.network_monitor is not None and self.network_monitor.isVisible()
        )

        self.hide()
        if not self.screenshot_overlay:
            self.screenshot_overlay = ScreenshotOverlay()
            self.screenshot_overlay.closed.connect(self.on_screenshot_closed)
        self.screenshot_overlay.capture_screen()

        # Hide monitor AFTER capture_screen grabs the screen, so it appears in the screenshot
        if self._monitor_was_visible:
            self.network_monitor.hide()

    def on_screenshot_closed(self):
        # Re-show network monitor if it was visible before screenshot
        if getattr(self, "_monitor_was_visible", False) and self.network_monitor:
            QTimer.singleShot(300, self._restore_monitor_after_screenshot)

    def _restore_monitor_after_screenshot(self):
        if self.network_monitor:
            self.network_monitor.show()
            self.network_monitor.keep_on_top()

    def pin_clipboard(self):
        from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QFontMetrics

        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        pixmap = None
        if mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
        elif mime.hasText():
            text = mime.text().strip()
            if text:
                font = QFont("Microsoft YaHei UI", 14)
                fm = QFontMetrics(font)
                padding = 24
                lines = text.split("\n")
                line_height = fm.height()
                max_width = max(fm.horizontalAdvance(line) for line in lines)
                img_w = min(max_width + padding * 2, 800)
                img_h = line_height * len(lines) + padding * 2

                image = QImage(img_w, img_h, QImage.Format.Format_ARGB32)
                image.fill(QColor(36, 38, 48, 230))

                painter = QPainter(image)
                painter.setFont(font)
                painter.setPen(QColor(240, 240, 240))
                y = padding + fm.ascent()
                for line in lines:
                    painter.drawText(padding, y, line)
                    y += line_height
                painter.end()

                pixmap = QPixmap.fromImage(image)

        if pixmap and not pixmap.isNull():
            pin_win = PinnedImageWindow(pixmap)
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.geometry()
                pin_win.move(
                    (sg.width() - pixmap.width()) // 2,
                    (sg.height() - pixmap.height()) // 2,
                )
            pin_win.show()
            self._pinned_windows.append(pin_win)

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()

            if self.search_bar.text().strip() or self.plugin_mode:
                self.adjust_size(expanded=True)
            else:
                self.adjust_size(expanded=False)

            if self._needs_initial_render_sync:
                self._sync_initial_render_rect()
                self._needs_initial_render_sync = False

            if not self._has_positioned_once:
                self.center_window()
                self._has_positioned_once = True

            self.activateWindow()
            self.raise_()

            try:
                hwnd = int(self.winId())
                foreground_window = ctypes.windll.user32.GetForegroundWindow()
                current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
                foreground_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(
                    foreground_window, None
                )

                if current_thread_id != foreground_thread_id:
                    ctypes.windll.user32.AttachThreadInput(
                        foreground_thread_id, current_thread_id, True
                    )
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    ctypes.windll.user32.AttachThreadInput(
                        foreground_thread_id, current_thread_id, False
                    )
                else:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

            self.search_bar.setFocus()
            self.search_bar.deselect()
            self.search_bar.end(False)

    def on_search_query(self, text):
        if self.plugin_mode:
            self.execute_plugin(text)
            return

        self._pending_query = text
        self._search_debounce_timer.stop()
        self._search_request_id += 1

        if not text.strip():
            self.result_list.clear()
            self.preview_text.clear()
            self._search_started_at.clear()
            self._search_query_snapshot.clear()
            self.adjust_size(expanded=False)
            return

        self._search_debounce_timer.start()

    def _perform_debounced_search(self):
        raw_query = self._pending_query
        if not raw_query.strip():
            return

        plugin, plugin_query = self._parse_inline_plugin_command(raw_query)
        if plugin is not None:
            started = time.perf_counter()
            results = plugin.execute(plugin_query)
            elapsed = (time.perf_counter() - started) * 1000
            self._record_command_usage(
                raw_query.strip(), plugin=plugin, plugin_query=plugin_query
            )
            metrics_store.record(
                "search.inline_plugin",
                elapsed,
                {
                    "plugin": plugin.get_name(),
                    "query_len": len(plugin_query),
                    "result_count": len(results) if isinstance(results, list) else 0,
                },
            )
            self.update_results(results, query=raw_query, source_plugin=plugin)
            return

        query = raw_query.strip()
        request_id = self._search_request_id
        self._search_started_at[request_id] = time.perf_counter()
        self._search_query_snapshot[request_id] = raw_query
        self.search_thread = SearchThread(query, request_id)
        self.search_thread.results_found.connect(self._on_search_results)
        self.search_thread.finished.connect(self.search_thread.deleteLater)
        self.search_thread.start()

    def _on_search_results(self, request_id, query, results):
        raw_query = self._search_query_snapshot.pop(request_id, query)
        started = self._search_started_at.pop(request_id, None)
        if started is not None:
            elapsed = (time.perf_counter() - started) * 1000
            metrics_store.record(
                "search.global",
                elapsed,
                {
                    "query_len": len(raw_query),
                    "result_count": len(results) if isinstance(results, list) else 0,
                },
            )

        if request_id != self._search_request_id:
            return
        if self.plugin_mode:
            return
        if raw_query.strip() != self.search_bar.text().strip():
            return
        self.update_results(results, query=self.search_bar.text())

    def execute_plugin(self, text):
        if not self.plugin_mode:
            return
        results = self.plugin_mode.execute(text)
        self.update_results(results, query=text, source_plugin=self.plugin_mode)

    def update_results(self, results, query=None, source_plugin=None):
        self.result_list.clear()

        raw_text = query if query is not None else self.search_bar.text()
        text_stripped = raw_text.strip()
        text_lower = text_stripped.lower()

        def add_item(item_data, icon=None):
            widget_item = QListWidgetItem(item_data.get("name", ""))
            widget_item.setData(Qt.ItemDataRole.UserRole, item_data)
            if icon is not None:
                widget_item.setIcon(icon)

            item_type = item_data.get("type")
            if item_type == "app":
                widget_item.setText(f"🖥️  {item_data['name']}")
            elif item_type == "sys_cmd":
                widget_item.setForeground(QColor(108, 114, 230))
            elif item_type in ["calc_error", "error"]:
                widget_item.setForeground(Qt.GlobalColor.red)
            elif item_type == "command_hint":
                text_value = str(item_data.get("path", "")).strip()
                widget_item.setText(f"[CMD] {text_value}".strip())
            elif item_type == "command_template":
                pass
            elif item_type == "command_form":
                pass
            elif item_type == "command_recent":
                pass
            elif item_type == "command_correction":
                pass
            elif item_type == "workflow_run":
                pass
            elif item_type == "clipboard_entry":
                pass
            elif item_type in {"clipboard_center", "clipboard_cmd"}:
                pass
            elif "path" in item_data and item_type == "file":
                widget_item.setText(
                    f"📄  {item_data.get('name', '')}   ({item_data.get('path', '')})"
                )

            if self._is_favorite(item_data):
                show_text = widget_item.text()
                if show_text and not show_text.startswith("★ "):
                    widget_item.setText(f"★ {show_text}")

            self.result_list.addItem(widget_item)

        if source_plugin is None and text_lower:
            for plugin in plugin_manager.get_plugins(enabled_only=True):
                if text_lower in self._normalize_keywords(plugin):
                    if plugin.is_direct_action():
                        for res in plugin.execute(text_stripped):
                            payload = dict(res)
                            payload["plugin"] = plugin
                            add_item(
                                payload,
                                self.style().standardIcon(
                                    self.style().StandardPixmap.SP_CommandLink
                                ),
                            )
                    else:
                        add_item(
                            {
                                "type": "plugin_trigger",
                                "plugin": plugin,
                                "name": f"{plugin.get_name()} 专清模式",
                            },
                            self.style().standardIcon(
                                self.style().StandardPixmap.SP_ArrowRight
                            ),
                        )

        if not isinstance(results, list):
            results = []

        for raw_item in sorted(results, key=self._result_sort_key):
            item_data = dict(raw_item)
            if source_plugin is not None and "plugin" not in item_data:
                item_data["plugin"] = source_plugin
            add_item(item_data)

        if source_plugin is None and text_lower and self.result_list.count() == 0:
            for hint_item in self._build_command_hint_items(raw_text):
                add_item(hint_item)

        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)
            if self.results_container.isHidden():
                self.adjust_size(expanded=True)
        else:
            self.preview_text.clear()
            self.adjust_size(expanded=False)

    def on_enter_pressed(self):
        current_item = self.result_list.currentItem()
        if current_item:
            data = current_item.data(Qt.ItemDataRole.UserRole)
            self.handle_item_action(data)
        elif self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)
            current_item = self.result_list.currentItem()
            if current_item:
                data = current_item.data(Qt.ItemDataRole.UserRole)
                self.handle_item_action(data)

    def handle_item_action(self, data):
        if not isinstance(data, dict):
            return

        item_type = data.get("type")

        if item_type == "command_hint":
            template = str(data.get("path", "")).strip()
            if template:
                self.search_bar.setText(template)
                self.search_bar.setFocus()
                self.search_bar.end(False)
            return

        if item_type in {"command_template", "command_recent", "command_correction"}:
            template = str(data.get("path", "")).strip()
            if template:
                self.search_bar.setText(template)
                self.search_bar.setFocus()
                self.search_bar.end(False)
            return

        if item_type == "command_form":
            plugin = data.get("plugin")
            if plugin is not None:
                self._show_plugin_form_dialog(plugin)
            return

        if item_type == "plugin_trigger":
            self._search_debounce_timer.stop()
            self._search_request_id += 1
            self.plugin_mode = data["plugin"]
            self.search_bar.clear()
            self.search_bar.setPlaceholderText(
                f"已进入 {self.plugin_mode.get_name()} (按 ESC 退出)"
            )
            self.plugin_mode.on_enter()
            self.result_list.clear()
            self.preview_text.clear()
        elif item_type in {
            "workflow_run",
            "clipboard_center",
            "clipboard_cmd",
            "clipboard_entry",
        }:
            plugin = data.get("plugin") or self.plugin_mode
            if plugin is None or not hasattr(plugin, "handle_action"):
                return

            action = str(data.get("path", "")).strip()
            if item_type == "clipboard_entry":
                clipboard_id = str(data.get("clipboard_id") or action)
                action = f"copy:{clipboard_id}"

            message = plugin.handle_action(action)
            if message:
                try:
                    self.tray_icon.showMessage(
                        "X-Tools",
                        str(message),
                        QSystemTrayIcon.MessageIcon.Information,
                        2800,
                    )
                except Exception:
                    pass

            self._record_item_usage(data)
            if item_type != "clipboard_center":
                self.hide()
        elif item_type in ["calc_result", "copy_result"]:
            path_value = data.get("path", "")
            QApplication.clipboard().setText(path_value)
            self._record_item_usage(data)
            if self.plugin_mode:
                self.search_bar.setText(path_value)
        elif item_type == "sys_cmd":
            plugin = data.get("plugin") or self.plugin_mode
            if plugin is None:
                return

            cmd = data.get("path", "")
            if hasattr(plugin, "is_dangerous_command") and plugin.is_dangerous_command(
                cmd
            ):
                reply = QMessageBox.question(
                    self,
                    "高风险操作确认",
                    f"确认要执行系统命令 '{cmd}' 吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            plugin.handle_action(cmd)
            self._record_item_usage(data)
            self.hide()
        elif item_type == "qr_generate":
            plugin = data.get("plugin") or self.plugin_mode
            if plugin is None:
                return
            plugin.handle_action(data["path"])
            self._record_item_usage(data)
            self.hide()
        elif item_type == "hosts_cmd":
            plugin = data.get("plugin") or self.plugin_mode
            if plugin is None:
                return
            plugin.handle_action(data["path"])
            self._record_item_usage(data)
            self.hide()
        elif data.get("path"):
            self.launch_item(data["path"], data)

    def on_item_clicked(self, item):
        if item is None:
            return
        self.handle_item_action(item.data(Qt.ItemDataRole.UserRole))

    def contextMenuEvent(self, event):
        list_pos = self.result_list.viewport().mapFromGlobal(event.globalPos())
        item = self.result_list.itemAt(list_pos)
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        path = data.get("path")
        item_key = self._item_key(data)
        plugin = data.get("plugin")
        menu = QMenu(self)

        if data.get("type") == "calc_result":
            copy_action = QAction("复制结果", self)
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(path)
            )
            menu.addAction(copy_action)
        elif data.get("type") in {
            "command_hint",
            "command_template",
            "command_correction",
        }:
            fill_action = QAction("填充到输入框", self)
            fill_action.triggered.connect(
                lambda: self.search_bar.setText(str(path or "").strip())
            )
            menu.addAction(fill_action)
        elif data.get("type") == "command_recent":
            run_action = QAction("执行该命令", self)
            run_action.triggered.connect(
                lambda: self.search_bar.setText(str(path or "").strip())
            )
            menu.addAction(run_action)
        elif data.get("type") == "workflow_run":
            run_flow_action = QAction("立即执行", self)
            run_flow_action.triggered.connect(
                lambda: self.handle_item_action(item.data(Qt.ItemDataRole.UserRole))
            )
            menu.addAction(run_flow_action)
        elif data.get("type") == "clipboard_entry":
            copy_clip_action = QAction("复制该条目", self)
            copy_clip_action.triggered.connect(
                lambda: self.handle_item_action(item.data(Qt.ItemDataRole.UserRole))
            )
            menu.addAction(copy_clip_action)

            if plugin is not None and hasattr(plugin, "handle_action"):
                pinned = bool(data.get("clipboard_pinned", False))
                pin_text = "取消置顶" if pinned else "置顶"
                toggle_pin_action = QAction(pin_text, self)
                toggle_pin_action.triggered.connect(
                    lambda checked=False,
                    p=plugin,
                    entry_id=data.get("clipboard_id", ""): (
                        p.handle_action(f"pin:{entry_id}"),
                        self.on_search_query(self.search_bar.text()),
                    )
                )
                menu.addAction(toggle_pin_action)
        elif path and data.get("type") in {"file", "app"}:
            open_action = QAction("打开", self)
            open_action.triggered.connect(lambda: self.launch_item(path, data))
            menu.addAction(open_action)

            open_folder_action = QAction("打开所在文件夹", self)
            open_folder_action.triggered.connect(lambda: self.open_folder(path))
            menu.addAction(open_folder_action)

            copy_path_action = QAction("复制路径", self)
            copy_path_action.triggered.connect(
                lambda: QApplication.clipboard().setText(path)
            )
            menu.addAction(copy_path_action)

        if plugin is not None:
            schema = self._schema_from_plugin(plugin)
            params = schema.get("params", []) if isinstance(schema, dict) else []
            if isinstance(params, list) and params:
                plugin_form_action = QAction("打开参数面板", self)
                plugin_form_action.triggered.connect(
                    lambda checked=False, p=plugin: self._show_plugin_form_dialog(p)
                )
                menu.addAction(plugin_form_action)

        if item_key:
            menu.addSeparator()
            fav_text = "取消收藏" if item_key in self._favorites else "加入收藏"
            favorite_action = QAction(fav_text, self)
            favorite_action.triggered.connect(
                lambda checked=False, key=item_key: self._toggle_favorite_by_key(key)
            )
            menu.addAction(favorite_action)

        menu.exec(event.globalPos())

    def open_folder(self, path):
        if not path:
            return
        try:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                os.startfile(folder)
        except Exception as e:
            logger.warning("Error opening folder: %s", e)

    def launch_item(self, path, data=None):
        if path:
            try:
                os.startfile(path)
                self._record_item_usage(
                    data if isinstance(data, dict) else {"path": path, "type": "file"}
                )
                self.hide()
            except Exception as e:
                logger.warning("Error launching %s: %s", path, e)

    def focusOutEvent(self, event):
        if self._search_dragging_window:
            event.ignore()
            return
        self.hide()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.plugin_mode:
                self.plugin_mode.on_exit()
                self.plugin_mode = None
                self._search_request_id += 1
                self.search_bar.clear()
                self.search_bar.setPlaceholderText(
                    "唤起各类高级工具、本地搜索与系统功能..."
                )
                self.result_list.clear()
                self.adjust_size(expanded=False)
            else:
                self.hide()
        else:
            super().keyPressEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SearchWindow()
    sys.exit(app.exec())
