import os
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ListWidget, PrimaryPushButton, PushButton, SearchLineEdit
from qframelesswindow import AcrylicWindow

from src.core.capture_history import capture_history_manager
from src.core.logger import get_logger
from src.platform.shell import open_parent, open_path
from src.ui.pinned_image_window import PinnedImageWindow


logger = get_logger(__name__)


class CaptureHistoryWindow(AcrylicWindow):
    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager or capture_history_manager
        self._pinned_windows = []

        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.titleBar.hide()
        self.setMinimumSize(920, 580)

        self._build_ui()
        self.manager.entries_changed.connect(self.refresh_list)
        self.refresh_list()

    def _build_ui(self):
        self.container = QWidget(self)
        self.container.setObjectName("captureHistoryContainer")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索捕获历史...")
        self.search_edit.textChanged.connect(self.refresh_list)
        layout.addWidget(self.search_edit)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(12)

        self.list_widget = ListWidget(self)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.copy_selected())
        self.list_widget.currentItemChanged.connect(
            lambda current, _previous: self.show_entry_preview(current)
        )
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        content_row.addWidget(self.list_widget, 3)

        self.preview_panel = QWidget(self)
        self.preview_panel.setObjectName("capturePreviewPanel")
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)

        self.preview_image = QLabel(self.preview_panel)
        self.preview_image.setObjectName("capturePreviewImage")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumHeight(300)
        preview_layout.addWidget(self.preview_image, 1)

        self.preview_details = QLabel("未选择捕获记录", self.preview_panel)
        self.preview_details.setObjectName("capturePreviewDetails")
        self.preview_details.setWordWrap(True)
        preview_layout.addWidget(self.preview_details)

        content_row.addWidget(self.preview_panel, 2)
        layout.addLayout(content_row, 1)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 4, 0, 0)

        self.copy_btn = PrimaryPushButton("复制")
        self.copy_btn.clicked.connect(self.copy_selected)
        buttons_layout.addWidget(self.copy_btn)

        self.pin_btn = PushButton("贴图")
        self.pin_btn.clicked.connect(self.pin_selected)
        buttons_layout.addWidget(self.pin_btn)

        self.open_btn = PushButton("打开图片")
        self.open_btn.clicked.connect(self.open_selected)
        buttons_layout.addWidget(self.open_btn)

        self.folder_btn = PushButton("打开目录")
        self.folder_btn.clicked.connect(self.open_folder_selected)
        buttons_layout.addWidget(self.folder_btn)

        self.toggle_pin_btn = PushButton("置顶/取消置顶")
        self.toggle_pin_btn.clicked.connect(self.toggle_pin_selected)
        buttons_layout.addWidget(self.toggle_pin_btn)

        self.delete_btn = PushButton("删除")
        self.delete_btn.clicked.connect(self.delete_selected)
        buttons_layout.addWidget(self.delete_btn)

        self.clear_btn = PushButton("清空未置顶")
        self.clear_btn.clicked.connect(self.clear_unpinned)
        buttons_layout.addWidget(self.clear_btn)

        self.close_btn = PushButton("关闭")
        self.close_btn.clicked.connect(self.hide)
        buttons_layout.addWidget(self.close_btn)

        layout.addLayout(buttons_layout)

        self.setStyleSheet(
            """
            #captureHistoryContainer {
                background-color: rgba(28, 30, 36, 180);
                border-radius: 12px;
            }
            #capturePreviewPanel {
                background-color: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 36);
                border-radius: 8px;
            }
            QLabel#capturePreviewImage {
                background-color: rgba(0, 0, 0, 36);
                border-radius: 6px;
            }
            QLabel#capturePreviewDetails {
                color: rgba(255, 255, 255, 210);
                font-size: 13px;
            }
            """
        )

    @staticmethod
    def _format_time(ts):
        try:
            return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M:%S")
        except Exception:
            return ""

    def _entry_title(self, entry):
        pinned_prefix = "★ " if entry.get("pinned", False) else ""
        size = f"{entry.get('width', 0)}x{entry.get('height', 0)}"
        time_text = self._format_time(entry.get("created_at", 0))
        actions = " / ".join(entry.get("actions", [])) or "capture"
        return f"{pinned_prefix}截图  {size}  {actions}  [{time_text}]"

    def refresh_list(self):
        query = self.search_edit.text().strip()
        current_id = self._current_entry_id()
        self.list_widget.clear()

        entries = self.manager.get_entries(query=query, limit=300)
        selected_row = 0
        for row, entry in enumerate(entries):
            item = QListWidgetItem(self._entry_title(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry.get("id"))

            if entry.get("pinned", False):
                item.setForeground(QColor(255, 214, 102))
            else:
                item.setForeground(QColor(140, 210, 255))

            self.list_widget.addItem(item)
            if current_id and entry.get("id") == current_id:
                selected_row = row

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(selected_row)
        else:
            self.preview_image.clear()
            self.preview_details.setText("没有捕获记录")

    def _current_entry_id(self):
        item = self.list_widget.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _current_entry(self):
        entry_id = self._current_entry_id()
        if not entry_id:
            return None
        return self.manager.get_entry(entry_id)

    def show_entry_preview(self, item):
        if item is None:
            self.preview_image.clear()
            self.preview_details.setText("未选择捕获记录")
            return

        entry_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        entry = self.manager.get_entry(entry_id)
        if not entry:
            self.preview_image.clear()
            self.preview_details.setText("捕获记录已失效")
            return

        path = str(entry.get("image_path", ""))
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.preview_image.clear()
        else:
            target = self.preview_image.size()
            scaled = pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview_image.setPixmap(scaled)

        saved_path = str(entry.get("saved_path", "")).strip() or "仅历史副本"
        detail_lines = [
            f"尺寸: {entry.get('width', 0)}x{entry.get('height', 0)}",
            f"时间: {self._format_time(entry.get('created_at', 0))}",
            f"动作: {' / '.join(entry.get('actions', [])) or 'capture'}",
            f"文件: {saved_path}",
        ]
        self.preview_details.setText("\n".join(detail_lines))

    def copy_selected(self):
        entry_id = self._current_entry_id()
        if not entry_id:
            return

        ok = self.manager.copy_entry_to_clipboard(entry_id)
        if ok:
            self.hide()
        else:
            QMessageBox.warning(self, "失败", "复制失败，捕获记录可能已失效。")

    def pin_selected(self):
        entry = self._current_entry()
        if not entry:
            return

        pixmap = QPixmap(str(entry.get("image_path", "")))
        if pixmap.isNull():
            QMessageBox.warning(self, "失败", "贴图失败，捕获记录可能已失效。")
            return

        window = PinnedImageWindow(pixmap)
        window.show()
        self._pinned_windows.append(window)
        self.hide()

    def toggle_pin_selected(self):
        entry_id = self._current_entry_id()
        if not entry_id:
            return
        self.manager.toggle_pin(entry_id)
        self.refresh_list()

    def _open_path_for_entry(self, entry):
        saved_path = str(entry.get("saved_path", "")).strip()
        if saved_path and os.path.exists(saved_path):
            return saved_path
        return str(entry.get("image_path", "")).strip()

    def open_selected(self):
        entry = self._current_entry()
        if not entry:
            return
        path = self._open_path_for_entry(entry)
        if path and not open_path(path):
            logger.warning("Failed to open capture image: %s", path)

    def open_folder_selected(self):
        entry = self._current_entry()
        if not entry:
            return
        path = self._open_path_for_entry(entry)
        if not open_parent(path):
            logger.warning("Failed to open capture folder: %s", path)

    def delete_selected(self):
        entry_id = self._current_entry_id()
        if not entry_id:
            return
        if self.manager.delete_entry(entry_id):
            self.refresh_list()

    def clear_unpinned(self):
        removed = self.manager.clear_unpinned()
        QMessageBox.information(self, "完成", f"已清理 {removed} 条未置顶记录")

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is None:
            return

        entry_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        entry = self.manager.get_entry(entry_id)
        if not entry:
            return

        menu = QMenu(self)

        copy_action = QAction("复制", self)
        copy_action.triggered.connect(self.copy_selected)
        menu.addAction(copy_action)

        pin_image_action = QAction("贴图", self)
        pin_image_action.triggered.connect(self.pin_selected)
        menu.addAction(pin_image_action)

        open_action = QAction("打开图片", self)
        open_action.triggered.connect(self.open_selected)
        menu.addAction(open_action)

        folder_action = QAction("打开目录", self)
        folder_action.triggered.connect(self.open_folder_selected)
        menu.addAction(folder_action)

        pin_text = "取消置顶" if entry.get("pinned", False) else "置顶"
        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(self.toggle_pin_selected)
        menu.addAction(pin_action)

        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self.delete_selected)
        menu.addAction(delete_action)

        menu.exec(self.list_widget.viewport().mapToGlobal(pos))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "list_widget"):
            self.show_entry_preview(self.list_widget.currentItem())

    def closeEvent(self, event):
        self.hide()
        event.ignore()


if __name__ == "__main__":
    app = QApplication([])
    window = CaptureHistoryWindow()
    window.show()
    app.exec()
