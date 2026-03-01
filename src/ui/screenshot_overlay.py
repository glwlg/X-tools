from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal, QSize
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QPainterPath,
    QPainterPathStroker,
    QIcon,
    QPixmap,
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
)
from datetime import datetime
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
        self.draw_actions = []
        self.current_action = None
        self.mosaic_pixmap = None

        self.text_input = QLineEdit(self)
        self.text_input.hide()
        self.text_input.setStyleSheet(
            "background: transparent; border: none; font-size: 18px; color: #FF3333; outline: none; margin: 0; padding: 0;"
        )
        self.text_input.returnPressed.connect(self.commit_text_action)

        # For undo mechanism
        self.redo_actions = []

        self.init_toolbar()

    def create_icon(self, mode):
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))

        if mode == "rect":
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

        painter.end()
        return QIcon(pixmap)

    def init_toolbar(self):
        # Main overlay container for toolbar
        self.toolbar_widget = QFrame(self)
        self.toolbar_widget.setStyleSheet(
            "QFrame#MainFrame { background-color: #2D2D2D; border: 1px solid #555; border-radius: 6px; }"
            "QPushButton { background-color: transparent; color: white; border: none; padding: 6px 12px; font-weight: bold; font-family: 'Segoe UI', sans-serif; }"
            "QPushButton:hover { background-color: #444; border-radius: 4px; }"
            "QPushButton:checked { background-color: #555; border-radius: 4px; color: #00AEFF; }"
            "QFrame#SubFrame { background-color: #383838; border: 1px solid #555; border-radius: 6px; margin-top: 5px; }"
        )
        self.toolbar_widget.setObjectName("MainFrame")

        main_layout = QVBoxLayout(self.toolbar_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sub Toolbar (Colors & Thickness)
        self.sub_toolbar = QFrame()
        self.sub_toolbar.setObjectName("SubFrame")
        sub_layout = QHBoxLayout(self.sub_toolbar)
        sub_layout.setContentsMargins(10, 5, 10, 5)

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
        self.color_group = QButtonGroup(self)
        for i, h in enumerate(colors):
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {h}; border: 2px solid transparent; border-radius: 9px; }}
                QPushButton:checked {{ border: 2px solid white; }}
                QPushButton:hover {{ border: 2px solid #888; }}
            """)
            btn.clicked.connect(lambda checked, c=h: self.set_draw_color(c))
            self.color_group.addButton(btn, i)
            sub_layout.addWidget(btn)
            if i == 0:
                btn.setChecked(True)

        sub_layout.addSpacing(15)

        # Thickness hint
        from PyQt6.QtWidgets import QLabel

        hint_label = QLabel("滚轮调节粗细")
        hint_label.setStyleSheet("color: #AAA; font-size: 11px;")
        sub_layout.addWidget(hint_label)

        main_layout.addWidget(self.sub_toolbar)
        self.sub_toolbar.hide()

        # Tools Row
        self.tools_row = QFrame()
        tools_layout = QHBoxLayout(self.tools_row)
        tools_layout.setContentsMargins(5, 5, 5, 5)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(False)

        def create_tool(name, mode):
            btn = QPushButton()
            btn.setIcon(self.create_icon(mode))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(name)
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda checked, m=mode, b=btn: self.handle_tool_click(b, m)
            )
            self.tool_group.addButton(btn)
            return btn

        btn_rect = create_tool("矩形", "rect")
        btn_line = create_tool("直线", "line")
        btn_arrow = create_tool("箭头", "arrow")
        btn_pen = create_tool("画笔", "pen")
        btn_mosaic = create_tool("马赛克", "mosaic")
        btn_text = create_tool("文字", "text")
        btn_eraser = create_tool("橡皮擦", "eraser")

        tools_layout.addWidget(btn_rect)
        tools_layout.addWidget(btn_line)
        tools_layout.addWidget(btn_arrow)
        tools_layout.addWidget(btn_pen)
        tools_layout.addWidget(btn_mosaic)
        tools_layout.addWidget(btn_text)
        tools_layout.addWidget(btn_eraser)

        btn_undo = QPushButton()
        btn_undo.setIcon(self.create_icon("undo"))
        btn_undo.setIconSize(QSize(18, 18))
        btn_undo.setToolTip("撤销")
        btn_undo.clicked.connect(self.undo_action)
        tools_layout.addWidget(btn_undo)

        btn_redo = QPushButton()
        btn_redo.setIcon(self.create_icon("redo"))
        btn_redo.setIconSize(QSize(18, 18))
        btn_redo.setToolTip("重做")
        btn_redo.clicked.connect(self.redo_action)
        tools_layout.addWidget(btn_redo)

        tools_layout.addSpacing(10)

        btn_copy = QPushButton()
        btn_copy.setIcon(self.create_icon("copy"))
        btn_copy.setIconSize(QSize(18, 18))
        btn_copy.setToolTip("复制到剪贴板 (Enter)")
        btn_copy.clicked.connect(self.on_copy_clicked)

        btn_pin = QPushButton()
        btn_pin.setIcon(self.create_icon("pin"))
        btn_pin.setIconSize(QSize(18, 18))
        btn_pin.setToolTip("贴图 (P)")
        btn_pin.clicked.connect(self.on_pin_clicked)

        btn_qr = QPushButton()
        btn_qr.setIcon(self.create_icon("qr"))
        btn_qr.setIconSize(QSize(18, 18))
        btn_qr.setToolTip("扫码 (Q)")
        btn_qr.clicked.connect(self.on_qr_clicked)

        btn_cancel = QPushButton()
        btn_cancel.setIcon(self.create_icon("close"))
        btn_cancel.setIconSize(QSize(18, 18))
        btn_cancel.setToolTip("退出 (Esc)")
        btn_cancel.clicked.connect(self.close_overlay)

        tools_layout.addWidget(btn_pin)
        tools_layout.addWidget(btn_qr)
        tools_layout.addWidget(btn_cancel)
        tools_layout.addWidget(btn_copy)

        main_layout.addWidget(self.tools_row)
        self.toolbar_widget.hide()

    def set_draw_color(self, color_hex):
        self.draw_color = QColor(color_hex)
        self.text_input.setStyleSheet(
            f"background: transparent; border: none; font-size: 18px; color: {color_hex}; outline: none; margin: 0; padding: 0;"
        )

    def set_draw_thickness(self, val):
        self.draw_thickness = val

    def handle_tool_click(self, btn, mode):
        # Enforce exclusivity manually to allow unchecking
        if btn.isChecked():
            for b in self.tool_group.buttons():
                if b != btn:
                    b.setChecked(False)
            self.draw_mode = mode
            if mode in ["rect", "line", "arrow", "pen", "text"]:
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
        if self.draw_actions:
            self.redo_actions.append(self.draw_actions.pop())
            self.update()

    def redo_action(self):
        if self.redo_actions:
            self.draw_actions.append(self.redo_actions.pop())
            self.update()

    def update_text_input_style(self):
        font_size = max(12, 12 + self.draw_thickness * 2)
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
            if txt.strip():
                self.draw_actions.append(
                    {
                        "type": "text",
                        "color": self.draw_color,
                        "text": txt,
                        "pos": self.text_input.pos(),
                        "font_size": max(12, 12 + self.draw_thickness * 2),
                    }
                )
                self.redo_actions.clear()
            self.text_input.clear()
            self.text_input.hide()
            self.update()

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

        self.screen_pixmap = QPixmap(virtual_rect.size())
        self.screen_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(self.screen_pixmap)
        for screen in screens:
            shot = screen.grabWindow(0)
            offset = screen.geometry().topLeft() - virtual_rect.topLeft()
            painter.drawPixmap(offset, shot)
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
        self.redo_actions.clear()
        self.current_action = None
        self.draw_mode = None
        if self.tool_group:
            for b in self.tool_group.buttons():
                b.setChecked(False)
        self.sub_toolbar.hide()

        self.text_input.hide()
        self.toolbar_widget.hide()

        self.setGeometry(virtual_rect)
        self.show()
        self.activateWindow()

    def paintEvent(self, event):
        if not self.screen_pixmap:
            return

        painter = QPainter(self)
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
                self.selection_rect, self.screen_pixmap, self.selection_rect
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
            and self.toolbar_widget.isVisible()
            and self.selection_rect.contains(self.current_mouse_pos)
        ):
            from PyQt6.QtCore import QPointF

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                self.draw_color if self.draw_mode != "eraser" else Qt.GlobalColor.white
            )
            r = self.draw_thickness / 2
            painter.drawEllipse(QPointF(self.current_mouse_pos), r, r)

        # Draw magnifier
        if not self.current_mouse_pos.isNull() and self.screen_image:
            cursor_pos = self.current_mouse_pos
            zoom_size = 15  # Must be odd to have a true center (15x15 pixels)
            scale = 12

            if self.screen_image.valid(cursor_pos):
                c = self.screen_image.pixelColor(cursor_pos)

                zoom_rect = QRect(
                    cursor_pos.x() - zoom_size // 2,
                    cursor_pos.y() - zoom_size // 2,
                    zoom_size,
                    zoom_size,
                )

                zoomed_pixmap = self.screen_pixmap.copy(zoom_rect)
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

            if t == "rect" and len(pts) == 2:
                painter.drawRect(QRect(pts[0], pts[1]))
            elif t == "line" and len(pts) == 2:
                painter.drawLine(pts[0], pts[1])
            elif t == "arrow" and len(pts) == 2:
                p1, p2 = pts[0], pts[1]
                painter.drawLine(p1, p2)
                # Arrow head math
                import math

                angle = math.atan2(p1.y() - p2.y(), p1.x() - p2.x())
                m = 12
                p3 = QPoint(
                    int(p2.x() + m * math.cos(angle + 0.5)),
                    int(p2.y() + m * math.sin(angle + 0.5)),
                )
                p4 = QPoint(
                    int(p2.x() + m * math.cos(angle - 0.5)),
                    int(p2.y() + m * math.sin(angle - 0.5)),
                )
                painter.drawLine(p2, p3)
                painter.drawLine(p2, p4)
            elif t == "pen" and len(pts) > 1:
                painter.drawPolyline(*pts)
            elif t == "text":
                painter.setPen(act["color"])
                f = painter.font()
                font_size = act.get("font_size", 18)
                f.setPixelSize(font_size)
                painter.setFont(f)
                fm = painter.fontMetrics()
                # To match QLineEdit visual position alignment approximately
                painter.drawText(act["pos"] + QPoint(2, fm.ascent() + 2), act["text"])
            elif t in ["mosaic", "eraser"] and len(pts) > 1:
                stroker = QPainterPathStroker()
                stroker.setWidth(15)
                stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

                path = QPainterPath()
                path.moveTo(float(pts[0].x()), float(pts[0].y()))
                for p in pts[1:]:
                    path.lineTo(float(p.x()), float(p.y()))

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
        if not self.is_drawing and not self.is_resizing:
            anchor = self.get_anchor(pos)
            if anchor in ["tl", "br"]:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif anchor in ["tr", "bl"]:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif anchor in ["l", "r"]:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif anchor in ["t", "b"]:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event):
        if not self.selection_rect.isNull() and self.draw_mode:
            delta = event.angleDelta().y()
            if delta > 0:
                self.draw_thickness = min(50, self.draw_thickness + 2)
            elif delta < 0:
                self.draw_thickness = max(2, self.draw_thickness - 2)

            if self.draw_mode == "text" and self.text_input.isVisible():
                self.update_text_input_style()

            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()

            # Handle Drawing
            if (
                self.draw_mode
                and not self.selection_rect.isNull()
                and self.selection_rect.contains(pos)
            ):
                if self.draw_mode == "text":
                    # Check if clicking on an existing text to edit it
                    clicked_existing = False
                    for i, act in enumerate(self.draw_actions):
                        if act["type"] == "text":
                            # Extremely basic hit test
                            act_pos = act["pos"]
                            # roughly estimate bounding box based on length and font size
                            font_size = act.get("font_size", 18)
                            est_width = len(act["text"]) * font_size
                            est_height = font_size + 10
                            if (
                                act_pos.x() <= pos.x() <= act_pos.x() + est_width
                                and act_pos.y() <= pos.y() <= act_pos.y() + est_height
                            ):
                                # Re-open this text
                                self.text_input.move(act_pos)
                                self.text_input.setText(act["text"])
                                self.text_input.show()
                                self.text_input.setFocus()
                                # Remove from actions
                                self.draw_actions.pop(i)
                                clicked_existing = True
                                break

                    if not clicked_existing:
                        # Commit any existing text before starting new
                        if self.text_input.isVisible():
                            # Only abort moving to a new spot if we're clicking inside the current box
                            # But wait, QLineEdit consumes its own clicks. So if we get a mouse press here,
                            # it means we clicked outside the line edit. We should commit and then start new.
                            self.commit_text_action()
                        self.text_input.move(pos)
                        self.text_input.setText("")
                        self.text_input.show()
                        self.text_input.setFocus()
                    return
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
                self.draw_actions.append(self.current_action)
                self.redo_actions.clear()
                self.current_action = None
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
            if self.screen_image.valid(self.current_mouse_pos):
                c = self.screen_image.pixelColor(self.current_mouse_pos)
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

        pixmap = self.screen_pixmap.copy(self.selection_rect)
        if hasattr(self, "draw_actions") and self.draw_actions:
            painter = QPainter(pixmap)
            painter.translate(-self.selection_rect.topLeft())
            self.draw_all_actions(painter)
            painter.end()

        return pixmap

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

        os.makedirs(save_dir, exist_ok=True)
        file_name = self._build_screenshot_filename()
        output_path = os.path.join(save_dir, file_name)

        started = time.perf_counter()
        ok = pixmap.save(output_path, "PNG")
        elapsed = (time.perf_counter() - started) * 1000
        metrics_store.record(
            "screenshot.save",
            elapsed,
            {"ok": bool(ok), "path": output_path},
        )

        if ok:
            logger.info("Screenshot saved: %s", output_path)
            return output_path

        logger.warning("Failed to save screenshot: %s", output_path)
        return None

    def _pin_pixmap(self, pixmap):
        pin_win = PinnedImageWindow(pixmap)

        global_top_left = self.mapToGlobal(self.selection_rect.topLeft())
        pin_win.move(global_top_left - QPoint(15, 15))
        pin_win.show()

        from PyQt6.QtCore import QTimer

        QTimer.singleShot(100, pin_win.recognize_text)
        self.pinned_windows.append(pin_win)

    def finalize_capture(self, manual_copy=False, manual_pin=False):
        pixmap = self.get_selected_pixmap()
        if not pixmap:
            return

        auto_copy = bool(config_manager.get_value("screenshot_auto_copy", False))
        auto_pin = bool(config_manager.get_value("screenshot_auto_pin", False))

        if manual_copy or auto_copy:
            QApplication.clipboard().setPixmap(pixmap)

        if manual_pin or auto_pin:
            self._pin_pixmap(pixmap)

        self._auto_save_pixmap(pixmap)
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
        self.hide()
        self.closed.emit()
