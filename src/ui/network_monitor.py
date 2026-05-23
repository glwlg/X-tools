import sys
import ctypes
import psutil
from ctypes import wintypes
from typing import Callable
from PyQt6.QtCore import Qt, QTimer, QPoint, QSettings, QRect, QSize
from PyQt6.QtGui import QMouseEvent, QAction, QFont, QFontMetrics
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
FULLSCREEN_RECT_TOLERANCE = 2
MONITOR_TASKBAR_FILL_RATIO = 0.82
HORIZONTAL_MARGIN_RATIO = 0.14
VERTICAL_MARGIN_RATIO = 0.06
ROW_SPACING_RATIO = 0.03
COLUMN_SPACING_RATIO = 0.07
FONT_LINE_RATIO = 0.82
SPEED_LABEL_SAMPLES = ("999.9 KB/s", "1024.5 MB/s")


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


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
        self._temporarily_hidden_for_fullscreen = False
        self._applied_metrics_context = None

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

        self.content_layout = QVBoxLayout(self.container)

        # Upload Row
        self.up_layout = QHBoxLayout()
        self.up_layout.setContentsMargins(0, 0, 0, 0)
        self.up_icon_label = QLabel("↑:")
        self.up_icon_label.setStyleSheet(
            "color: #FFFFFF;"
        )  # Changed to white as requested
        self.up_speed_label = QLabel("0 B/s")
        self.up_speed_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.up_layout.addWidget(self.up_icon_label)
        self.up_layout.addWidget(self.up_speed_label)

        # Download Row
        self.down_layout = QHBoxLayout()
        self.down_layout.setContentsMargins(0, 0, 0, 0)
        self.down_icon_label = QLabel("↓:")
        self.down_icon_label.setStyleSheet(
            "color: #FFFFFF;"
        )  # Changed to white as requested
        self.down_speed_label = QLabel("0 B/s")
        self.down_speed_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.down_layout.addWidget(self.down_icon_label)
        self.down_layout.addWidget(self.down_speed_label)

        self.content_layout.addLayout(self.up_layout)
        self.content_layout.addLayout(self.down_layout)

        self._apply_adaptive_metrics(force=True)
        self.adjustSize()

    @classmethod
    def _is_horizontal_taskbar(cls, taskbar_rect: QRect) -> bool:
        return taskbar_rect.width() >= taskbar_rect.height()

    @classmethod
    def _taskbar_thickness(cls, taskbar_rect: QRect) -> int:
        if taskbar_rect.isNull():
            return FALLBACK_TASKBAR_HEIGHT
        if cls._is_horizontal_taskbar(taskbar_rect):
            return max(1, taskbar_rect.height())
        return max(1, taskbar_rect.width())

    @classmethod
    def _adaptive_metrics(cls, taskbar_rect: QRect) -> dict[str, int]:
        taskbar_thickness = cls._taskbar_thickness(taskbar_rect)
        target_height = max(24, round(taskbar_thickness * MONITOR_TASKBAR_FILL_RATIO))
        vertical_margin = max(2, round(taskbar_thickness * VERTICAL_MARGIN_RATIO))
        row_spacing = max(1, round(taskbar_thickness * ROW_SPACING_RATIO))

        line_box_height = max(
            10, (target_height - vertical_margin * 2 - row_spacing) / 2
        )
        return {
            "target_height": target_height,
            "font_pixel_size": max(9, round(line_box_height * FONT_LINE_RATIO)),
            "horizontal_margin": max(
                5, round(taskbar_thickness * HORIZONTAL_MARGIN_RATIO)
            ),
            "vertical_margin": vertical_margin,
            "row_spacing": row_spacing,
            "column_spacing": max(2, round(taskbar_thickness * COLUMN_SPACING_RATIO)),
        }

    def _current_screen(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return None
        return screen

    def _current_taskbar_rect(self) -> QRect:
        screen = self._current_screen()
        if screen is None:
            return QRect(0, 0, 1, FALLBACK_TASKBAR_HEIGHT)
        return self._infer_taskbar_rect(screen.geometry(), screen.availableGeometry())

    @staticmethod
    def _speed_label_width(font: QFont, current_texts=()) -> int:
        fm = QFontMetrics(font)
        samples = [*SPEED_LABEL_SAMPLES, *[str(text) for text in current_texts]]
        return max(fm.horizontalAdvance(text) for text in samples if text) + 4

    def _apply_adaptive_metrics(self, force=False):
        screen = self._current_screen()
        dpr = max(1.0, float(screen.devicePixelRatio())) if screen is not None else 1.0
        taskbar_rect = self._current_taskbar_rect()
        context = (
            round(dpr, 3),
            taskbar_rect.x(),
            taskbar_rect.y(),
            taskbar_rect.width(),
            taskbar_rect.height(),
            self.up_speed_label.text(),
            self.down_speed_label.text(),
        )
        if not force and self._applied_metrics_context == context:
            return

        metrics = self._adaptive_metrics(taskbar_rect)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setWeight(QFont.Weight.Bold)
        font.setPixelSize(metrics["font_pixel_size"])

        self.content_layout.setContentsMargins(
            metrics["horizontal_margin"],
            metrics["vertical_margin"],
            metrics["horizontal_margin"],
            metrics["vertical_margin"],
        )
        self.content_layout.setSpacing(metrics["row_spacing"])
        self.up_layout.setSpacing(metrics["column_spacing"])
        self.down_layout.setSpacing(metrics["column_spacing"])

        for label in (
            self.up_icon_label,
            self.up_speed_label,
            self.down_icon_label,
            self.down_speed_label,
        ):
            label.setFont(font)

        speed_label_width = self._speed_label_width(
            font, (self.up_speed_label.text(), self.down_speed_label.text())
        )
        self.up_speed_label.setMinimumWidth(speed_label_width)
        self.down_speed_label.setMinimumWidth(speed_label_width)
        self._applied_metrics_context = context
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

        self._apply_adaptive_metrics()
        self._sync_fullscreen_visibility()

        # Continuously enforce topmost if visible
        if self.isVisible():
            self.anchor_to_taskbar()
            self.keep_on_top()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_adaptive_metrics()
        self.anchor_to_taskbar()
        self.keep_on_top()
        QTimer.singleShot(0, self._sync_fullscreen_visibility)

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
        screen = self._current_screen()
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

    @staticmethod
    def _qrect_from_win_rect(rect) -> QRect:
        return QRect(
            int(rect.left),
            int(rect.top),
            max(0, int(rect.right) - int(rect.left)),
            max(0, int(rect.bottom) - int(rect.top)),
        )

    @staticmethod
    def _rect_covers_rect(
        outer_rect: QRect,
        inner_rect: QRect,
        tolerance: int = FULLSCREEN_RECT_TOLERANCE,
    ) -> bool:
        return (
            outer_rect.left() <= inner_rect.left() + tolerance
            and outer_rect.top() <= inner_rect.top() + tolerance
            and outer_rect.right() >= inner_rect.right() - tolerance
            and outer_rect.bottom() >= inner_rect.bottom() - tolerance
        )

    @staticmethod
    def _windows_class_name(hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        try:
            user32 = ctypes.windll.user32
            user32.GetClassNameW.argtypes = [
                wintypes.HWND,
                wintypes.LPWSTR,
                ctypes.c_int,
            ]
            user32.GetClassNameW.restype = ctypes.c_int
            length = user32.GetClassNameW(hwnd, buffer, len(buffer))
        except Exception:
            return ""
        if length <= 0:
            return ""
        return buffer.value

    @staticmethod
    def _windows_window_rect(hwnd: int) -> QRect | None:
        rect = wintypes.RECT()
        try:
            dwmapi = ctypes.windll.dwmapi
            result = dwmapi.DwmGetWindowAttribute(
                hwnd,
                9,  # DWMWA_EXTENDED_FRAME_BOUNDS
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            if result == 0:
                return NetworkMonitorWidget._qrect_from_win_rect(rect)
        except Exception:
            pass

        try:
            user32 = ctypes.windll.user32
            user32.GetWindowRect.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(wintypes.RECT),
            ]
            user32.GetWindowRect.restype = wintypes.BOOL
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return NetworkMonitorWidget._qrect_from_win_rect(rect)
        except Exception:
            return None
        return None

    @staticmethod
    def _windows_monitor_rect_for_window(hwnd: int) -> QRect | None:
        try:
            user32 = ctypes.windll.user32
            user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            user32.MonitorFromWindow.restype = wintypes.HMONITOR
            user32.GetMonitorInfoW.argtypes = [
                wintypes.HMONITOR,
                ctypes.POINTER(_MonitorInfo),
            ]
            user32.GetMonitorInfoW.restype = wintypes.BOOL

            monitor = user32.MonitorFromWindow(hwnd, 2)
            if not monitor:
                return None

            info = _MonitorInfo()
            info.cbSize = ctypes.sizeof(_MonitorInfo)
            if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                return None
            return NetworkMonitorWidget._qrect_from_win_rect(info.rcMonitor)
        except Exception:
            return None

    def _is_foreground_fullscreen_window(self) -> bool:
        if not sys.platform.startswith("win"):
            return False

        try:
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
            user32.IsChild.restype = wintypes.BOOL
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.restype = wintypes.BOOL
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.IsIconic.restype = wintypes.BOOL

            foreground_hwnd = int(user32.GetForegroundWindow())
            if not foreground_hwnd:
                return False

            own_hwnd = int(self.winId())
            if foreground_hwnd == own_hwnd or user32.IsChild(own_hwnd, foreground_hwnd):
                return False

            ignored_classes = {
                "Progman",
                "WorkerW",
                "Shell_TrayWnd",
                "Shell_SecondaryTrayWnd",
            }
            if self._windows_class_name(foreground_hwnd) in ignored_classes:
                return False

            if not user32.IsWindowVisible(foreground_hwnd) or user32.IsIconic(
                foreground_hwnd
            ):
                return False

            window_rect = self._windows_window_rect(foreground_hwnd)
            monitor_rect = self._windows_monitor_rect_for_window(foreground_hwnd)
            if window_rect is None or monitor_rect is None:
                return False

            return self._rect_covers_rect(window_rect, monitor_rect)
        except Exception as e:
            logger.debug("Failed to detect foreground fullscreen window: %s", e)
            return False

    def _sync_fullscreen_visibility(self):
        enabled = self.settings.value("is_visible", type=bool, defaultValue=False)
        foreground_fullscreen = self._is_foreground_fullscreen_window()

        if self.isVisible() and foreground_fullscreen:
            self._temporarily_hidden_for_fullscreen = True
            self.hide()
            return

        if not self._temporarily_hidden_for_fullscreen:
            return

        if not enabled:
            self._temporarily_hidden_for_fullscreen = False
            return

        if not foreground_fullscreen:
            self._temporarily_hidden_for_fullscreen = False
            self.show()

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
        self._temporarily_hidden_for_fullscreen = False
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
