import sys
import os
import threading
import ctypes
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QEvent, QTimer
from PyQt6.QtGui import QAction, QIcon, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QListWidgetItem,
    QSystemTrayIcon,
    QMenu,
    QGraphicsDropShadowEffect,
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


class SearchThread(QThread):
    results_found = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        app_results = app_scanner.search(self.query)
        file_results = []
        if everything_client:
            file_results = everything_client.search(self.query)
        results = app_results + file_results
        self.results_found.emit(results)


class SearchWindow(AcrylicWindow):
    toggle_signal = pyqtSignal()
    screenshot_signal = pyqtSignal()
    pin_clipboard_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.plugin_mode = None

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

        threading.Thread(target=app_scanner.scan, daemon=True).start()

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
        self._style_result_list()
        self.result_list.hide()
        layout.addWidget(self.result_list)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 50))
        self.container.setGraphicsEffect(shadow)

        self.adjust_size(expanded=False)
        # Center with slight top-offset logic
        QTimer.singleShot(50, self.center_window)

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
        self.result_list.setStyleSheet(qss)

    def update_style(self):
        self._apply_fluent_theme()
        self._style_search_bar()
        self._style_result_list()

        effect = self.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setColor(
                QColor(0, 0, 0, 80) if isDarkTheme() else QColor(0, 0, 0, 40)
            )

    def eventFilter(self, obj, event):
        if obj == self.search_bar and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self.navigate_list(1)
                return True
            elif key == Qt.Key.Key_Up:
                self.navigate_list(-1)
                return True
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
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - 600) // 4
        self.move(x, y)

    def adjust_size(self, expanded=True):
        if expanded:
            self.setFixedSize(700, 560)
            self.result_list.show()
        else:
            self.setFixedSize(700, 86)
            self.result_list.hide()

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = (
            QIcon(self.logo_path)
            if self.logo_path
            else self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon)
        )
        self.tray_icon.setIcon(icon)

        menu = QMenu()
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

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
        self.hide()
        if not self.screenshot_overlay:
            self.screenshot_overlay = ScreenshotOverlay()
            self.screenshot_overlay.closed.connect(self.on_screenshot_closed)
        self.screenshot_overlay.capture_screen()

    def on_screenshot_closed(self):
        pass

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

            if self.search_bar.text().strip() or self.plugin_mode:
                self.adjust_size(expanded=True)
            else:
                self.adjust_size(expanded=False)

    def on_search_query(self, text):
        if self.plugin_mode:
            self.execute_plugin(text)
            return

        if not text.strip():
            self.result_list.clear()
            self.adjust_size(expanded=False)
            return

        self.search_thread = SearchThread(text)
        self.search_thread.results_found.connect(self.update_results)
        self.search_thread.start()

    def execute_plugin(self, text):
        results = self.plugin_mode.execute(text)
        self.update_results(results)

    def update_results(self, results):
        self.result_list.clear()

        text = self.search_bar.text().strip()
        for plugin in plugin_manager.get_plugins(enabled_only=True):
            if text in plugin.get_keywords():
                if hasattr(plugin, "is_direct_action") and plugin.is_direct_action():
                    for res in plugin.execute(text):
                        item = QListWidgetItem(res["name"])
                        res["plugin"] = plugin
                        item.setData(Qt.ItemDataRole.UserRole, res)
                        item.setIcon(
                            self.style().standardIcon(
                                self.style().StandardPixmap.SP_CommandLink
                            )
                        )
                        self.result_list.addItem(item)
                else:
                    item = QListWidgetItem(f"{plugin.get_name()} 专清模式")
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        {"type": "plugin_trigger", "plugin": plugin},
                    )
                    item.setIcon(
                        self.style().standardIcon(
                            self.style().StandardPixmap.SP_ArrowRight
                        )
                    )
                    self.result_list.addItem(item)

        for item in results:
            widget_item = QListWidgetItem(item["name"])
            widget_item.setData(Qt.ItemDataRole.UserRole, item)

            if item.get("type") == "app":
                widget_item.setText(f"🖥️  {item['name']}")
            elif item.get("type") in ["calc_result", "copy_result"]:
                pass
            elif item.get("type") in ["calc_error", "error"]:
                widget_item.setForeground(Qt.GlobalColor.red)
            elif item.get("type") == "sys_cmd":
                widget_item.setForeground(QColor(108, 114, 230))
            else:
                if "path" in item:
                    widget_item.setText(f"📄  {item['name']}   ({item['path']})")

            self.result_list.addItem(widget_item)

        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)
            if self.result_list.isHidden():
                self.adjust_size(expanded=True)

    def on_enter_pressed(self):
        if self.result_list.currentItem():
            data = self.result_list.currentItem().data(Qt.ItemDataRole.UserRole)
            self.handle_item_action(data)
        elif self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)
            data = self.result_list.currentItem().data(Qt.ItemDataRole.UserRole)
            self.handle_item_action(data)

    def handle_item_action(self, data):
        if data.get("type") == "plugin_trigger":
            self.plugin_mode = data["plugin"]
            self.search_bar.clear()
            self.search_bar.setPlaceholderText(
                f"已进入 {self.plugin_mode.get_name()} (按 ESC 退出)"
            )
            self.plugin_mode.on_enter()
            self.result_list.clear()
        elif data.get("type") in ["calc_result", "copy_result"]:
            QApplication.clipboard().setText(data["path"])
            if self.plugin_mode:
                self.search_bar.setText(data["path"])
        elif data.get("type") == "sys_cmd":
            self.plugin_mode.handle_action(data["path"])
            self.hide()
        elif data.get("type") == "qr_generate":
            self.plugin_mode.handle_action(data["path"])
            self.hide()
        elif data.get("type") == "hosts_cmd":
            plugin = data.get("plugin")
            if plugin:
                plugin.handle_action(data["path"])
            else:
                self.plugin_mode.handle_action(data["path"])
            self.hide()
        elif data.get("path"):
            self.launch_item(data["path"])

    def on_item_clicked(self, item):
        self.handle_item_action(item.data(Qt.ItemDataRole.UserRole))

    def contextMenuEvent(self, event):
        item = self.result_list.itemAt(event.pos())
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        path = data.get("path")
        menu = QMenu(self)

        if data.get("type") == "calc_result":
            copy_action = QAction("复制结果", self)
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(path)
            )
            menu.addAction(copy_action)
        elif path:
            open_action = QAction("打开", self)
            open_action.triggered.connect(lambda: self.launch_item(path))
            menu.addAction(open_action)

            open_folder_action = QAction("打开所在文件夹", self)
            open_folder_action.triggered.connect(lambda: self.open_folder(path))
            menu.addAction(open_folder_action)

            copy_path_action = QAction("复制路径", self)
            copy_path_action.triggered.connect(
                lambda: QApplication.clipboard().setText(path)
            )
            menu.addAction(copy_path_action)

        menu.exec(event.globalPos())

    def open_folder(self, path):
        if not path:
            return
        try:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                os.startfile(folder)
        except Exception as e:
            print(f"Error opening folder: {e}")

    def launch_item(self, path):
        if path:
            try:
                os.startfile(path)
                self.hide()
            except Exception as e:
                print(f"Error launching {path}: {e}")

    def focusOutEvent(self, event):
        self.hide()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.plugin_mode:
                self.plugin_mode.on_exit()
                self.plugin_mode = None
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
