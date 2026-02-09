import sys
import os
import keyboard
import threading
import ctypes
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QEvent
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSystemTrayIcon,
    QMenu,
)

from src.core.everything import everything_client
from src.core.app_scanner import app_scanner
from src.core.config import config_manager
from src.ui.settings_window import SettingsWindow
from src.plugins.calculator import CalculatorPlugin


class SearchThread(QThread):
    results_found = pyqtSignal(list)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        # 1. Search Apps (In-memory, fast)
        app_results = app_scanner.search(self.query)

        # 2. Search Files (Everything SDK)
        file_results = []
        if everything_client:
            file_results = everything_client.search(self.query)

        # Combine
        results = app_results + file_results
        self.results_found.emit(results)


class SearchWindow(QMainWindow):
    toggle_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.plugin_mode = None
        self.calculator_plugin = CalculatorPlugin()

        self.logo_path = self.resolve_resource_path("logo.png")

        self.init_ui()
        self.init_tray()
        self.init_hotkey()

        self.toggle_signal.connect(self.toggle_visibility)

        # Scan apps on startup
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
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Central Widget & Layout
        self.central_widget = QWidget()
        self.update_style()  # Apply theme

        if self.logo_path:
            self.setWindowIcon(QIcon(self.logo_path))

        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(15, 15, 15, 15)

        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.textChanged.connect(self.on_search_query)
        self.search_bar.returnPressed.connect(self.on_enter_pressed)
        layout.addWidget(self.search_bar)

        # Install event filter on search bar to handle navigation keys
        self.search_bar.installEventFilter(self)

        # Result List
        self.result_list = QListWidget()
        self.result_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.result_list.itemClicked.connect(self.on_item_clicked)
        # Initially hidden
        self.result_list.hide()
        layout.addWidget(self.result_list)

        self.setCentralWidget(self.central_widget)
        # Apply initial size
        self.adjust_size(expanded=False)
        self.center_window()

    def update_style(self):
        theme = config_manager.get_theme()
        qss = f"""
            QWidget {{
                background-color: {theme["window_bg"]};
                border-radius: 10px;
                border: 1px solid {theme["border"]};
                color: {theme["text_color"]};
            }}
            QLineEdit {{
                background-color: {theme["input_bg"]};
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 18px;
                selection-background-color: {theme["highlight"]};
                color: {theme["text_color"]};
            }}
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 5px;
                color: {theme["text_color"]};
            }}
            QListWidget::item:selected {{
                background-color: {theme["highlight"]};
            }}
            QMenu {{
                background-color: {theme["window_bg"]};
                color: {theme["text_color"]};
                border: 1px solid {theme["border"]};
            }}
            QMenu::item:selected {{
                background-color: {theme["highlight"]};
            }}
            QScrollBar:vertical {{
                border: none;
                background: {theme["scrollbar_bg"]};
                width: 10px;
                margin: 0px 0px 0px 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme["scrollbar_handle"]};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
        """
        self.central_widget.setStyleSheet(qss)

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

        current_row = self.result_list.currentRow()
        next_row = current_row + direction

        # Clamp selection
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
            self.setFixedSize(700, 500)
            self.result_list.show()
        else:
            self.setFixedSize(700, 80)  # Compact height
            self.result_list.hide()

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)

        if self.logo_path:
            icon = QIcon(self.logo_path)
        else:
            icon = self.style().standardIcon(
                self.style().StandardPixmap.SP_ComputerIcon
            )

        self.tray_icon.setIcon(icon)

        menu = QMenu()

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def open_settings(self):
        self.settings_window = SettingsWindow(config_manager)
        self.settings_window.settings_changed.connect(self.update_style)
        self.settings_window.show()

    def init_hotkey(self):
        try:
            keyboard.add_hotkey("alt+q", self.toggle_signal.emit, suppress=True)
        except ImportError:
            print("Keyboard module failed.")

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()

            # Force focus
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

        # Check for plugin trigger manually here
        text = self.search_bar.text().strip()
        if text == "c":
            item = QListWidgetItem("Calculator Mode")
            item.setData(
                Qt.ItemDataRole.UserRole,
                {"type": "plugin_trigger", "plugin": "calculator"},
            )
            icon = self.style().standardIcon(
                self.style().StandardPixmap.SP_ArrowRight
            )  # Or similar
            item.setIcon(icon)
            self.result_list.addItem(item)

        for item in results:
            widget_item = QListWidgetItem(item["name"])
            widget_item.setData(Qt.ItemDataRole.UserRole, item)

            if item.get("type") == "app":
                widget_item.setText(f"[App] {item['name']}")
            elif item.get("type") == "calc_result":
                pass  # Already formatted in name
            elif item.get("type") == "calc_error":
                widget_item.setForeground(Qt.GlobalColor.red)
            else:
                if "path" in item:
                    widget_item.setText(f"{item['name']}   ({item['path']})")

            self.result_list.addItem(widget_item)

        if self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)
            if self.result_list.isHidden():
                self.adjust_size(expanded=True)
        # In plugin mode, maybe always expand or context dependant?
        # Calculator might show result immediately.

    def on_enter_pressed(self):
        text = self.search_bar.text().strip()

        # Check for Plugin trigger
        if not self.plugin_mode:
            # Removed hardcoded check, relying on selected item
            pass

        # Launch Item
        if self.result_list.currentItem():
            data = self.result_list.currentItem().data(Qt.ItemDataRole.UserRole)
            self.handle_item_action(data)
        elif self.result_list.count() > 0:
            self.result_list.setCurrentRow(0)
            data = self.result_list.currentItem().data(Qt.ItemDataRole.UserRole)
            self.handle_item_action(data)

    def handle_item_action(self, data):
        if data.get("type") == "plugin_trigger":
            if data["plugin"] == "calculator":
                self.plugin_mode = self.calculator_plugin
                self.search_bar.clear()
                self.search_bar.setPlaceholderText(
                    "Calculator Mode (Type expression...)"
                )
                self.plugin_mode.on_enter()
                self.result_list.clear()
        elif data.get("type") == "calc_result":
            # Copy result to clipboard
            QApplication.clipboard().setText(data["path"])
            # Maybe show a message?
            self.search_bar.setText(
                data["path"]
            )  # Replace input with result for further calc?
        elif data.get("path"):
            self.launch_item(data["path"])

    def on_item_clicked(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.handle_item_action(data)

    def contextMenuEvent(self, event):
        item = self.result_list.itemAt(event.pos())
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        path = data.get("path")

        menu = QMenu(self)

        if data.get("type") == "calc_result":
            copy_action = QAction("Copy Result", self)
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(path)
            )
            menu.addAction(copy_action)
        elif path:
            open_action = QAction("Open", self)
            open_action.triggered.connect(lambda: self.launch_item(path))
            menu.addAction(open_action)

            open_folder_action = QAction("Open Containing Folder", self)
            open_folder_action.triggered.connect(lambda: self.open_folder(path))
            menu.addAction(open_folder_action)

            copy_path_action = QAction("Copy Path", self)
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

    # Events
    def focusOutEvent(self, event):
        # Don't hide if settings window is active or context menu?
        # But focusOut is for this window. Settiings is separate.
        # If settings is open, we might want to keep SearchWindow open?
        # User said "hide by esc". But let's keep focus out behavior unless plugin mode override?
        # "按esc退出插件，再按esc才会隐藏窗口" - implies strict control logic for Esc.
        self.hide()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.plugin_mode:
                # Exit plugin mode
                self.plugin_mode.on_exit()
                self.plugin_mode = None
                self.search_bar.clear()
                self.search_bar.setPlaceholderText("Search...")
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
