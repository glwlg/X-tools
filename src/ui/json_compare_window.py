import difflib
import os
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import PushButton, Theme, isDarkTheme, setTheme
from qframelesswindow import AcrylicWindow

from src.core.json_compare import (
    compare_json_text,
    format_json_value,
    parse_json_text,
)


AUTO_COMPARE_INTERVAL_MS = 900
MAX_AUTO_COMPARE_CHARS = 1_200_000
MAX_VISUAL_DIFF_LINES = 8000
MAX_CHAR_DIFF_LINE_LENGTH = 240


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class JsonDiffHighlighter(QSyntaxHighlighter):
    _STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
    _KEY_RE = re.compile(r'"(?:\\.|[^"\\])*"\s*:')
    _NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])")
    _LITERAL_RE = re.compile(r"\b(?:true|false|null)\b")

    def __init__(self, document=None):
        super().__init__(document)
        self._marks = {}
        self.set_dark(True)

    def set_dark(self, dark: bool):
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#22a06b" if not dark else "#8dd672"))

        self.key_format = QTextCharFormat()
        self.key_format.setForeground(QColor("#d82c55" if not dark else "#ff7b93"))
        self.key_format.setFontWeight(QFont.Weight.Bold)

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#7f56d9" if not dark else "#c4b5fd"))

        self.literal_format = QTextCharFormat()
        self.literal_format.setForeground(QColor("#0875c9" if not dark else "#8ab4ff"))

        self.left_diff_format = QTextCharFormat()
        self.left_diff_format.setForeground(QColor("#d1123f" if not dark else "#ff6b81"))
        self.left_diff_format.setFontWeight(QFont.Weight.Bold)
        self.left_diff_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)

        self.right_diff_format = QTextCharFormat()
        self.right_diff_format.setForeground(QColor("#139c4a" if not dark else "#5fd38d"))
        self.right_diff_format.setFontWeight(QFont.Weight.Bold)
        self.right_diff_format.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SingleUnderline
        )
        self.rehighlight()

    def set_marks(self, marks: dict[int, dict]):
        self._marks = marks or {}
        self.rehighlight()

    def highlightBlock(self, text):
        for match in self._STRING_RE.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)

        for match in self._NUMBER_RE.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)

        for match in self._LITERAL_RE.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.literal_format)

        for match in self._KEY_RE.finditer(text):
            key_end = text.rfind(":", match.start(), match.end())
            if key_end > match.start():
                self.setFormat(match.start(), key_end - match.start(), self.key_format)

        mark = self._marks.get(self.currentBlock().blockNumber())
        if not mark:
            return

        for start, end, kind in mark.get("ranges", []):
            if end <= start:
                continue
            fmt = self.left_diff_format if kind == "left" else self.right_diff_format
            self.setFormat(start, end - start, fmt)


class JsonDiffEditor(QPlainTextEdit):
    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.highlighter = JsonDiffHighlighter(self.document())
        self._line_marks = {}
        self._dark = True
        self._text_color = QColor("#242936")
        self._line_number_color = QColor("#8a92a6")
        self._line_number_bg = QColor("#f7f8fb")
        self._line_number_border = QColor("#d9dde8")
        self._left_line_bg = QColor("#f6d8dd")
        self._right_line_bg = QColor("#d8f2e0")
        self._changed_line_bg = QColor("#e6e6e6")

        self.setPlaceholderText(placeholder)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(28)
        self.setFont(QFont("Consolas", 11))
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)

    def line_number_area_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 18 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0,
                rect.y(),
                self.line_number_area.width(),
                rect.height(),
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self._line_number_bg)
        painter.setPen(self._line_number_border)
        painter.drawLine(
            self.line_number_area.width() - 1,
            event.rect().top(),
            self.line_number_area.width() - 1,
            event.rect().bottom(),
        )

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                mark = self._line_marks.get(block_number, {})
                painter.setPen(self._pen_for_mark(mark))
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 7,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def _pen_for_mark(self, mark: dict):
        kind = mark.get("kind", "")
        if kind == "left":
            return QColor("#d1123f" if not self._dark else "#ff6b81")
        if kind == "right":
            return QColor("#139c4a" if not self._dark else "#5fd38d")
        return self._line_number_color

    def set_theme(self, *, dark: bool, border: str, editor_bg: str, text: str):
        self._dark = dark
        self._text_color = QColor(text)
        self._line_number_color = QColor("#8a92a6" if not dark else "#8f98ad")
        self._line_number_bg = QColor("#f7f8fb" if not dark else "#171a22")
        self._line_number_border = QColor("#d9dde8" if not dark else "#303543")
        self._left_line_bg = QColor("#f2d7dd" if not dark else "#4d2530")
        self._right_line_bg = QColor("#d6f0df" if not dark else "#1d4630")
        self._changed_line_bg = QColor("#e7e7e7" if not dark else "#34363d")
        self.highlighter.set_dark(dark)
        self.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {editor_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 0;
                padding: 8px 8px 8px 0;
                selection-background-color: rgba(68, 138, 255, 0.28);
            }}
            """
        )
        self._apply_extra_selections()
        self.line_number_area.update()

    def set_diff_marks(self, marks: dict[int, dict]):
        self._line_marks = marks or {}
        self.highlighter.set_marks(self._line_marks)
        self._apply_extra_selections()
        self.line_number_area.update()

    def clear_diff_marks(self):
        self.set_diff_marks({})

    def _apply_extra_selections(self):
        selections = []
        for line_no, mark in self._line_marks.items():
            block = self.document().findBlockByNumber(line_no)
            if not block.isValid():
                continue
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(block)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            kind = mark.get("kind", "")
            if kind == "left":
                selection.format.setBackground(self._left_line_bg)
            elif kind == "right":
                selection.format.setBackground(self._right_line_bg)
            else:
                selection.format.setBackground(self._changed_line_bg)
            selections.append(selection)
        self.setExtraSelections(selections)


class JsonCompareWindow(AcrylicWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JSON 对比")
        self.resize(1280, 720)

        logo_path = self._resolve_resource_path("logo.png")
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        self._last_report = ""
        self._last_compare_key = None
        self._updating_text = False
        self._syncing_scroll = False

        self._compare_timer = QTimer(self)
        self._compare_timer.setSingleShot(True)
        self._compare_timer.setInterval(AUTO_COMPARE_INTERVAL_MS)
        self._compare_timer.timeout.connect(self.compare_json)

        self._build_ui()
        self.update_style()
        self._connect_auto_compare()

    @staticmethod
    def _resolve_resource_path(filename: str) -> str:
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
            candidates = [
                os.path.join(base_path, filename),
                os.path.join(base_path, "_internal", filename),
            ]
        else:
            candidates = [os.path.join(os.getcwd(), filename)]
        for path in candidates:
            if os.path.exists(path):
                return path
        return ""

    def _build_ui(self):
        self.titleBar.raise_()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, self.titleBar.height(), 0, 0)
        root.setSpacing(0)

        toolbar = QWidget(self)
        toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 8, 14, 8)
        toolbar_layout.setSpacing(8)

        self.format_btn = PushButton("格式化两侧")
        self.format_btn.clicked.connect(self.format_inputs)
        toolbar_layout.addWidget(self.format_btn)

        self.load_left_btn = PushButton("导入左侧")
        self.load_left_btn.clicked.connect(lambda: self.load_file_into(self.left_editor))
        toolbar_layout.addWidget(self.load_left_btn)

        self.load_right_btn = PushButton("导入右侧")
        self.load_right_btn.clicked.connect(
            lambda: self.load_file_into(self.right_editor)
        )
        toolbar_layout.addWidget(self.load_right_btn)

        self.paste_left_btn = PushButton("剪贴板到左侧")
        self.paste_left_btn.clicked.connect(lambda: self.paste_clipboard(self.left_editor))
        toolbar_layout.addWidget(self.paste_left_btn)

        self.paste_right_btn = PushButton("剪贴板到右侧")
        self.paste_right_btn.clicked.connect(
            lambda: self.paste_clipboard(self.right_editor)
        )
        toolbar_layout.addWidget(self.paste_right_btn)

        self.swap_btn = PushButton("交换")
        self.swap_btn.clicked.connect(self.swap_inputs)
        toolbar_layout.addWidget(self.swap_btn)

        self.copy_btn = PushButton("复制报告")
        self.copy_btn.clicked.connect(self.copy_report)
        toolbar_layout.addWidget(self.copy_btn)

        self.clear_btn = PushButton("清空")
        self.clear_btn.clicked.connect(self.clear_all)
        toolbar_layout.addWidget(self.clear_btn)

        self.sort_keys_check = QCheckBox("规范化 key 顺序")
        self.sort_keys_check.setChecked(True)
        self.sort_keys_check.stateChanged.connect(self.schedule_compare)
        toolbar_layout.addWidget(self.sort_keys_check)

        toolbar_layout.addStretch()
        self.status_label = QLabel("等待两侧 JSON 内容")
        self.status_label.setObjectName("statusLabel")
        toolbar_layout.addWidget(self.status_label)
        root.addWidget(toolbar)

        content = QWidget(self)
        content.setObjectName("content")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.left_editor = JsonDiffEditor("粘贴或导入左侧 JSON", content)
        self.right_editor = JsonDiffEditor("粘贴或导入右侧 JSON", content)
        content_layout.addWidget(self._wrap_editor("左侧 JSON", self.left_editor), 1)
        content_layout.addWidget(self._build_gutter(), 0)
        content_layout.addWidget(self._wrap_editor("右侧 JSON", self.right_editor), 1)
        root.addWidget(content, 1)

    def _build_gutter(self):
        gutter = QWidget(self)
        gutter.setObjectName("diffGutter")
        gutter.setFixedWidth(84)
        layout = QVBoxLayout(gutter)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(8)

        self.legend_label = QLabel("红色标记表示多于右侧内容\n绿色标记表示多于左侧内容")
        self.legend_label.setObjectName("legendLabel")
        self.legend_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.legend_label.setWordWrap(True)
        layout.addWidget(self.legend_label)

        layout.addStretch()
        self.arrow_label = QLabel(">>\n\n<<")
        self.arrow_label.setObjectName("arrowLabel")
        self.arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.arrow_label)
        layout.addStretch()
        return gutter

    def _wrap_editor(self, title: str, editor: JsonDiffEditor) -> QWidget:
        panel = QFrame(self)
        panel.setObjectName("editorPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        label = QLabel(title, panel)
        label.setObjectName("panelTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        layout.addWidget(editor, 1)
        return panel

    def _connect_auto_compare(self):
        self.left_editor.textChanged.connect(self.schedule_compare)
        self.right_editor.textChanged.connect(self.schedule_compare)
        self.left_editor.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_scroll(self.left_editor, self.right_editor, value)
        )
        self.right_editor.verticalScrollBar().valueChanged.connect(
            lambda value: self._sync_scroll(self.right_editor, self.left_editor, value)
        )

    def _sync_scroll(self, source: JsonDiffEditor, target: JsonDiffEditor, value: int):
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        try:
            target.verticalScrollBar().setValue(value)
        finally:
            self._syncing_scroll = False

    def update_style(self):
        from src.core.config import config_manager

        dark = config_manager.get_theme_name() == "Dark"
        setTheme(Theme.DARK if dark else Theme.LIGHT)
        try:
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=dark)
        except Exception:
            pass

        if dark:
            border = "rgba(255, 255, 255, 0.10)"
            editor_bg = "rgba(16, 18, 25, 0.86)"
            panel_bg = "rgba(20, 22, 30, 0.60)"
            gutter_bg = "rgba(24, 26, 34, 0.72)"
            text = "#ECEEF6"
            dim = "#A8AFBF"
        else:
            border = "rgba(0, 0, 0, 0.10)"
            editor_bg = "rgba(255, 255, 255, 0.94)"
            panel_bg = "rgba(250, 251, 254, 0.82)"
            gutter_bg = "rgba(242, 244, 249, 0.92)"
            text = "#242936"
            dim = "#687083"

        self.left_editor.set_theme(dark=dark, border=border, editor_bg=editor_bg, text=text)
        self.right_editor.set_theme(
            dark=dark,
            border=border,
            editor_bg=editor_bg,
            text=text,
        )
        self.titleBar.setStyleSheet("QFrame { background: transparent; }")
        self.setStyleSheet(
            f"""
            JsonCompareWindow {{
                background-color: transparent;
                font-family: "Microsoft YaHei UI", sans-serif;
            }}
            #toolbar {{
                background-color: transparent;
                border-bottom: 1px solid {border};
            }}
            #content {{
                background-color: transparent;
            }}
            #editorPanel {{
                background-color: {panel_bg};
            }}
            #panelTitle {{
                color: {text};
                font-size: 13px;
                font-weight: 600;
                padding: 7px 0;
                border-bottom: 1px solid {border};
            }}
            #diffGutter {{
                background-color: {gutter_bg};
                border-left: 1px solid {border};
                border-right: 1px solid {border};
            }}
            #legendLabel {{
                color: {dim};
                font-size: 11px;
                line-height: 1.3;
            }}
            #arrowLabel {{
                color: {dim};
                font-size: 15px;
                font-weight: 700;
            }}
            #statusLabel {{
                color: {dim};
                font-size: 12px;
            }}
            QCheckBox {{
                color: {text};
            }}
            QLabel {{
                color: {text};
            }}
            """
        )

    def schedule_compare(self):
        if self._updating_text:
            return

        left_text = self.left_editor.toPlainText()
        right_text = self.right_editor.toPlainText()

        if not left_text.strip() or not right_text.strip():
            self._compare_timer.stop()
            self._last_report = ""
            self._last_compare_key = None
            self.status_label.setText("等待两侧 JSON 内容")
            if self.left_editor._line_marks or self.right_editor._line_marks:
                QTimer.singleShot(0, self._clear_diff_marks)
            return

        if len(left_text) + len(right_text) > MAX_AUTO_COMPARE_CHARS:
            self._compare_timer.stop()
            self._last_report = ""
            self._last_compare_key = None
            self.status_label.setText("内容较大，已暂停自动对比，避免拖慢系统")
            if self.left_editor._line_marks or self.right_editor._line_marks:
                QTimer.singleShot(0, self._clear_diff_marks)
            return

        self._compare_timer.start()

    def _clear_diff_marks(self):
        self.left_editor.clear_diff_marks()
        self.right_editor.clear_diff_marks()

    def load_file_into(self, editor: QPlainTextEdit):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入 JSON",
            "",
            "JSON Files (*.json);;Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return

        try:
            editor.setPlainText(self._read_text_file(Path(path)))
            self.status_label.setText(f"已导入: {path}")
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))

    @staticmethod
    def _read_text_file(path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def paste_clipboard(editor: QPlainTextEdit):
        editor.setPlainText(QApplication.clipboard().text())

    def format_inputs(self):
        sort_keys = self.sort_keys_check.isChecked()
        try:
            self._updating_text = True
            if self.left_editor.toPlainText().strip():
                left_value = parse_json_text(self.left_editor.toPlainText(), "左侧 JSON")
                self.left_editor.setPlainText(
                    format_json_value(left_value, sort_keys=sort_keys)
                )
            if self.right_editor.toPlainText().strip():
                right_value = parse_json_text(
                    self.right_editor.toPlainText(),
                    "右侧 JSON",
                )
                self.right_editor.setPlainText(
                    format_json_value(right_value, sort_keys=sort_keys)
                )
            self.status_label.setText("格式化完成")
        except ValueError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "格式化失败", str(exc))
        finally:
            self._updating_text = False
        self.schedule_compare()

    def compare_json(self, force: bool = False):
        left_text = self.left_editor.toPlainText()
        right_text = self.right_editor.toPlainText()
        if not left_text.strip() or not right_text.strip():
            self.schedule_compare()
            return

        compare_key = (
            hash(left_text),
            hash(right_text),
            self.sort_keys_check.isChecked(),
        )
        if not force and compare_key == self._last_compare_key:
            return

        if not force and len(left_text) + len(right_text) > MAX_AUTO_COMPARE_CHARS:
            self.status_label.setText("内容较大，已暂停自动对比，避免拖慢系统")
            self._clear_diff_marks()
            return

        result = compare_json_text(
            left_text,
            right_text,
            sort_keys=self.sort_keys_check.isChecked(),
        )

        self._last_compare_key = compare_key
        self._last_report = result.report
        self.status_label.setText(result.summary)

        if not result.ok:
            self.left_editor.clear_diff_marks()
            self.right_editor.clear_diff_marks()
            return

        if not result.differences:
            self.left_editor.clear_diff_marks()
            self.right_editor.clear_diff_marks()
            return

        left_lines = left_text.splitlines()
        right_lines = right_text.splitlines()
        if (
            len(left_lines) > MAX_VISUAL_DIFF_LINES
            or len(right_lines) > MAX_VISUAL_DIFF_LINES
        ):
            self.left_editor.clear_diff_marks()
            self.right_editor.clear_diff_marks()
            self.status_label.setText(f"{result.summary}，内容较多，已跳过行内标记")
            return

        left_marks, right_marks = self._build_visual_marks(left_lines, right_lines)
        self.left_editor.set_diff_marks(left_marks)
        self.right_editor.set_diff_marks(right_marks)

    def _build_visual_marks(self, left_lines: list[str], right_lines: list[str]):
        left_marks = {}
        right_marks = {}
        matcher = difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)

        for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
            if tag == "equal":
                continue

            if tag == "delete":
                for index in range(left_start, left_end):
                    self._set_line_mark(left_marks, index, "left", [(0, len(left_lines[index]), "left")])
                continue

            if tag == "insert":
                for index in range(right_start, right_end):
                    self._set_line_mark(
                        right_marks,
                        index,
                        "right",
                        [(0, len(right_lines[index]), "right")],
                    )
                continue

            left_count = left_end - left_start
            right_count = right_end - right_start
            pair_count = min(left_count, right_count)
            for offset in range(pair_count):
                left_index = left_start + offset
                right_index = right_start + offset
                left_line = left_lines[left_index]
                right_line = right_lines[right_index]
                if (
                    len(left_line) > MAX_CHAR_DIFF_LINE_LENGTH
                    or len(right_line) > MAX_CHAR_DIFF_LINE_LENGTH
                ):
                    left_ranges = [(0, len(left_line), "left")]
                    right_ranges = [(0, len(right_line), "right")]
                else:
                    left_ranges, right_ranges = self._build_char_ranges(
                        left_line,
                        right_line,
                    )
                self._set_line_mark(left_marks, left_index, "left", left_ranges)
                self._set_line_mark(right_marks, right_index, "right", right_ranges)

            for index in range(left_start + pair_count, left_end):
                self._set_line_mark(left_marks, index, "left", [(0, len(left_lines[index]), "left")])

            for index in range(right_start + pair_count, right_end):
                self._set_line_mark(
                    right_marks,
                    index,
                    "right",
                    [(0, len(right_lines[index]), "right")],
                )

        return left_marks, right_marks

    @staticmethod
    def _set_line_mark(marks: dict[int, dict], line_no: int, kind: str, ranges: list[tuple]):
        marks[line_no] = {
            "kind": kind,
            "ranges": ranges,
        }

    @staticmethod
    def _build_char_ranges(left_line: str, right_line: str):
        left_ranges = []
        right_ranges = []
        matcher = difflib.SequenceMatcher(None, left_line, right_line, autojunk=False)
        for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
            if tag == "equal":
                continue
            if left_end > left_start:
                left_ranges.append((left_start, left_end, "left"))
            if right_end > right_start:
                right_ranges.append((right_start, right_end, "right"))

        if not left_ranges and left_line != right_line:
            left_ranges.append((0, len(left_line), "left"))
        if not right_ranges and left_line != right_line:
            right_ranges.append((0, len(right_line), "right"))
        return left_ranges, right_ranges

    def swap_inputs(self):
        left = self.left_editor.toPlainText()
        self.left_editor.setPlainText(self.right_editor.toPlainText())
        self.right_editor.setPlainText(left)
        self.status_label.setText("已交换左右 JSON")

    def copy_report(self):
        report = self._last_report
        if not report and self.left_editor.toPlainText().strip() and self.right_editor.toPlainText().strip():
            self.compare_json(force=True)
            report = self._last_report
        if report:
            QApplication.clipboard().setText(report)
            self.status_label.setText("差异报告已复制到剪贴板")

    def clear_all(self):
        self._compare_timer.stop()
        self._updating_text = True
        try:
            self.left_editor.clear()
            self.right_editor.clear()
        finally:
            self._updating_text = False
        self.left_editor.clear_diff_marks()
        self.right_editor.clear_diff_marks()
        self._last_report = ""
        self._last_compare_key = None
        self.status_label.setText("已清空")

    def closeEvent(self, event):
        self.hide()
        event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JsonCompareWindow()
    if isDarkTheme():
        setTheme(Theme.DARK)
    window.show()
    sys.exit(app.exec())
