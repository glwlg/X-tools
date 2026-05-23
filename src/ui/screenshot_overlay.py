from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, pyqtSignal, QSize, QSettings
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QPainterPath,
    QPainterPathStroker,
    QPolygonF,
    QIcon,
    QPixmap,
    QFont,
    QFontMetrics,
    QKeySequence,
)
from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLineEdit,
    QButtonGroup,
    QFileDialog,
    QMessageBox,
    QGraphicsDropShadowEffect,
    QLabel,
)
from datetime import datetime
import math
import time
import os

cv2 = None
np = None

try:
    import cv2
    import numpy as np

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from src.ui.pinned_image_window import PinnedImageWindow
from src.core.logger import get_logger
from src.core.config import config_manager
from src.core.capture_history import capture_history_manager
from src.core.metrics import metrics_store


logger = get_logger(__name__)


class ScreenshotOverlay(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.screen_pixmap = None
        self.screen_image = None
        self.screen_virtual_rect = QRect()
        self.screen_capture_sources = []
        self.screen_scale = 1.0

        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.current_mouse_pos = QPoint()
        self.is_drawing = False
        self.is_resizing = False
        self.resize_anchor = None
        self.selection_rect = QRect()
        self.setMouseTracking(True)

        self.pinned_windows = []

        self.draw_mode = None
        self.color_format = "rgb"
        self.draw_color = QColor("#FF3333")  # Default Red
        self.draw_thickness = 3
        self.settings = QSettings("x-tools", "screenshot_overlay")
        self._load_annotation_style()
        self.draw_actions = []
        self.current_action = None
        self.mosaic_pixmap = None
        self.is_moving_action = False
        self.moving_action_index = None
        self.action_drag_last_pos = QPoint()
        self.action_drag_changed = False
        self.editing_text_index = None
        self.editing_text_snapshot = None

        self.text_input = QLineEdit(self)
        self.text_input.hide()
        self.text_input.setStyleSheet(
            "background: transparent; border: none; font-size: 18px; color: #FF3333; outline: none; margin: 0; padding: 0;"
        )
        self.text_input.returnPressed.connect(self.commit_text_action)

        self.undo_states = []
        self.redo_states = []

        self.init_toolbar()

    def create_icon(self, mode):
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))

        if mode == "move":
            painter.drawLine(12, 2, 12, 22)
            painter.drawLine(2, 12, 22, 12)
            painter.drawLine(12, 2, 9, 5)
            painter.drawLine(12, 2, 15, 5)
            painter.drawLine(12, 22, 9, 19)
            painter.drawLine(12, 22, 15, 19)
            painter.drawLine(2, 12, 5, 9)
            painter.drawLine(2, 12, 5, 15)
            painter.drawLine(22, 12, 19, 9)
            painter.drawLine(22, 12, 19, 15)
        elif mode == "rect":
            painter.drawRoundedRect(3, 3, 18, 18, 2, 2)
        elif mode == "line":
            painter.drawLine(4, 20, 20, 4)
        elif mode == "arrow":
            painter.drawLine(4, 20, 20, 4)
            painter.drawLine(20, 4, 12, 4)
            painter.drawLine(20, 4, 20, 12)
        elif mode == "pen":
            painter.setPen(
                QPen(
                    Qt.GlobalColor.white,
                    2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            path = QPainterPath()
            path.moveTo(4, 16)
            path.quadTo(12, 4, 20, 4)
            painter.drawPath(path)
        elif mode == "mosaic":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(Qt.GlobalColor.white)
            painter.drawRect(4, 4, 8, 8)
            painter.drawRect(12, 12, 8, 8)
            painter.setBrush(QColor(150, 150, 150))
            painter.drawRect(12, 4, 8, 8)
            painter.drawRect(4, 12, 8, 8)
        elif mode == "text":
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(18)
            painter.setFont(font)
            painter.drawText(QRect(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, "T")
        elif mode == "number":
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(14)
            painter.setFont(font)
            painter.drawEllipse(4, 4, 16, 16)
            painter.drawText(QRect(4, 4, 16, 16), Qt.AlignmentFlag.AlignCenter, "1")
        elif mode == "eraser":
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawRect(4, 8, 16, 8)
            painter.setBrush(Qt.GlobalColor.white)
            painter.drawRect(4, 12, 16, 4)
        elif mode == "undo":
            painter.drawArc(4, 4, 16, 16, 16 * 16, 180 * 16)
            painter.drawLine(4, 12, 0, 8)
            painter.drawLine(4, 12, 8, 8)
        elif mode == "redo":
            painter.drawArc(4, 4, 16, 16, -16 * 16, -180 * 16)
            painter.drawLine(20, 12, 24, 8)
            painter.drawLine(20, 12, 16, 8)
        elif mode == "copy":
            painter.drawRect(8, 8, 12, 12)
            painter.drawLine(4, 8, 4, 16)
            painter.drawLine(4, 4, 12, 4)
        elif mode == "pin":
            painter.drawEllipse(8, 4, 8, 8)
            painter.drawLine(12, 12, 12, 20)
        elif mode == "qr":
            painter.drawRect(4, 4, 6, 6)
            painter.drawRect(14, 4, 6, 6)
            painter.drawRect(4, 14, 6, 6)
            painter.drawRect(14, 14, 6, 6)
        elif mode == "close":
            painter.drawLine(6, 6, 18, 18)
            painter.drawLine(6, 18, 18, 6)
        elif mode == "save":
            painter.drawRoundedRect(4, 4, 16, 16, 2, 2)
            painter.drawLine(8, 4, 8, 10)
            painter.drawLine(16, 4, 16, 10)
            painter.drawLine(8, 10, 16, 10)
            painter.drawRect(8, 13, 8, 5)

        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _add_toolbar_shadow(widget: QWidget, blur: int = 30):
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setColor(QColor(0, 0, 0, 165))
        shadow.setOffset(0, 8)
        widget.setGraphicsEffect(shadow)

    def init_toolbar(self):
        # Transparent host: the visual weight lives in the rounded clusters below.
        self.toolbar_widget = QFrame(self)
        self.toolbar_widget.setObjectName("MainFrame")
        self.toolbar_widget.setStyleSheet(
            """
            QFrame#MainFrame {
                background: transparent;
                border: none;
            }
            QFrame#ToolbarCluster, QFrame#SubFrame {
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #34383D,
                    stop: 0.46 #25292D,
                    stop: 1 #181B1F
                );
                border: 1px solid rgba(255, 255, 255, 50);
            }
            QFrame#ToolbarCluster {
                border-radius: 26px;
            }
            QFrame#SubFrame {
                border-radius: 18px;
            }
            QFrame#ToolbarSeparator {
                background-color: rgba(255, 255, 255, 46);
                border: none;
                min-width: 1px;
                max-width: 1px;
                margin: 9px 7px;
            }
            QPushButton[toolbarButton="true"] {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 17px;
                padding: 0;
            }
            QPushButton[toolbarButton="true"]:hover {
                background-color: rgba(255, 255, 255, 28);
                border: 1px solid rgba(255, 255, 255, 34);
            }
            QPushButton[toolbarButton="true"]:pressed {
                background-color: rgba(0, 0, 0, 52);
                border: 1px solid rgba(255, 255, 255, 22);
            }
            QPushButton[toolbarButton="true"]:checked {
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #5FA3FF,
                    stop: 0.52 #367DE8,
                    stop: 1 #2465C9
                );
                border: 1px solid rgba(255, 255, 255, 78);
            }
            QPushButton[colorButton="true"] {
                border: 2px solid rgba(255, 255, 255, 34);
                border-radius: 11px;
                padding: 0;
            }
            QPushButton[colorButton="true"]:hover {
                border: 2px solid rgba(255, 255, 255, 118);
            }
            QPushButton[colorButton="true"]:checked {
                border: 2px solid #FFFFFF;
            }
            QLabel#ToolbarHint {
                color: rgba(255, 255, 255, 170);
                font-family: "Microsoft YaHei UI";
                font-size: 11px;
                padding-left: 2px;
            }
            """
        )

        main_layout = QVBoxLayout(self.toolbar_widget)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(8)

        # Sub Toolbar (Colors & Thickness)
        self.sub_toolbar = QFrame(self.toolbar_widget)
        self.sub_toolbar.setObjectName("SubFrame")
        sub_layout = QHBoxLayout(self.sub_toolbar)
        sub_layout.setContentsMargins(14, 8, 14, 8)
        sub_layout.setSpacing(8)
        self._add_toolbar_shadow(self.sub_toolbar, blur=22)

        # Color palettes
        colors = [
            "#FF3333",
            "#FF9933",
            "#FFCC00",
            "#33CC33",
            "#3399FF",
            "#CC33FF",
            "#FFFFFF",
            "#000000",
        ]
        self.palette_colors = colors
        self.color_group = QButtonGroup(self)
        for i, h in enumerate(colors):
            btn = QPushButton()
            btn.setProperty("colorButton", True)
            btn.setFixedSize(22, 22)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {h};
                    border: 2px solid rgba(255, 255, 255, 34);
                    border-radius: 11px;
                    padding: 0;
                }}
                QPushButton:hover {{
                    border: 2px solid rgba(255, 255, 255, 118);
                }}
                QPushButton:checked {{
                    border: 2px solid #FFFFFF;
                }}
            """)
            btn.clicked.connect(lambda checked, c=h: self.set_draw_color(c))
            self.color_group.addButton(btn, i)
            sub_layout.addWidget(btn)
        self._sync_color_buttons()

        sub_layout.addSpacing(15)

        # Thickness hint
        hint_label = QLabel("滚轮调节粗细")
        hint_label.setObjectName("ToolbarHint")
        sub_layout.addWidget(hint_label)

        main_layout.addWidget(self.sub_toolbar)
        self.sub_toolbar.hide()

        # Tools Row
        self.tools_row = QFrame(self.toolbar_widget)
        self.tools_row.setObjectName("ToolbarRow")
        tools_layout = QHBoxLayout(self.tools_row)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(14)

        tool_cluster = QFrame(self.tools_row)
        tool_cluster.setObjectName("ToolbarCluster")
        action_cluster = QFrame(self.tools_row)
        action_cluster.setObjectName("ToolbarCluster")
        self._add_toolbar_shadow(tool_cluster)
        self._add_toolbar_shadow(action_cluster)

        tool_layout = QHBoxLayout(tool_cluster)
        tool_layout.setContentsMargins(10, 8, 10, 8)
        tool_layout.setSpacing(7)
        action_layout = QHBoxLayout(action_cluster)
        action_layout.setContentsMargins(10, 8, 10, 8)
        action_layout.setSpacing(7)
        tools_layout.addWidget(tool_cluster)
        tools_layout.addWidget(action_cluster)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(False)

        def create_separator():
            separator = QFrame()
            separator.setObjectName("ToolbarSeparator")
            separator.setFixedHeight(32)
            return separator

        def prepare_toolbar_button(btn):
            btn.setProperty("toolbarButton", True)
            btn.setFixedSize(46, 46)
            btn.setIconSize(QSize(24, 24))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            return btn

        def create_tool(name, mode):
            btn = QPushButton()
            prepare_toolbar_button(btn)
            btn.setIcon(self.create_icon(mode))
            btn.setToolTip(name)
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda checked, m=mode, b=btn: self.handle_tool_click(b, m)
            )
            self.tool_group.addButton(btn)
            return btn

        def create_action(name, mode, callback):
            btn = QPushButton()
            prepare_toolbar_button(btn)
            btn.setIcon(self.create_icon(mode))
            btn.setToolTip(name)
            btn.clicked.connect(callback)
            return btn

        btn_rect = create_tool("矩形", "rect")
        btn_pen = create_tool("画笔", "pen")
        btn_arrow = create_tool("箭头", "arrow")
        btn_line = create_tool("直线", "line")
        btn_mosaic = create_tool("马赛克", "mosaic")
        btn_text = create_tool("文字", "text")
        btn_number = create_tool("编号", "number")
        btn_eraser = create_tool("橡皮擦", "eraser")

        tool_layout.addWidget(btn_rect)
        tool_layout.addWidget(btn_pen)
        tool_layout.addWidget(btn_arrow)
        tool_layout.addWidget(btn_line)
        tool_layout.addWidget(btn_mosaic)
        tool_layout.addWidget(create_separator())
        tool_layout.addWidget(btn_text)
        tool_layout.addWidget(btn_number)
        tool_layout.addWidget(btn_eraser)

        btn_undo = create_action("撤销", "undo", self.undo_action)
        btn_redo = create_action("重做", "redo", self.redo_action)
        btn_pin = create_action("贴图 (P)", "pin", self.on_pin_clicked)
        btn_qr = create_action("扫码 (Q)", "qr", self.on_qr_clicked)
        btn_save = create_action("保存到... (Ctrl+S)", "save", self.on_save_clicked)
        btn_copy = create_action("复制到剪贴板 (Enter)", "copy", self.on_copy_clicked)
        btn_cancel = create_action("退出 (Esc)", "close", self.close_overlay)

        action_layout.addWidget(btn_undo)
        action_layout.addWidget(btn_redo)
        action_layout.addWidget(create_separator())
        action_layout.addWidget(btn_pin)
        action_layout.addWidget(btn_qr)
        action_layout.addWidget(create_separator())
        action_layout.addWidget(btn_save)
        action_layout.addWidget(btn_copy)
        action_layout.addWidget(btn_cancel)

        main_layout.addWidget(self.tools_row)
        self.toolbar_widget.hide()

    def set_draw_color(self, color_hex):
        self.draw_color = QColor(color_hex)
        self._save_annotation_style()
        self._sync_color_buttons()
        self.text_input.setStyleSheet(
            f"background: transparent; border: none; font-size: 18px; color: {color_hex}; outline: none; margin: 0; padding: 0;"
        )
        if self.text_input.isVisible():
            self.update_text_input_style()

    def set_draw_thickness(self, val):
        self.draw_thickness = max(2, min(50, int(val)))
        self._save_annotation_style()
        if self.text_input.isVisible():
            self.update_text_input_style()

    def _load_annotation_style(self):
        color_hex = str(
            self.settings.value("draw_color", self.draw_color.name(), type=str)
        ).strip()
        color = QColor(color_hex)
        if color.isValid():
            self.draw_color = color

        thickness = self.settings.value(
            "draw_thickness", self.draw_thickness, type=int
        )
        if thickness is not None:
            self.draw_thickness = max(2, min(50, int(thickness)))

    def _save_annotation_style(self):
        self.settings.setValue("draw_color", self.draw_color.name().upper())
        self.settings.setValue("draw_thickness", self.draw_thickness)

    def _sync_color_buttons(self):
        if not hasattr(self, "color_group"):
            return

        current_color = self.draw_color.name().upper()
        for button in self.color_group.buttons():
            color_index = self.color_group.id(button)
            color_hex = self.palette_colors[color_index].upper()
            button.setChecked(color_hex == current_color)

    @staticmethod
    def _enable_quality_rendering(painter: QPainter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    @staticmethod
    def _annotation_font(base_font: QFont, pixel_size: int, bold: bool = False) -> QFont:
        font = QFont(base_font)
        font.setFamily("Microsoft YaHei UI")
        font.setPixelSize(max(1, int(pixel_size)))
        font.setBold(bold)
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return font

    @staticmethod
    def _number_text_color(marker_color: QColor) -> QColor:
        color = QColor(marker_color)
        if not color.isValid():
            return QColor("#FFFFFF")

        perceived_brightness = (
            color.red() * 299 + color.green() * 587 + color.blue() * 114
        ) / 1000
        return QColor("#000000" if perceived_brightness > 140 else "#FFFFFF")

    @staticmethod
    def _number_marker_size(thickness: int) -> int:
        return min(48, max(24, 20 + int(thickness) * 2))

    @staticmethod
    def _smooth_path(points) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path

        path.moveTo(QPointF(points[0]))
        if len(points) == 1:
            return path
        if len(points) == 2:
            path.lineTo(QPointF(points[1]))
            return path

        for index in range(1, len(points) - 1):
            current = points[index]
            next_point = points[index + 1]
            mid = QPointF(
                (current.x() + next_point.x()) / 2,
                (current.y() + next_point.y()) / 2,
            )
            path.quadTo(QPointF(current), mid)
        path.lineTo(QPointF(points[-1]))
        return path

    @staticmethod
    def _draw_arrow(painter: QPainter, p1: QPoint, p2: QPoint, color, thickness: int):
        start = QPointF(p1)
        end = QPointF(p2)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return

        arrow_color = QColor(color)
        ux = dx / length
        uy = dy / length
        head_len = min(max(14.0, float(thickness) * 5.5), max(8.0, length * 0.45))
        head_width = min(max(10.0, float(thickness) * 3.8), max(6.0, length * 0.35))
        shaft_end = QPointF(
            end.x() - ux * head_len * 0.45,
            end.y() - uy * head_len * 0.45,
        )
        base = QPointF(end.x() - ux * head_len, end.y() - uy * head_len)
        normal_x = -uy
        normal_y = ux
        left = QPointF(
            base.x() + normal_x * head_width / 2,
            base.y() + normal_y * head_width / 2,
        )
        right = QPointF(
            base.x() - normal_x * head_width / 2,
            base.y() - normal_y * head_width / 2,
        )

        painter.setPen(
            QPen(
                arrow_color,
                thickness,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(start, shaft_end)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(arrow_color)
        painter.drawPolygon(QPolygonF([end, left, right]))

    def _draw_number_marker(
        self,
        painter: QPainter,
        rect: QRect,
        marker_color,
        number_text: str,
        outline_width: int,
    ):
        color = QColor(marker_color)
        if not color.isValid():
            color = QColor("#FF3333")

        ellipse_rect = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 35))
        painter.drawEllipse(ellipse_rect.translated(0, 1))

        border_width = max(1.0, min(2.0, float(outline_width) * 0.45))
        painter.setPen(QPen(QColor(255, 255, 255, 190), border_width))
        painter.setBrush(color)
        painter.drawEllipse(ellipse_rect)

        font = self._annotation_font(
            painter.font(), max(12, int(rect.height() * 0.52)), bold=True
        )
        painter.setFont(font)
        painter.setPen(self._number_text_color(color))
        painter.drawText(QRectF(rect), Qt.AlignmentFlag.AlignCenter, number_text)

    def handle_tool_click(self, btn, mode):
        # Enforce exclusivity manually to allow unchecking
        if btn.isChecked():
            for b in self.tool_group.buttons():
                if b != btn:
                    b.setChecked(False)
            self.draw_mode = mode
            if mode in ["rect", "line", "arrow", "pen", "text", "number"]:
                self.sub_toolbar.show()
            else:
                self.sub_toolbar.hide()
        else:
            self.draw_mode = None
            self.sub_toolbar.hide()

        if self.text_input.isVisible():
            self.commit_text_action()
        self.toolbar_widget.adjustSize()

    def undo_action(self):
        if self.text_input.isVisible():
            self.commit_text_action()
        if self.undo_states:
            self.redo_states.append(self._clone_draw_actions())
            self.draw_actions = self.undo_states.pop()
            self.update()

    def redo_action(self):
        if self.text_input.isVisible():
            self.commit_text_action()
        if self.redo_states:
            self.undo_states.append(self._clone_draw_actions())
            self.draw_actions = self.redo_states.pop()
            self.update()

    @staticmethod
    def _clone_action(action):
        cloned = {}
        for key, value in action.items():
            if key == "points":
                cloned[key] = [QPoint(point) for point in value]
            elif key == "pos":
                cloned[key] = QPoint(value)
            elif key == "color":
                cloned[key] = QColor(value)
            else:
                cloned[key] = value
        return cloned

    def _clone_draw_actions(self):
        return [self._clone_action(action) for action in self.draw_actions]

    def _record_undo_state(self, snapshot=None):
        if snapshot is None:
            snapshot = self._clone_draw_actions()
        self.undo_states.append(snapshot)
        self.redo_states.clear()

    @staticmethod
    def _is_movable_action_type(action_type):
        return action_type in {"text", "rect", "line", "arrow", "number"}

    @staticmethod
    def _normalize_output_path(output_path: str) -> str:
        root, ext = os.path.splitext(output_path)
        if ext.lower() != ".png":
            return root + ".png"
        return output_path

    @staticmethod
    def _translate_action(action, delta: QPoint):
        if delta.isNull():
            return
        if action.get("type") in {"text", "number"}:
            action["pos"] = action["pos"] + delta
        elif "points" in action:
            action["points"] = [point + delta for point in action["points"]]

    @staticmethod
    def _get_number_action_rect(action) -> QRect:
        size = max(14, int(action.get("size", 24)))
        top_left = action["pos"] - QPoint(size // 2, size // 2)
        return QRect(top_left, QSize(size, size))

    def _next_number_label(self):
        max_number = 0
        for action in self.draw_actions:
            if action.get("type") != "number":
                continue
            try:
                max_number = max(max_number, int(action.get("number", 0)))
            except (TypeError, ValueError):
                continue
        return max_number + 1

    def _get_text_action_rect(self, action) -> QRect:
        font = QFont(self.text_input.font())
        font.setPixelSize(action.get("font_size", 18))
        fm = QFontMetrics(font)
        text = action.get("text", "")
        width = max(12, fm.horizontalAdvance(text) + 6)
        height = max(12, fm.height() + 4)
        return QRect(action["pos"], QSize(width, height))

    def _action_contains_point(self, action, pos: QPoint) -> bool:
        action_type = action.get("type")
        if action_type == "text":
            return self._get_text_action_rect(action).adjusted(-4, -4, 4, 4).contains(
                pos
            )

        if action_type == "number":
            return self._get_number_action_rect(action).adjusted(-4, -4, 4, 4).contains(
                pos
            )

        points = action.get("points", [])
        if action_type == "rect" and len(points) == 2:
            rect = QRect(points[0], points[1]).normalized()
            padding = max(8, int(action.get("thickness", 2)) + 6)
            return rect.adjusted(-padding, -padding, padding, padding).contains(pos)

        if action_type in {"line", "arrow"} and len(points) == 2:
            path = QPainterPath()
            path.moveTo(float(points[0].x()), float(points[0].y()))
            path.lineTo(float(points[1].x()), float(points[1].y()))
            stroker = QPainterPathStroker()
            stroker.setWidth(max(10.0, float(action.get("thickness", 2)) + 6.0))
            return stroker.createStroke(path).contains(QPointF(pos))

        return False

    def _add_number_action(self, pos: QPoint):
        self._record_undo_state()
        self.draw_actions.append(
            {
                "type": "number",
                "color": QColor(self.draw_color),
                "number": self._next_number_label(),
                "pos": QPoint(pos),
                "size": self._number_marker_size(self.draw_thickness),
                "thickness": max(2, min(6, self.draw_thickness)),
            }
        )
        self.update()

    def _find_movable_action_index(self, pos: QPoint):
        for index in range(len(self.draw_actions) - 1, -1, -1):
            action = self.draw_actions[index]
            if self._is_movable_action_type(action.get("type")) and self._action_contains_point(
                action, pos
            ):
                return index
        return None

    def _find_text_action_index(self, pos: QPoint):
        for index in range(len(self.draw_actions) - 1, -1, -1):
            action = self.draw_actions[index]
            if action.get("type") == "text" and self._action_contains_point(action, pos):
                return index
        return None

    def _get_screenshot_save_dir(self):
        save_dir = str(
            config_manager.get_value(
                "screenshot_save_dir",
                os.path.join(
                    os.path.expanduser("~"), "Pictures", "x-tools-screenshots"
                ),
            )
        ).strip()
        if not save_dir:
            save_dir = os.path.join(
                os.path.expanduser("~"), "Pictures", "x-tools-screenshots"
            )
        return save_dir

    def update_text_input_style(self):
        font_size = max(12, 12 + self.draw_thickness * 2)
        self.text_input.setFont(
            self._annotation_font(self.text_input.font(), font_size)
        )
        self.text_input.setStyleSheet(
            f"background: transparent; border: 1px dashed {self.draw_color.name()}; font-size: {font_size}px; color: {self.draw_color.name()}; outline: none; margin: 0; padding: 0;"
        )
        fm = self.text_input.fontMetrics()
        self.text_input.resize(
            max(100, fm.horizontalAdvance(self.text_input.text()) + 30),
            fm.height() + 10,
        )

    def commit_text_action(self):
        if self.text_input.isVisible():
            txt = self.text_input.text()
            should_record = txt.strip() or self.editing_text_snapshot is not None
            if should_record:
                self._record_undo_state(self.editing_text_snapshot)
            if txt.strip():
                action = {
                    "type": "text",
                    "color": self.draw_color,
                    "text": txt,
                    "pos": self.text_input.pos(),
                    "font_size": max(12, 12 + self.draw_thickness * 2),
                }
                if self.editing_text_index is None:
                    self.draw_actions.append(action)
                else:
                    insert_at = min(self.editing_text_index, len(self.draw_actions))
                    self.draw_actions.insert(insert_at, action)
            self.editing_text_index = None
            self.editing_text_snapshot = None
            self.text_input.clear()
            self.text_input.hide()
            self.update()

    def _prompt_manual_save_path(self):
        suggested_path = os.path.join(
            self._get_screenshot_save_dir(), self._build_screenshot_filename()
        )
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存截图到",
            suggested_path,
            "PNG 图片 (*.png)",
        )
        if not output_path:
            return None
        return self._normalize_output_path(output_path)

    def _save_pixmap_to_path(self, pixmap, output_path, source="manual"):
        output_path = self._normalize_output_path(output_path)
        started = time.perf_counter()
        ok = False
        try:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            ok = pixmap.save(output_path, "PNG")
        except Exception as e:
            logger.warning("Failed to save screenshot to %s: %s", output_path, e)

        elapsed = (time.perf_counter() - started) * 1000
        metrics_store.record(
            "screenshot.save",
            elapsed,
            {"ok": bool(ok), "path": output_path, "source": source},
        )

        if ok:
            logger.info("Screenshot saved (%s): %s", source, output_path)
            return output_path

        logger.warning("Failed to save screenshot (%s): %s", source, output_path)
        return None

    @staticmethod
    def _capture_scale(screen, pixmap):
        geometry = screen.geometry()
        scale_values = [
            float(screen.devicePixelRatio()),
            float(pixmap.devicePixelRatio()),
        ]
        if geometry.width() > 0:
            scale_values.append(float(pixmap.width()) / float(geometry.width()))
        if geometry.height() > 0:
            scale_values.append(float(pixmap.height()) / float(geometry.height()))

        return max(1.0, max(scale_values))

    @staticmethod
    def _scaled_rect(rect: QRect, scale: float) -> QRect:
        x1 = round(rect.x() * scale)
        y1 = round(rect.y() * scale)
        x2 = round((rect.x() + rect.width()) * scale)
        y2 = round((rect.y() + rect.height()) * scale)
        return QRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    def _native_rect(self, rect: QRect) -> QRect:
        return self._scaled_rect(rect, self.screen_scale)

    def _native_point(self, point: QPoint) -> QPoint:
        return QPoint(
            round(point.x() * self.screen_scale),
            round(point.y() * self.screen_scale),
        )

    def save_selection_as(self):
        output_path = self._prompt_manual_save_path()
        if output_path:
            self.finalize_capture(manual_save_path=output_path)

    def on_save_clicked(self):
        self.save_selection_as()

    def show_toolbar(self):
        self.toolbar_widget.adjustSize()
        x = self.selection_rect.right() - self.toolbar_widget.width()
        y = self.selection_rect.bottom() + 10
        if y + self.toolbar_widget.height() > self.height():
            y = self.selection_rect.top() - self.toolbar_widget.height() - 10
        if x < 0:
            x = 0
        self.toolbar_widget.move(int(x), int(y))
        self.toolbar_widget.show()
        self.toolbar_widget.raise_()

    def on_copy_clicked(self):
        self.finalize_capture(manual_copy=True)

    def on_pin_clicked(self):
        self.finalize_capture(manual_pin=True)

    def on_qr_clicked(self):
        self.recognize_qr()
        self.close_overlay()

    def capture_screen(self):
        screens = QApplication.screens()
        if not screens:
            return

        virtual_rect = screens[0].geometry()
        for screen in screens[1:]:
            virtual_rect = virtual_rect.united(screen.geometry())

        captures = []
        self.screen_scale = 1.0
        for screen in screens:
            shot = screen.grabWindow(0)
            scale = self._capture_scale(screen, shot)
            if abs(float(shot.devicePixelRatio()) - scale) > 0.01:
                shot.setDevicePixelRatio(scale)
            captures.append(
                {
                    "geometry": QRect(screen.geometry()),
                    "pixmap": shot,
                    "scale": scale,
                }
            )
            self.screen_scale = max(self.screen_scale, scale)

        native_size = QSize(
            max(1, round(virtual_rect.width() * self.screen_scale)),
            max(1, round(virtual_rect.height() * self.screen_scale)),
        )
        self.screen_virtual_rect = QRect(virtual_rect)
        self.screen_capture_sources = captures
        self.screen_pixmap = QPixmap(native_size)
        self.screen_pixmap.setDevicePixelRatio(self.screen_scale)
        self.screen_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(self.screen_pixmap)
        for capture in captures:
            offset = capture["geometry"].topLeft() - virtual_rect.topLeft()
            painter.drawPixmap(offset, capture["pixmap"])
        painter.end()

        self.screen_image = self.screen_pixmap.toImage()

        # Precompute mosaic
        self.mosaic_pixmap = self.screen_pixmap.scaled(
            max(1, self.screen_pixmap.width() // 15),
            max(1, self.screen_pixmap.height() // 15),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        ).scaled(
            self.screen_pixmap.width(),
            self.screen_pixmap.height(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

        # Reset state on new capture
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.is_drawing = False
        self.is_resizing = False
        self.resize_anchor = None
        self.selection_rect = QRect()
        self.draw_actions.clear()
        self.undo_states.clear()
        self.redo_states.clear()
        self.current_action = None
        self.draw_mode = None
        self.is_moving_action = False
        self.moving_action_index = None
        self.action_drag_last_pos = QPoint()
        self.action_drag_changed = False
        self.editing_text_index = None
        self.editing_text_snapshot = None
        if self.tool_group:
            for b in self.tool_group.buttons():
                b.setChecked(False)
        self.sub_toolbar.hide()

        self.text_input.clear()
        self.text_input.hide()
        self.toolbar_widget.hide()

        self.setGeometry(virtual_rect)
        self.show()
        self.activateWindow()

    def paintEvent(self, event):
        if not self.screen_pixmap:
            return

        painter = QPainter(self)
        self._enable_quality_rendering(painter)
        painter.drawPixmap(0, 0, self.screen_pixmap)

        # Draw darkened overlay
        overlay_color = QColor(0, 0, 0, 100)
        painter.fillRect(self.rect(), overlay_color)

        if not self.selection_rect.isNull():
            # Clear the chosen rect so it's bright
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self.selection_rect, Qt.GlobalColor.transparent)

            # Draw the chosen rect back with normal pixmap
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
            painter.drawPixmap(
                self.selection_rect,
                self.screen_pixmap,
                self._native_rect(self.selection_rect),
            )

            # Draw border
            pen = QPen(QColor(0, 174, 255), 2)
            painter.setPen(pen)
            painter.drawRect(self.selection_rect)

            # Clip drawing rendering to the selection area
            painter.setClipRect(self.selection_rect)
            self.draw_all_actions(painter)
            painter.setClipping(False)

            # Draw dimension text
            dim_text = f"{self.selection_rect.width()} x {self.selection_rect.height()}"
            painter.setPen(Qt.GlobalColor.white)

            # Explicitly set a normal font to avoid inheriting large font sizes from drawing actions
            f = painter.font()
            f.setPixelSize(12)
            f.setBold(False)
            painter.setFont(f)

            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(dim_text)
            text_rect.adjust(-5, -2, 5, 2)

            text_x = self.selection_rect.left()
            text_y = self.selection_rect.top() - text_rect.height() - 5

            if text_y < 0:
                text_y = self.selection_rect.top() + 5

            text_rect.moveTo(text_x, text_y)

            painter.fillRect(text_rect, QColor(0, 0, 0, 150))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, dim_text)

            # Draw anchor dots
            painter.setBrush(QColor(0, 174, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            r = 4
            for px, py in self.get_anchor_points():
                painter.drawEllipse(QPoint(px, py), r, r)

        if (
            self.draw_mode
            and self.draw_mode != "text"
            and self.draw_mode != "mosaic"
            and self.draw_mode != "number"
            and self.toolbar_widget.isVisible()
            and self.selection_rect.contains(self.current_mouse_pos)
        ):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                self.draw_color if self.draw_mode != "eraser" else Qt.GlobalColor.white
            )
            r = self.draw_thickness / 2
            painter.drawEllipse(QPointF(self.current_mouse_pos), r, r)

        if (
            self.draw_mode == "number"
            and self.toolbar_widget.isVisible()
            and self.selection_rect.contains(self.current_mouse_pos)
        ):
            size = self._number_marker_size(self.draw_thickness)
            rect = QRect(
                self.current_mouse_pos - QPoint(size // 2, size // 2),
                QSize(size, size),
            )
            self._draw_number_marker(
                painter,
                rect,
                self.draw_color,
                str(self._next_number_label()),
                max(2, min(6, self.draw_thickness)),
            )

        # Draw magnifier
        if not self.current_mouse_pos.isNull() and self.screen_image:
            cursor_pos = self.current_mouse_pos
            native_cursor_pos = self._native_point(cursor_pos)
            zoom_size = 15  # Must be odd to have a true center (15x15 pixels)
            scale = 12

            if self.screen_image.valid(native_cursor_pos):
                c = self.screen_image.pixelColor(native_cursor_pos)

                zoom_rect = QRect(
                    native_cursor_pos.x() - zoom_size // 2,
                    native_cursor_pos.y() - zoom_size // 2,
                    zoom_size,
                    zoom_size,
                )

                zoomed_pixmap = self.screen_pixmap.copy(zoom_rect)
                zoomed_pixmap.setDevicePixelRatio(1.0)
                zoomed_pixmap = zoomed_pixmap.scaled(
                    zoom_size * scale,
                    zoom_size * scale,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )

                mag_x = cursor_pos.x() + 20
                mag_y = cursor_pos.y() + 20
                mag_w = zoom_size * scale
                mag_h = zoom_size * scale

                # Calculate Info panel dimensions
                panel_h = 75

                # Boundary checks
                if mag_x + mag_w > self.width():
                    mag_x = cursor_pos.x() - mag_w - 40
                if mag_y + mag_h + panel_h > self.height():
                    mag_y = cursor_pos.y() - mag_h - panel_h - 40

                # 1. Draw the scaled image
                mag_rect = QRect(mag_x, mag_y, mag_w, mag_h)
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_SourceOver
                )
                painter.drawPixmap(mag_rect, zoomed_pixmap)

                # 2. Draw Crosshair bands (horizontal and vertical overlay passing through center)
                center_x = mag_x + (zoom_size // 2) * scale
                center_y = mag_y + (zoom_size // 2) * scale
                band_color = QColor(0, 174, 255, 80)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(band_color)
                # Horizontal band
                painter.drawRect(mag_x, center_y, mag_w, scale)
                # Vertical band
                painter.drawRect(center_x, mag_y, scale, mag_h)

                # 3. Draw Grid
                painter.setPen(QPen(QColor(0, 0, 0, 50), 1, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for i in range(1, zoom_size):
                    # Vertical
                    painter.drawLine(
                        mag_x + i * scale, mag_y, mag_x + i * scale, mag_y + mag_h
                    )
                    # Horizontal
                    painter.drawLine(
                        mag_x, mag_y + i * scale, mag_x + mag_w, mag_y + i * scale
                    )

                # 4. Draw Center Pixel Outline
                painter.setPen(QPen(Qt.GlobalColor.black, 1))
                painter.drawRect(center_x, center_y, scale, scale)
                painter.setPen(QPen(Qt.GlobalColor.white, 1))
                painter.drawRect(center_x + 1, center_y + 1, scale - 2, scale - 2)

                # 5. Draw Image Border
                painter.setPen(QPen(Qt.GlobalColor.black, 1))
                painter.drawRect(mag_rect)

                # 6. Draw Info Panel Background
                panel_rect = QRect(mag_x, mag_y + mag_h, mag_w, panel_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(30, 30, 30, 240))
                painter.drawRect(panel_rect)

                # 7. Draw Texts
                painter.setPen(Qt.GlobalColor.white)
                f = painter.font()
                f.setPixelSize(12)
                f.setBold(False)
                painter.setFont(f)

                # Line 1: coordinates
                global_pos = self.mapToGlobal(cursor_pos)
                coord_text = f"({global_pos.x()}, {global_pos.y()})"
                painter.drawText(
                    QRect(mag_x, mag_y + mag_h + 5, mag_w, 15),
                    Qt.AlignmentFlag.AlignCenter,
                    coord_text,
                )

                # Line 2: color box + text
                color_text = (
                    f"rgb({c.red()}, {c.green()}, {c.blue()})"
                    if self.color_format == "rgb"
                    else c.name().upper()
                )
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(color_text)
                box_size = 12
                spacing = 5
                total_w = box_size + spacing + tw
                start_x = mag_x + (mag_w - total_w) // 2

                # Draw color box
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(c)
                painter.drawRect(start_x, mag_y + mag_h + 24, box_size, box_size)
                painter.setPen(QPen(Qt.GlobalColor.white, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(start_x, mag_y + mag_h + 24, box_size, box_size)

                # Draw color text
                painter.drawText(
                    start_x + box_size + spacing,
                    mag_y + mag_h + 23,
                    tw,
                    15,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    color_text,
                )

                # Line 3: Shift Hint
                f.setPixelSize(11)
                painter.setFont(f)
                painter.setPen(QColor(200, 200, 200))
                painter.drawText(
                    QRect(mag_x, mag_y + mag_h + 40, mag_w, 15),
                    Qt.AlignmentFlag.AlignCenter,
                    "Shift: 切换颜色格式",
                )

                # Line 4: Copy Hint
                painter.drawText(
                    QRect(mag_x, mag_y + mag_h + 55, mag_w, 15),
                    Qt.AlignmentFlag.AlignCenter,
                    "C: 复制色值",
                )

    def draw_all_actions(self, painter):
        self._enable_quality_rendering(painter)
        actions = self.draw_actions.copy()
        if self.current_action:
            actions.append(self.current_action)

        for act in actions:
            pts = act.get("points", [])
            color = act.get("color", Qt.GlobalColor.red)
            t = act.get("type")
            thickness = act.get("thickness", 2)

            painter.setPen(
                QPen(
                    color,
                    thickness,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)

            if t == "rect" and len(pts) == 2:
                rect = QRect(pts[0], pts[1]).normalized()
                painter.drawRoundedRect(
                    QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 2, 2
                )
            elif t == "line" and len(pts) == 2:
                painter.drawLine(QPointF(pts[0]), QPointF(pts[1]))
            elif t == "arrow" and len(pts) == 2:
                self._draw_arrow(painter, pts[0], pts[1], color, thickness)
            elif t == "pen" and len(pts) > 1:
                painter.drawPath(self._smooth_path(pts))
            elif t == "text":
                painter.setPen(act["color"])
                font_size = act.get("font_size", 18)
                painter.setFont(self._annotation_font(painter.font(), font_size))
                fm = painter.fontMetrics()
                # To match QLineEdit visual position alignment approximately
                painter.drawText(act["pos"] + QPoint(2, fm.ascent() + 2), act["text"])
            elif t == "number":
                rect = self._get_number_action_rect(act)
                outline_width = max(1, int(act.get("thickness", 2)))
                self._draw_number_marker(
                    painter,
                    rect,
                    act.get("color", QColor("#FF3333")),
                    str(act.get("number", 1)),
                    outline_width,
                )
            elif t in ["mosaic", "eraser"] and len(pts) > 1:
                stroker = QPainterPathStroker()
                stroker.setWidth(15)
                stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

                path = self._smooth_path(pts)

                s_path = stroker.createStroke(path)
                painter.setClipPath(s_path)
                if t == "mosaic" and self.mosaic_pixmap:
                    painter.drawPixmap(0, 0, self.mosaic_pixmap)
                elif t == "eraser" and self.screen_pixmap:
                    painter.drawPixmap(0, 0, self.screen_pixmap)
                # Reset clip
                painter.setClipRect(self.selection_rect)

    def get_anchor_points(self):
        if self.selection_rect.isNull():
            return []
        r = self.selection_rect
        return [
            (r.left(), r.top()),
            (r.center().x(), r.top()),
            (r.right(), r.top()),
            (r.right(), r.center().y()),
            (r.right(), r.bottom()),
            (r.center().x(), r.bottom()),
            (r.left(), r.bottom()),
            (r.left(), r.center().y()),
        ]

    def get_anchor(self, pos: QPoint):
        if self.selection_rect.isNull():
            return None

        margin = 10
        rect = self.selection_rect

        if (pos - rect.topLeft()).manhattanLength() < margin:
            return "tl"
        if (pos - rect.topRight()).manhattanLength() < margin:
            return "tr"
        if (pos - rect.bottomLeft()).manhattanLength() < margin:
            return "bl"
        if (pos - rect.bottomRight()).manhattanLength() < margin:
            return "br"

        if (
            abs(pos.x() - rect.left()) < margin
            and rect.top() <= pos.y() <= rect.bottom()
        ):
            return "l"
        if (
            abs(pos.x() - rect.right()) < margin
            and rect.top() <= pos.y() <= rect.bottom()
        ):
            return "r"
        if (
            abs(pos.y() - rect.top()) < margin
            and rect.left() <= pos.x() <= rect.right()
        ):
            return "t"
        if (
            abs(pos.y() - rect.bottom()) < margin
            and rect.left() <= pos.x() <= rect.right()
        ):
            return "b"

        return None

    def update_cursor(self, pos):
        if not self.is_drawing and not self.is_resizing and not self.is_moving_action:
            anchor = self.get_anchor(pos)
            if anchor in ["tl", "br"]:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif anchor in ["tr", "bl"]:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif anchor in ["l", "r"]:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif anchor in ["t", "b"]:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif (
                self.selection_rect.contains(pos)
                and self.draw_mode != "text"
                and self._find_movable_action_index(pos) is not None
            ):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif (
                self.draw_mode == "text"
                and self.selection_rect.contains(pos)
                and self._find_text_action_index(pos) is not None
            ):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self.draw_mode == "text" and self.selection_rect.contains(pos):
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event):
        adjustable_modes = {
            "rect",
            "line",
            "arrow",
            "pen",
            "text",
            "number",
            "mosaic",
            "eraser",
        }
        if not self.selection_rect.isNull() and self.draw_mode in adjustable_modes:
            delta = event.angleDelta().y()
            if delta > 0:
                self.set_draw_thickness(self.draw_thickness + 2)
            elif delta < 0:
                self.set_draw_thickness(self.draw_thickness - 2)

            if self.draw_mode == "text" and self.text_input.isVisible():
                self.update_text_input_style()

            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()

            if not self.selection_rect.isNull() and self.selection_rect.contains(pos):
                if self.draw_mode == "text":
                    text_index = self._find_text_action_index(pos)
                    if text_index is not None:
                        if self.text_input.isVisible():
                            self.commit_text_action()
                        self.is_moving_action = True
                        self.moving_action_index = text_index
                        self.action_drag_last_pos = pos
                        self.action_drag_changed = False
                        self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    else:
                        if self.text_input.isVisible():
                            self.commit_text_action()
                        self.text_input.move(pos)
                        self.text_input.setText("")
                        self.editing_text_index = None
                        self.editing_text_snapshot = None
                        self.update_text_input_style()
                        self.text_input.show()
                        self.text_input.setFocus()
                    return

                action_index = self._find_movable_action_index(pos)
                if action_index is not None:
                    if self.text_input.isVisible():
                        self.commit_text_action()
                    self.is_moving_action = True
                    self.moving_action_index = action_index
                    self.action_drag_last_pos = pos
                    self.action_drag_changed = False
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return

                if self.draw_mode == "number":
                    if self.text_input.isVisible():
                        self.commit_text_action()
                    self._add_number_action(pos)
                    return

                if self.draw_mode:
                    self.current_action = {
                        "type": self.draw_mode,
                        "color": self.draw_color,
                        "points": [pos],
                        "thickness": self.draw_thickness,
                    }
                    return

            anchor = self.get_anchor(pos)
            if anchor and not self.selection_rect.isNull():
                self.is_resizing = True
                self.resize_anchor = anchor
                if self.text_input.isVisible():
                    self.commit_text_action()
                self.toolbar_widget.hide()
            elif not self.selection_rect.isNull() and (
                self.draw_actions or self.text_input.isVisible()
            ):
                if self.text_input.isVisible():
                    self.commit_text_action()
                self.is_drawing = False
                self.current_action = None
                self.show_toolbar()
                self.update_cursor(pos)
                self.update()
                return
            else:
                self.start_pos = pos
                self.end_pos = self.start_pos
                self.is_drawing = True
                self.selection_rect = QRect()
                if self.text_input.isVisible():
                    self.commit_text_action()
                self.toolbar_widget.hide()
                self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            if not self.selection_rect.isNull():
                # Clear selection
                self.selection_rect = QRect()
                self.toolbar_widget.hide()
                self.update()
            else:
                # Close overlay
                self.close_overlay()

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseDoubleClickEvent(event)

        pos = event.position().toPoint()
        if (
            self.draw_mode == "text"
            and not self.selection_rect.isNull()
            and self.selection_rect.contains(pos)
        ):
            text_index = self._find_text_action_index(pos)
            if text_index is not None:
                if self.text_input.isVisible():
                    self.commit_text_action()
                action = self.draw_actions[text_index]
                self.editing_text_snapshot = self._clone_draw_actions()
                self.editing_text_index = text_index
                self.text_input.move(action["pos"])
                self.text_input.setText(action["text"])
                self.draw_color = QColor(action["color"])
                self.draw_thickness = max(2, (action.get("font_size", 18) - 12) // 2)
                self.update_text_input_style()
                self.text_input.show()
                self.text_input.setFocus()
                self.draw_actions.pop(text_index)
                self.is_moving_action = False
                self.moving_action_index = None
                self.action_drag_last_pos = QPoint()
                self.action_drag_changed = False
                self.update()
                return

        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self.current_mouse_pos = pos

        if self.current_action:
            if self.current_action["type"] in ["rect", "line", "arrow"]:
                if len(self.current_action["points"]) > 1:
                    self.current_action["points"][1] = pos
                else:
                    self.current_action["points"].append(pos)
            elif self.current_action["type"] in ["pen", "mosaic", "eraser"]:
                self.current_action["points"].append(pos)
        elif self.is_moving_action and self.moving_action_index is not None:
            delta = pos - self.action_drag_last_pos
            if not delta.isNull():
                if not self.action_drag_changed:
                    self._record_undo_state()
                    self.action_drag_changed = True
                self._translate_action(self.draw_actions[self.moving_action_index], delta)
                self.action_drag_last_pos = pos
        elif self.is_drawing:
            self.end_pos = pos
            self.selection_rect = QRect(self.start_pos, self.end_pos).normalized()
            self.toolbar_widget.hide()
        elif self.is_resizing:
            rect = self.selection_rect
            if self.resize_anchor == "tl":
                rect.setTopLeft(pos)
            elif self.resize_anchor == "tr":
                rect.setTopRight(pos)
            elif self.resize_anchor == "bl":
                rect.setBottomLeft(pos)
            elif self.resize_anchor == "br":
                rect.setBottomRight(pos)
            elif self.resize_anchor == "t":
                rect.setTop(pos.y())
            elif self.resize_anchor == "b":
                rect.setBottom(pos.y())
            elif self.resize_anchor == "l":
                rect.setLeft(pos.x())
            elif self.resize_anchor == "r":
                rect.setRight(pos.x())
            self.selection_rect = rect.normalized()
        else:
            self.update_cursor(pos)

        self.update()  # Update to render magnifier at all times

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.current_action:
                self._record_undo_state()
                self.draw_actions.append(self.current_action)
                self.current_action = None
                self.update()
                return

            if self.is_moving_action:
                self.is_moving_action = False
                self.moving_action_index = None
                self.action_drag_last_pos = QPoint()
                self.action_drag_changed = False
                self.update_cursor(event.position().toPoint())
                self.update()
                return

            self.is_drawing = False
            self.is_resizing = False
            self.resize_anchor = None
            if (
                not self.selection_rect.isNull()
                and self.selection_rect.width() > 10
                and self.selection_rect.height() > 10
            ):
                self.show_toolbar()
            else:
                self.toolbar_widget.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close_overlay()
        elif event.key() == Qt.Key.Key_Shift:
            self.color_format = "hex" if self.color_format == "rgb" else "rgb"
            self.update()
        elif (
            event.key() == Qt.Key.Key_Z
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.undo_action()
        elif (
            event.key() == Qt.Key.Key_Y
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
        ):
            self.redo_action()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            self.redo_action()
        elif (
            event.matches(QKeySequence.StandardKey.Save)
            and not self.selection_rect.isNull()
        ):
            self.save_selection_as()
        elif (
            event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter
        ) and not self.selection_rect.isNull():
            self.finalize_capture(manual_copy=True)
        elif event.key() == Qt.Key.Key_P and not self.selection_rect.isNull():
            self.finalize_capture(manual_pin=True)
        elif (
            event.key() == Qt.Key.Key_C
            and not self.current_mouse_pos.isNull()
            and self.screen_image
        ):
            native_mouse_pos = self._native_point(self.current_mouse_pos)
            if self.screen_image.valid(native_mouse_pos):
                c = self.screen_image.pixelColor(native_mouse_pos)
                text = (
                    f"rgb({c.red()}, {c.green()}, {c.blue()})"
                    if self.color_format == "rgb"
                    else c.name().upper()
                )
                QApplication.clipboard().setText(text)
                # Quick visual feedback by showing a small tip?
                # A bit complex to do a temporary toast without a dedicated mechanism.
                # Just updating the clipboard is fine.
        elif event.key() == Qt.Key.Key_Q and not self.selection_rect.isNull():
            self.recognize_qr()
            self.close_overlay()

    def get_selected_pixmap(self):
        if self.selection_rect.isNull() or not self.screen_pixmap:
            return None

        if self.text_input.isVisible():
            self.commit_text_action()

        pixmap = self._copy_selected_native_pixmap()
        if hasattr(self, "draw_actions") and self.draw_actions:
            painter = QPainter(pixmap)
            painter.translate(-self.selection_rect.topLeft())
            self.draw_all_actions(painter)
            painter.end()

        return pixmap

    def _copy_selected_native_pixmap(self):
        selection_rect = QRect(self.selection_rect)
        selection_global = QRect(selection_rect)
        selection_global.translate(self.screen_virtual_rect.topLeft())

        matches = []
        for capture in self.screen_capture_sources:
            screen_rect = capture["geometry"]
            intersection = selection_global.intersected(screen_rect)
            if (
                not intersection.isNull()
                and intersection.width() > 0
                and intersection.height() > 0
            ):
                matches.append((capture, intersection))

        if len(matches) == 1:
            capture, intersection = matches[0]
            source_rect = QRect(intersection)
            source_rect.translate(-capture["geometry"].topLeft())
            pixmap = capture["pixmap"].copy(
                self._scaled_rect(source_rect, capture["scale"])
            )
            pixmap.setDevicePixelRatio(capture["scale"])
            return pixmap

        return self.screen_pixmap.copy(self._native_rect(selection_rect))

    def pin_selection(self):
        pixmap = self.get_selected_pixmap()
        if pixmap:
            self._pin_pixmap(pixmap)

    def copy_selection(self):
        pixmap = self.get_selected_pixmap()
        if pixmap:
            QApplication.clipboard().setPixmap(pixmap)

    def _build_screenshot_filename(self):
        template = str(
            config_manager.get_value(
                "screenshot_filename_template", "x-tools_{date}_{time}"
            )
        ).strip()
        if not template:
            template = "x-tools_{date}_{time}"

        now = datetime.now()
        safe_name = (
            template.replace("{date}", now.strftime("%Y%m%d"))
            .replace("{time}", now.strftime("%H%M%S"))
            .replace("{datetime}", now.strftime("%Y%m%d_%H%M%S"))
        )

        invalid_chars = '<>:"/\\|?*'
        for ch in invalid_chars:
            safe_name = safe_name.replace(ch, "_")

        safe_name = safe_name.strip().strip(".")
        if not safe_name:
            safe_name = f"x-tools_{now.strftime('%Y%m%d_%H%M%S')}"
        return safe_name + ".png"

    def _auto_save_pixmap(self, pixmap):
        if not config_manager.get_value("screenshot_auto_save", False):
            return None

        output_path = os.path.join(
            self._get_screenshot_save_dir(), self._build_screenshot_filename()
        )
        return self._save_pixmap_to_path(pixmap, output_path, source="auto")

    def _pin_pixmap(self, pixmap):
        pin_win = PinnedImageWindow(pixmap)

        global_top_left = self.mapToGlobal(self.selection_rect.topLeft())
        pin_win.move(global_top_left - QPoint(15, 15))
        pin_win.show()

        from PyQt6.QtCore import QTimer

        QTimer.singleShot(100, pin_win.recognize_text)
        self.pinned_windows.append(pin_win)

    def finalize_capture(
        self, manual_copy=False, manual_pin=False, manual_save_path=None
    ):
        pixmap = self.get_selected_pixmap()
        if not pixmap:
            return

        auto_copy = bool(config_manager.get_value("screenshot_auto_copy", False))
        auto_pin = bool(config_manager.get_value("screenshot_auto_pin", False))
        saved_path = ""
        actions = []

        if manual_save_path:
            saved_path = self._save_pixmap_to_path(
                pixmap, manual_save_path, source="manual"
            )
            if not saved_path:
                QMessageBox.warning(
                    self,
                    "保存失败",
                    f"无法保存截图到:\n{manual_save_path}",
                )
                return
            actions.append("save")

        if manual_copy or auto_copy:
            QApplication.clipboard().setPixmap(pixmap)
            actions.append("copy")

        if manual_pin or auto_pin:
            self._pin_pixmap(pixmap)
            actions.append("pin")

        if not manual_save_path:
            saved_path = self._auto_save_pixmap(pixmap) or ""
            if saved_path:
                actions.append("save")

        source = "manual" if any([manual_copy, manual_pin, manual_save_path]) else "auto"
        capture_history_manager.add_capture(
            pixmap,
            source=source,
            saved_path=saved_path,
            actions=actions,
        )
        self.close_overlay()

    def recognize_qr(self):
        pixmap = self.get_selected_pixmap()
        if not pixmap or not CV2_AVAILABLE:
            return

        import cv2 as cv2_mod
        import numpy as np_mod

        image = pixmap.toImage()
        width = image.width()
        height = image.height()

        # Format_ARGB32 -> 32-bit Depth -> BGRA
        # Note: Depending on Qt Image format it might be RGB32 or ARGB32
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        buffer = ptr.asstring()

        try:
            # Create a numpy array from the buffer
            arr = np_mod.frombuffer(buffer, dtype=np_mod.uint8).reshape(
                (height, width, 4)
            )
            # Convert BGRA to grayscale for QR detection
            gray = cv2_mod.cvtColor(arr, cv2_mod.COLOR_BGRA2GRAY)

            detector = cv2_mod.QRCodeDetector()
            data, bbox, straight_qrcode = detector.detectAndDecode(gray)

            if data:
                QApplication.clipboard().setText(data)
                logger.info("QR decoded and copied to clipboard")
        except Exception as e:
            logger.warning("QR decode error: %s", e)

    def close_overlay(self):
        self.is_moving_action = False
        self.moving_action_index = None
        self.action_drag_last_pos = QPoint()
        self.action_drag_changed = False
        self.hide()
        self.closed.emit()
