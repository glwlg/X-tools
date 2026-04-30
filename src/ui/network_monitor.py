import sys
import ctypes
import psutil
from typing import Callable
from PyQt6.QtCore import Qt, QTimer, QPoint, QSettings, QRect, QSize
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


TASKBAR_ANCHOR_MARGIN = 6
FALLBACK_TASKBAR_HEIGHT = 48


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
            self.anchor_to_taskbar()
            self.keep_on_top()

    def showEvent(self, event):
        super().showEvent(event)
        self.anchor_to_taskbar()
        self.keep_on_top()

    @staticmethod
    def _clamp_point_to_rect(point: QPoint, size: QSize, rect: QRect) -> QPoint:
        max_x = rect.x() + max(0, rect.width() - size.width())
        max_y = rect.y() + max(0, rect.height() - size.height())
        return QPoint(
            min(max(point.x(), rect.x()), max_x),
            min(max(point.y(), rect.y()), max_y),
        )

    def _resolve_visible_rect(self) -> QRect | None:
        frame_rect = self.frameGeometry()
        for screen in QApplication.screens():
            available_rect = screen.geometry()
            if (
                available_rect.intersects(frame_rect)
                or available_rect.contains(frame_rect.topLeft())
                or available_rect.contains(frame_rect.center())
            ):
                return available_rect

        screen = QApplication.primaryScreen()
        if screen is not None:
            return screen.geometry()
        return None

    @staticmethod
    def _infer_taskbar_rect(
        screen_rect: QRect,
        available_rect: QRect,
        fallback_height: int = FALLBACK_TASKBAR_HEIGHT,
    ) -> QRect:
        top_band = max(0, available_rect.top() - screen_rect.top())
        bottom_band = max(0, screen_rect.bottom() - available_rect.bottom())
        left_band = max(0, available_rect.left() - screen_rect.left())
        right_band = max(0, screen_rect.right() - available_rect.right())

        largest_band = max(top_band, bottom_band, left_band, right_band)
        if largest_band <= 0:
            height = min(fallback_height, max(1, screen_rect.height()))
            return QRect(
                screen_rect.left(),
                screen_rect.bottom() - height + 1,
                screen_rect.width(),
                height,
            )

        if bottom_band == largest_band:
            return QRect(
                screen_rect.left(),
                available_rect.bottom() + 1,
                screen_rect.width(),
                bottom_band,
            )
        if top_band == largest_band:
            return QRect(
                screen_rect.left(),
                screen_rect.top(),
                screen_rect.width(),
                top_band,
            )
        if left_band == largest_band:
            return QRect(
                screen_rect.left(),
                screen_rect.top(),
                left_band,
                screen_rect.height(),
            )

        return QRect(
            available_rect.right() + 1,
            screen_rect.top(),
            right_band,
            screen_rect.height(),
        )

    @staticmethod
    def _taskbar_left_anchor_point(
        taskbar_rect: QRect,
        widget_size: QSize,
        margin: int = TASKBAR_ANCHOR_MARGIN,
        bounding_rect: QRect | None = None,
    ) -> QPoint:
        is_horizontal_taskbar = taskbar_rect.width() >= taskbar_rect.height()
        if is_horizontal_taskbar:
            target = QPoint(
                taskbar_rect.left() + margin,
                taskbar_rect.top()
                + max(0, (taskbar_rect.height() - widget_size.height()) // 2),
            )
        else:
            target = QPoint(
                taskbar_rect.left()
                + max(0, (taskbar_rect.width() - widget_size.width()) // 2),
                taskbar_rect.top() + margin,
            )
        if bounding_rect is None:
            bounding_rect = taskbar_rect
        return NetworkMonitorWidget._clamp_point_to_rect(
            target, widget_size, bounding_rect
        )

    def _resolve_taskbar_anchor_context(self) -> tuple[QRect, QRect] | None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return None

        screen_rect = screen.geometry()
        return (
            self._infer_taskbar_rect(screen_rect, screen.availableGeometry()),
            screen_rect,
        )

    def anchor_to_taskbar(self):
        anchor_context = self._resolve_taskbar_anchor_context()
        if anchor_context is None:
            self.ensure_visible()
            return

        taskbar_rect, screen_rect = anchor_context
        target_top_left = self._taskbar_left_anchor_point(
            taskbar_rect, self.size(), bounding_rect=screen_rect
        )
        current_top_left = self.frameGeometry().topLeft()
        if target_top_left != current_top_left:
            logger.info(
                "Anchored network monitor to taskbar from (%s, %s) to (%s, %s)",
                current_top_left.x(),
                current_top_left.y(),
                target_top_left.x(),
                target_top_left.y(),
            )
            self.move(target_top_left)

    def ensure_visible(self):
        visible_rect = self._resolve_visible_rect()
        if visible_rect is None:
            return

        current_top_left = self.frameGeometry().topLeft()
        clamped_top_left = self._clamp_point_to_rect(
            current_top_left, self.size(), visible_rect
        )
        if clamped_top_left != current_top_left:
            logger.info(
                "Adjusted network monitor position from (%s, %s) to (%s, %s)",
                current_top_left.x(),
                current_top_left.y(),
                clamped_top_left.x(),
                clamped_top_left.y(),
            )
            self.move(clamped_top_left)

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
        self.is_locked = self.settings.value("is_locked", type=bool, defaultValue=False)
        self.anchor_to_taskbar()

    def save_settings(self):
        self.settings.remove("pos_x")
        self.settings.remove("pos_y")
        self.settings.remove("geometry")
        self.settings.setValue("placement", "taskbar_left")
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
            self.anchor_to_taskbar()
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
