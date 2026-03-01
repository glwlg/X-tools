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
    QFileDialog,
)
import threading
import csv
import io
import json
import time
import urllib.parse
import urllib.request
from src.core.logger import get_logger
from src.core.metrics import metrics_store


logger = get_logger(__name__)
_OCR_ENGINE = None
_OCR_ENGINE_LOCK = threading.Lock()
_OCR_INFER_LOCK = threading.Lock()


def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        with _OCR_ENGINE_LOCK:
            if _OCR_ENGINE is None:
                from rapidocr_onnxruntime import RapidOCR

                _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


class OCRWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.pixmap = pixmap

    def run(self):
        try:
            import numpy as np

            ocr = get_ocr_engine()
            image = self.pixmap.toImage()
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
            width, height = image.width(), image.height()

            ptr = image.bits()
            ptr.setsize(image.sizeInBytes())
            arr = np.frombuffer(ptr.asstring(), dtype=np.uint8).reshape(
                (height, width, 4)
            )
            arr = arr[:, :, :3]  # Drop alpha channel

            with _OCR_INFER_LOCK:
                result, elapse = ocr(arr)

            elapsed_ms = 0.0
            try:
                elapsed_val = float(elapse)
                elapsed_ms = elapsed_val * (1000.0 if elapsed_val < 100 else 1.0)
            except Exception:
                elapsed_ms = 0.0
            metrics_store.record(
                "ocr.inference",
                elapsed_ms,
                {"result_count": len(result) if result else 0},
            )

            if result:
                self.finished.emit(result)
            else:
                self.finished.emit([])
        except Exception as e:
            self.error.emit(str(e))


class TranslateWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, text: str, target_lang: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.target_lang = target_lang

    def run(self):
        try:
            if not self.text.strip():
                self.error.emit("没有可翻译内容")
                return

            params = {
                "client": "gtx",
                "sl": "auto",
                "tl": self.target_lang,
                "dt": "t",
                "q": self.text,
            }
            url = (
                "https://translate.googleapis.com/translate_a/single?"
                + urllib.parse.urlencode(params)
            )

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                payload = response.read().decode("utf-8", errors="replace")

            data = json.loads(payload)
            translated_parts = []
            if isinstance(data, list) and data and isinstance(data[0], list):
                for item in data[0]:
                    if isinstance(item, list) and item:
                        translated_parts.append(str(item[0]))

            translated = "".join(translated_parts).strip()
            if not translated:
                self.error.emit("翻译结果为空")
                return

            self.finished.emit(translated)
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
        self.translate_worker = None
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

        if self.image_label.ocr_lines:
            menu.addSeparator()

            copy_ocr_action = QAction("复制 OCR 全文", self)
            copy_ocr_action.triggered.connect(self.copy_ocr_text)
            menu.addAction(copy_ocr_action)

            merge_line_action = QAction("复制 OCR (去换行)", self)
            merge_line_action.triggered.connect(self.copy_ocr_single_line)
            menu.addAction(merge_line_action)

            translate_action = QAction("翻译 OCR 文本", self)
            translate_action.triggered.connect(self.translate_ocr_text)
            menu.addAction(translate_action)

            export_csv_action = QAction("导出 OCR 表格 CSV", self)
            export_csv_action.triggered.connect(self.export_ocr_csv)
            menu.addAction(export_csv_action)

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

    def _sorted_ocr_lines(self):
        return sorted(
            self.image_label.ocr_lines, key=lambda l: (l["rect"][1], l["rect"][0])
        )

    def get_ocr_text(self, single_line=False):
        lines = [str(line.get("text", "")).strip() for line in self._sorted_ocr_lines()]
        lines = [line for line in lines if line]
        if not lines:
            return ""
        if single_line:
            return " ".join(lines)
        return "\n".join(lines)

    def copy_ocr_text(self):
        text = self.get_ocr_text(single_line=False)
        if not text:
            self.show_toast("暂无 OCR 结果")
            return
        QApplication.clipboard().setText(text)
        self.show_toast("OCR 全文已复制")

    def copy_ocr_single_line(self):
        text = self.get_ocr_text(single_line=True)
        if not text:
            self.show_toast("暂无 OCR 结果")
            return
        QApplication.clipboard().setText(text)
        self.show_toast("OCR 文本(去换行)已复制")

    def _ocr_to_table_rows(self):
        lines = self._sorted_ocr_lines()
        if not lines:
            return []

        heights = [max(1, int(line["rect"][3])) for line in lines]
        row_threshold = max(10, int(sum(heights) / len(heights) * 0.6))

        rows = []
        current = []
        current_y = None
        for line in lines:
            x, y, w, h = line["rect"]
            cy = int(y + h / 2)
            if current_y is None or abs(cy - current_y) <= row_threshold:
                current.append(line)
                if current_y is None:
                    current_y = cy
                else:
                    current_y = int((current_y + cy) / 2)
            else:
                rows.append(sorted(current, key=lambda item: item["rect"][0]))
                current = [line]
                current_y = cy
        if current:
            rows.append(sorted(current, key=lambda item: item["rect"][0]))

        column_positions = []
        tolerance = 22
        for row in rows:
            for cell in row:
                x = int(cell["rect"][0])
                matched = False
                for idx, col_x in enumerate(column_positions):
                    if abs(x - col_x) <= tolerance:
                        column_positions[idx] = int((column_positions[idx] + x) / 2)
                        matched = True
                        break
                if not matched:
                    column_positions.append(x)
        column_positions.sort()

        table_rows = []
        for row in rows:
            values = [""] * max(1, len(column_positions))
            for cell in row:
                x = int(cell["rect"][0])
                text = str(cell.get("text", "")).strip()
                col_idx = 0
                min_dist = None
                for i, col_x in enumerate(column_positions):
                    dist = abs(x - col_x)
                    if min_dist is None or dist < min_dist:
                        min_dist = dist
                        col_idx = i
                if values[col_idx]:
                    values[col_idx] = values[col_idx] + " " + text
                else:
                    values[col_idx] = text
            table_rows.append(values)

        return table_rows

    def export_ocr_csv(self):
        rows = self._ocr_to_table_rows()
        if not rows:
            self.show_toast("暂无 OCR 表格可导出")
            return

        default_name = f"ocr-table-{int(time.time())}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 OCR CSV", default_name, "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            QApplication.clipboard().setText(path)
            self.show_toast("CSV 导出成功，路径已复制")
        except Exception as e:
            logger.warning("Failed to export OCR CSV: %s", e)
            self.show_toast("CSV 导出失败")

    @staticmethod
    def _guess_target_lang(text):
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                return "en"
        return "zh-CN"

    def translate_ocr_text(self):
        text = self.get_ocr_text(single_line=False)
        if not text:
            self.show_toast("暂无 OCR 文本可翻译")
            return

        if self.translate_worker and self.translate_worker.isRunning():
            return

        target_lang = self._guess_target_lang(text)
        self.translate_worker = TranslateWorker(text, target_lang, self)
        self.translate_worker.finished.connect(self.on_translate_finished)
        self.translate_worker.error.connect(self.on_translate_error)
        self.translate_worker.finished.connect(self._clear_translate_worker)
        self.translate_worker.error.connect(self._clear_translate_worker)
        self.translate_worker.start()
        self.show_toast("正在翻译...")

    def _clear_translate_worker(self, *args):
        del args
        if self.translate_worker:
            self.translate_worker.deleteLater()
            self.translate_worker = None

    def on_translate_finished(self, text):
        QApplication.clipboard().setText(text)
        self.show_toast("翻译完成，结果已复制")

    def on_translate_error(self, error):
        logger.warning("OCR translation failed: %s", error)
        self.show_toast("翻译失败")

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
                if self.toast_label:
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
        self.ocr_worker.error.connect(lambda e: logger.warning("OCR Error: %s", e))
        self.ocr_worker.start()

    def on_ocr_finished(self, results):
        self.image_label.set_ocr_results(results)
        self.show_toast(f"OCR 完成，共 {len(results)} 条")
