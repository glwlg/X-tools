import sys
import ctypes
import psutil
from typing import Callable
from PyQt6.QtCore import Qt, QTimer, QPoint, QSettings
from PyQt6.QtGui import QMouseEvent, QAction, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QMenu,
    QApplication,
    QHBoxLayout,
)
from src.core.logger import get_logger


logger = get_logger(__name__)


class NetworkMonitorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Frameless, always on top, tool window (no taskbar icon)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # ToolTip bypasses some taskbar Z-order restrictions better than Tool
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.ToolTip
        )

        self.last_net_io = psutil.net_io_counters()
        self.is_locked = False
        self.hidden_signal: Callable[[], None] | None = None

        self.drag_position = QPoint()
        self.settings = QSettings("x-tools", "network_monitor")

        self.init_ui()
        self.load_settings()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_traffic)
        self.timer.start(1000)

    def init_ui(self):
        # Semi-transparent background
        self.setStyleSheet(
            """
            QWidget#MainContainer {
                background-color: rgba(30, 30, 34, 150);
                border-radius: 4px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: "Consolas", "Microsoft YaHei UI";
            }
        """
        )

        self.container = QWidget(self)
        self.container.setObjectName("MainContainer")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        font = QFont("Consolas", 10, QFont.Weight.Bold)

        # Upload Row
        up_layout = QHBoxLayout()
        up_layout.setContentsMargins(0, 0, 0, 0)
        up_layout.setSpacing(4)
        self.up_icon_label = QLabel("↑:")
        self.up_icon_label.setFont(font)
        self.up_icon_label.setStyleSheet(
            "color: #FFFFFF;"
        )  # Changed to white as requested
        self.up_speed_label = QLabel("0 B/s")
        self.up_speed_label.setFont(font)
        self.up_speed_label.setMinimumWidth(85)
        self.up_speed_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        up_layout.addWidget(self.up_icon_label)
        up_layout.addWidget(self.up_speed_label)

        # Download Row
        down_layout = QHBoxLayout()
        down_layout.setContentsMargins(0, 0, 0, 0)
        down_layout.setSpacing(4)
        self.down_icon_label = QLabel("↓:")
        self.down_icon_label.setFont(font)
        self.down_icon_label.setStyleSheet(
            "color: #FFFFFF;"
        )  # Changed to white as requested
        self.down_speed_label = QLabel("0 B/s")
        self.down_speed_label.setFont(font)
        self.down_speed_label.setMinimumWidth(85)
        self.down_speed_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        down_layout.addWidget(self.down_icon_label)
        down_layout.addWidget(self.down_speed_label)

        layout.addLayout(up_layout)
        layout.addLayout(down_layout)

        self.adjustSize()

    def format_speed(self, bytes_per_sec):
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"

    def update_traffic(self):
        current_net_io = psutil.net_io_counters()

        # Calculate bytes per second
        upload_bytes = current_net_io.bytes_sent - self.last_net_io.bytes_sent
        download_bytes = current_net_io.bytes_recv - self.last_net_io.bytes_recv

        self.up_speed_label.setText(self.format_speed(upload_bytes))
        self.down_speed_label.setText(self.format_speed(download_bytes))

        self.up_speed_label.setStyleSheet("color: #FFFFFF;")
        self.down_speed_label.setStyleSheet("color: #FFFFFF;")

        self.last_net_io = current_net_io

        # Continuously enforce topmost if visible
        if self.isVisible():
            self.keep_on_top()

    def showEvent(self, event):
        super().showEvent(event)
        self.keep_on_top()

    def keep_on_top(self):
        try:
            hwnd = int(self.winId())

            # Find taskbar HWND
            taskbar_hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)

            if taskbar_hwnd:
                # Set taskbar as parent to force z-order
                ctypes.windll.user32.SetWindowLongPtrW(
                    hwnd, -8, taskbar_hwnd
                )  # GWLP_HWNDPARENT = -8

            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040

            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
            )
        except Exception as e:
            logger.warning("Failed to set window to top most: %s", e)

    def load_settings(self):
        geometry = self.settings.value("geometry")
        pos_x = self.settings.value("pos_x", type=int)
        pos_y = self.settings.value("pos_y", type=int)

        if pos_x is not None and pos_y is not None:
            self.move(pos_x, pos_y)
        elif geometry:
            self.restoreGeometry(geometry)
        else:
            # Default position: bottom right part of the screen
            screen = QApplication.primaryScreen().geometry()
            self.move(screen.width() - 300, screen.height() - 100)

        self.is_locked = self.settings.value("is_locked", type=bool, defaultValue=False)

    def save_settings(self):
        # Save absolute position explicitly
        if self.parentWidget() or True:
            # If we reparented to taskbar, pos() is relative to taskbar.
            # However, when we restart, before showEvent, parent is None (desktop).
            # So restoring this relative pos to desktop will put it in the top left.
            # We must save global position.
            global_pos = self.mapToGlobal(QPoint(0, 0))
            self.settings.setValue("pos_x", global_pos.x())
            self.settings.setValue("pos_y", global_pos.y())

        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("is_locked", self.is_locked)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.is_locked:
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.is_locked:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.is_locked:
            self.save_settings()

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        lock_action = QAction("解锁位置" if self.is_locked else "锁定位置", self)
        lock_action.triggered.connect(self.toggle_lock)
        menu.addAction(lock_action)

        hide_action = QAction("隐藏", self)
        hide_action.triggered.connect(self.hide_monitor)
        menu.addAction(hide_action)

        menu.exec(event.globalPos())

    def toggle_lock(self):
        self.is_locked = not self.is_locked
        self.save_settings()

    def hide_monitor(self):
        self.hide()
        if callable(self.hidden_signal):
            self.hidden_signal()
        self.settings.setValue("is_visible", False)

    def closeEvent(self, event):
        self.save_settings()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    monitor = NetworkMonitorWidget()
    monitor.show()
    sys.exit(app.exec())
