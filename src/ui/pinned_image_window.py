from PyQt6.QtCore import Qt, QPoint, QThread, pyqtSignal, QRect
from PyQt6.QtGui import QPixmap, QAction, QColor, QPainter, QImage
from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QMenu,
    QLabel,
    QVBoxLayout,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
)


class OCRWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap

    def run(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            import numpy as np

            ocr = RapidOCR()
            image = self.pixmap.toImage()
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
            width, height = image.width(), image.height()

            ptr = image.bits()
            ptr.setsize(image.sizeInBytes())
            arr = np.frombuffer(ptr.asstring(), dtype=np.uint8).reshape(
                (height, width, 4)
            )
            arr = arr[:, :, :3]  # Drop alpha channel

            result, elapse = ocr(arr)
            if result:
                self.finished.emit(result)
            else:
                self.finished.emit([])
        except Exception as e:
            self.error.emit(str(e))


class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale_factor = 1.0
        self.ocr_lines = []
        self.is_selecting = False
        self.selection_start = None
        self.selection_end = None
        self.has_selection = False

    def set_ocr_results(self, results):
        self.ocr_lines = []
        for res in results:
            box = res[0]
            text = res[1]
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            x_min = min(x_coords)
            y_min = min(y_coords)
            w = max(x_coords) - x_min
            h = max(y_coords) - y_min
            self.ocr_lines.append({"text": text, "rect": (x_min, y_min, w, h)})
        self.selection_start = None
        self.selection_end = None
        self.has_selection = False
        self.update()

    def set_scale(self, scale_factor):
        self.scale_factor = scale_factor
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            clicked_text = False
            for line in self.ocr_lines:
                x, y, w, h = line["rect"]
                sx, sy, sw, sh = (
                    int(x * self.scale_factor),
                    int(y * self.scale_factor),
                    int(w * self.scale_factor),
                    int(h * self.scale_factor),
                )
                if QRect(sx, sy, sw, sh).contains(pos):
                    clicked_text = True
                    break

            if clicked_text:
                self.is_selecting = True
                self.selection_start = pos
                self.selection_end = pos
                self.has_selection = True
                event.accept()
                self.update()
                return
            else:
                self.has_selection = False
                self.update()

        event.ignore()

    def mouseMoveEvent(self, event):
        if self.is_selecting and (event.buttons() & Qt.MouseButton.LeftButton):
            self.selection_end = event.pos()
            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if self.is_selecting and event.button() == Qt.MouseButton.LeftButton:
            self.selection_end = event.pos()
            self.is_selecting = False
            self.copy_selection()
            self.update()
            event.accept()
        else:
            event.ignore()

    def copy_selection(self):
        if not self.has_selection or not self.selection_start or not self.selection_end:
            return

        sorted_lines = sorted(
            self.ocr_lines, key=lambda l: (l["rect"][1], l["rect"][0])
        )
        selected_texts = []

        # Determine logical start and end points (top-to-bottom, left-to-right)
        start_pt = self.selection_start
        end_pt = self.selection_end
        if start_pt.y() > end_pt.y() or (
            start_pt.y() == end_pt.y() and start_pt.x() > end_pt.x()
        ):
            start_pt, end_pt = end_pt, start_pt

        for line in sorted_lines:
            x, y, w, h = line["rect"]
            sx = int(x * self.scale_factor)
            sy = int(y * self.scale_factor)
            sw = int(w * self.scale_factor)
            sh = int(h * self.scale_factor)
            line_rect = QRect(sx, sy, sw, sh)

            # Check if line is vertically within the selection range
            line_centerY = sy + sh / 2

            # If the current line is above the selection start line
            if line_rect.bottom() < start_pt.y():
                continue
            # If the current line is below the selection end line
            if line_rect.top() > end_pt.y():
                break

            text_len = len(line["text"])
            if text_len == 0:
                continue

            char_w = sw / text_len

            start_idx = 0
            end_idx = text_len

            # If the line contains the start point
            if line_rect.top() <= start_pt.y() <= line_rect.bottom():
                px_start = start_pt.x() - sx
                start_idx = max(0, int(px_start / char_w))

            # If the line contains the end point
            if line_rect.top() <= end_pt.y() <= line_rect.bottom():
                px_end = end_pt.x() - sx
                end_idx = min(text_len, int(px_end / char_w) + 1)

            # If start_idx and end_idx are out of order (e.g., right to left drag on the same line)
            if start_idx > end_idx:
                start_idx, end_idx = end_idx, start_idx

            # Full line is between start/end
            if start_idx < end_idx:
                selected_texts.append(line["text"][start_idx:end_idx])

        if selected_texts:
            text_str = "\\n".join(selected_texts)
            QApplication.clipboard().setText(text_str)

    def paintEvent(self, event):
        super().paintEvent(event)
        if (
            not self.ocr_lines
            or not self.has_selection
            or not self.selection_start
            or not self.selection_end
        ):
            return

        painter = QPainter(self)
        highlight_color = QColor(0, 120, 215, 100)
        painter.setBrush(highlight_color)
        painter.setPen(Qt.PenStyle.NoPen)

        start_pt = self.selection_start
        end_pt = self.selection_end
        if start_pt.y() > end_pt.y() or (
            start_pt.y() == end_pt.y() and start_pt.x() > end_pt.x()
        ):
            start_pt, end_pt = end_pt, start_pt

        sorted_lines = sorted(
            self.ocr_lines, key=lambda l: (l["rect"][1], l["rect"][0])
        )

        for line in sorted_lines:
            x, y, w, h = line["rect"]
            sx = int(x * self.scale_factor)
            sy = int(y * self.scale_factor)
            sw = int(w * self.scale_factor)
            sh = int(h * self.scale_factor)
            line_rect = QRect(sx, sy, sw, sh)

            if line_rect.bottom() < start_pt.y() or line_rect.top() > end_pt.y():
                continue

            text_len = max(1, len(line["text"]))
            char_w = sw / text_len

            highlight_x = sx
            highlight_w = sw

            if line_rect.top() <= start_pt.y() <= line_rect.bottom():
                px_start = start_pt.x() - sx
                start_idx = max(0, int(px_start / char_w))
                highlight_x = sx + int(start_idx * char_w)
                highlight_w -= int(start_idx * char_w)

            if line_rect.top() <= end_pt.y() <= line_rect.bottom():
                px_end = end_pt.x() - sx
                end_idx = min(text_len, int(px_end / char_w) + 1)
                highlight_w -= sw - int(end_idx * char_w)

            # Ensure x and w are properly formed if dragged right-to-left on the same line
            if highlight_w < 0:
                highlight_w = abs(highlight_w)
                highlight_x = highlight_x - highlight_w

            if highlight_w > 0:
                painter.drawRect(QRect(highlight_x, sy, highlight_w, sh))


class PinnedImageWindow(QWidget):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self.scaled_pixmap = pixmap

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.scale_factor = 1.0

        self.image_label = ImageLabel(self)
        self.image_label.setPixmap(self.scaled_pixmap)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.addWidget(self.image_label)

        self.shadow_enabled = True
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0, 0, 0, 150))
        self.shadow.setOffset(0, 5)
        self.image_label.setGraphicsEffect(self.shadow)

        self.resize(
            self.original_pixmap.width() + 30, self.original_pixmap.height() + 30
        )

        self.drag_position = QPoint()
        self.ocr_worker = None
        self.toast_label = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def wheelEvent(self, event):
        # Zoom in/out with mouse wheel
        delta = event.angleDelta().y()
        if delta > 0:
            self.scale_factor *= 1.1
        else:
            self.scale_factor *= 0.9

        # Clamp scale factor to reasonable limits
        self.scale_factor = max(0.1, min(self.scale_factor, 10.0))

        new_width = int(self.original_pixmap.width() * self.scale_factor)
        new_height = int(self.original_pixmap.height() * self.scale_factor)

        # Calculate new position to keep the window centered on the mouse cursor

        self.scaled_pixmap = self.original_pixmap.scaled(
            new_width,
            new_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.image_label.setPixmap(self.scaled_pixmap)
        self.setFixedSize(new_width + 30, new_height + 30)

        self.image_label.set_scale(self.scale_factor)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.close()

    def show_context_menu(self, pos):
        menu = QMenu(self)

        copy_action = QAction("复制到剪贴板", self)
        copy_action.triggered.connect(self.copy_to_clipboard)
        menu.addAction(copy_action)

        ocr_action = QAction("文字识别 (OCR)", self)
        ocr_action.triggered.connect(self.recognize_text)
        menu.addAction(ocr_action)

        shadow_action = QAction("隐藏阴影" if self.shadow_enabled else "显示阴影", self)
        shadow_action.triggered.connect(self.toggle_shadow)
        menu.addAction(shadow_action)

        close_action = QAction("关闭", self)
        close_action.triggered.connect(self.close)
        menu.addAction(close_action)

        menu.exec(pos)

    def toggle_shadow(self):
        self.shadow_enabled = not self.shadow_enabled
        self.shadow.setEnabled(self.shadow_enabled)

    def copy_to_clipboard(self):
        QApplication.clipboard().setPixmap(self.original_pixmap)

    def show_toast(self, message, duration=3000):
        if self.toast_label:
            self.toast_label.hide()
            self.toast_label.deleteLater()

        self.toast_label = QLabel(message, self)
        self.toast_label.setStyleSheet(
            "background-color: rgba(30, 30, 30, 200); color: white; padding: 10px; border-radius: 5px; font-weight: bold;"
        )
        self.toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.toast_label.adjustSize()

        # Center horizontally, near the top
        x = (self.width() - self.toast_label.width()) // 2
        self.toast_label.move(x, 20)
        self.toast_label.show()

        # Fade out animation
        from PyQt6.QtCore import QPropertyAnimation, QTimer

        self.opacity_effect = QGraphicsOpacityEffect()
        self.toast_label.setGraphicsEffect(self.opacity_effect)

        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(500)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)

        QTimer.singleShot(duration, self.animation.start)

        def safe_delete():
            try:
                import sip

                if self.toast_label and not sip.isdeleted(self.toast_label):
                    self.toast_label.deleteLater()
            except Exception:
                pass

        self.animation.finished.connect(safe_delete)

    def recognize_text(self):
        if self.ocr_worker and self.ocr_worker.isRunning():
            return

        self.image_label.set_ocr_results([])

        self.ocr_worker = OCRWorker(self.original_pixmap, self)
        self.ocr_worker.finished.connect(self.on_ocr_finished)
        self.ocr_worker.error.connect(lambda e: print(f"OCR Error: {e}"))
        self.ocr_worker.start()

    def on_ocr_finished(self, results):
        self.image_label.set_ocr_results(results)
        # We no longer auto copy or notify on OCR completion
