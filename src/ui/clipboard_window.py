from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ListWidget, PrimaryPushButton, PushButton, SearchLineEdit
from qframelesswindow import AcrylicWindow

from src.core.clipboard_history import clipboard_history_manager
from src.core.logger import get_logger


logger = get_logger(__name__)


class ClipboardWindow(AcrylicWindow):
    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager or clipboard_history_manager

        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint
        )
        self.titleBar.hide()
        self.setMinimumSize(760, 520)

        self._build_ui()
        self.manager.entries_changed.connect(self.refresh_list)
        self.refresh_list()

    def _build_ui(self):
        self.container = QWidget(self)
        self.container.setObjectName("clipboardContainer")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索剪贴板历史...")
        self.search_edit.textChanged.connect(self.refresh_list)
        layout.addWidget(self.search_edit)

        self.list_widget = ListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self.copy_selected)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.list_widget, 1)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 4, 0, 0)

        self.copy_btn = PrimaryPushButton("复制选中")
        self.copy_btn.clicked.connect(self.copy_selected)
        buttons_layout.addWidget(self.copy_btn)

        self.pin_btn = PushButton("置顶/取消置顶")
        self.pin_btn.clicked.connect(self.toggle_pin_selected)
        buttons_layout.addWidget(self.pin_btn)

        self.delete_btn = PushButton("删除选中")
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
            "#clipboardContainer {"
            "background-color: rgba(28, 30, 36, 180);"
            "border-radius: 12px;"
            "}"
        )

    @staticmethod
    def _format_time(ts):
        try:
            return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M:%S")
        except Exception:
            return ""

    def _entry_title(self, entry):
        pinned_prefix = "★ " if entry.get("pinned", False) else ""
        if entry.get("type") == "text":
            text = str(entry.get("text", "")).replace("\n", " ").strip()
            if len(text) > 96:
                text = text[:93] + "..."
            return f"{pinned_prefix}文本  {text}"

        size = f"{entry.get('width', 0)}x{entry.get('height', 0)}"
        return f"{pinned_prefix}图片  {size}"

    def refresh_list(self):
        query = self.search_edit.text().strip()
        self.list_widget.clear()

        entries = self.manager.get_entries(query=query, limit=300)
        for entry in entries:
            title = self._entry_title(entry)
            time_text = self._format_time(entry.get("created_at", 0))
            item = QListWidgetItem(f"{title}    [{time_text}]".strip())
            item.setData(Qt.ItemDataRole.UserRole, entry.get("id"))

            if entry.get("pinned", False):
                item.setForeground(QColor(255, 214, 102))
            elif entry.get("type") == "image":
                item.setForeground(QColor(140, 210, 255))

            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _current_entry_id(self):
        item = self.list_widget.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def copy_selected(self):
        entry_id = self._current_entry_id()
        if not entry_id:
            return

        ok = self.manager.copy_entry_to_clipboard(entry_id)
        if ok:
            self.hide()
        else:
            QMessageBox.warning(self, "失败", "复制失败，条目可能已失效。")

    def toggle_pin_selected(self):
        entry_id = self._current_entry_id()
        if not entry_id:
            return

        pinned = self.manager.toggle_pin(entry_id)
        self.refresh_list()
        if pinned:
            logger.info("Clipboard entry pinned: %s", entry_id)
        else:
            logger.info("Clipboard entry unpinned: %s", entry_id)

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

        pin_text = "取消置顶" if entry.get("pinned", False) else "置顶"
        pin_action = QAction(pin_text, self)
        pin_action.triggered.connect(self.toggle_pin_selected)
        menu.addAction(pin_action)

        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self.delete_selected)
        menu.addAction(delete_action)

        menu.exec(self.list_widget.viewport().mapToGlobal(pos))

    def closeEvent(self, event):
        self.hide()
        event.ignore()


if __name__ == "__main__":
    app = QApplication([])
    clipboard_history_manager.start(QApplication.clipboard())
    window = ClipboardWindow()
    window.show()
    app.exec()
