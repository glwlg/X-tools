import os
import tempfile
import json
import re
import uuid
import sys
from PyQt6.QtCore import (
    Qt,
    QRect,
    QSize,
    QFileSystemWatcher,
)
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QTextCharFormat,
    QSyntaxHighlighter,
    QFont,
    QIcon,
)
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidgetItem,
    QPlainTextEdit,
    QMessageBox,
    QSplitter,
    QFileDialog,
    QLabel,
    QFormLayout,
)
from qfluentwidgets import (
    PushButton,
    PrimaryPushButton,
    ListWidget,
    RadioButton,
    LineEdit,
    SwitchButton,
    setTheme,
    Theme,
    isDarkTheme,
)
from qframelesswindow import AcrylicWindow

HOSTS_PATH = r"C:\Windows\System32\drivers\etc\hosts"
DB_PATH = os.path.join(os.path.expanduser("~"), ".x-tools", "hosts_profiles.json")

XTOOLS_START_MARKER = "# ================= X-TOOLS HOSTS START ================="
XTOOLS_END_MARKER = "# ================= X-TOOLS HOSTS END ================="


class HostsSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        self.ip_format = QTextCharFormat()
        self.comment_format = QTextCharFormat()
        self.set_colors(QColor(41, 128, 185), QColor(127, 140, 141))

    def set_colors(self, ip_color, comment_color):
        self.highlighting_rules.clear()

        self.ip_format.setForeground(ip_color)
        self.ip_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append(
            (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), self.ip_format)
        )

        self.comment_format.setForeground(comment_color)
        self.highlighting_rules.append((re.compile(r"^\s*#.*$"), self.comment_format))
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.updateLineNumberAreaWidth(0)

        font = QFont("Consolas", 11)
        self.setFont(font)
        self.bg_color = QColor(0, 0, 0, 0)
        self.text_color = QColor("#bdc3c7")
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: transparent;
                border: none;
                padding: 10px;
                color: #C8CAD4;
            }
        """)

    def set_theme(self, theme, dark=True):
        self.bg_color = QColor(0, 0, 0, 0)  # transparent
        self.text_color = QColor(theme.get("text_dim", "#bdc3c7"))

        color = "#C8CAD4" if dark else "#2C2C3A"
        qss = f"""
            QPlainTextEdit {{
                background-color: transparent;
                color: {color};
                border: none;
                padding: 12px;
                font-family: "Consolas", "Cascadia Code", monospace;
                font-size: 13px;
                line-height: 1.5;
            }}
        """
        self.setStyleSheet(qss)
        self.line_number_area.update()

    def lineNumberAreaWidth(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num /= 10
            digits += 1
        return 20 + self.fontMetrics().horizontalAdvance("9") * digits

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height())
        )

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        # Translucent line number area
        painter.fillRect(event.rect(), getattr(self, "bg_color", QColor(0, 0, 0, 0)))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())

        painter.setPen(getattr(self, "text_color", QColor("#bdc3c7")))
        font = self.font()
        painter.setFont(font)

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


class ProfileItemWidget(QWidget):
    def __init__(self, profile_id, title, is_system=False, enabled=False, parent=None):
        super().__init__(parent)
        self.profile_id = profile_id

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.icon_label = QLabel("💻" if is_system else "📄")
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 14px;")

        font = self.title_label.font()
        if is_system:
            font.setBold(True)
        self.title_label.setFont(font)

        self.switch = SwitchButton()
        self.switch.setChecked(enabled)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addStretch()

        if not is_system:
            layout.addWidget(self.switch)
        else:
            lock_label = QLabel("🔒")
            lock_label.setStyleSheet("color: #95a5a6; font-size: 14px;")
            layout.addWidget(lock_label)


class HostsWindow(AcrylicWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hosts 管理")
        self.resize(1050, 650)

        logo_path = self.resolve_resource_path("logo.png")
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        self.profiles = {}
        self.current_profile_id = None
        self._prevent_save = False
        self._is_applying = False

        self.init_ui()
        self.update_style()
        self.load_profiles()

        self.file_watcher = QFileSystemWatcher(self)
        if os.path.exists(HOSTS_PATH):
            self.file_watcher.addPath(HOSTS_PATH)
        self.file_watcher.fileChanged.connect(self.on_hosts_file_changed)

    def resolve_resource_path(self, filename):
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
            possible_paths = [
                os.path.join(base_path, filename),
                os.path.join(base_path, "_internal", filename),
            ]
        else:
            possible_paths = [os.path.join(os.getcwd(), filename)]
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return None

    def init_ui(self):
        # We need to add the layouts to AcrylicWindow internal container `self` (or self.windowBar placeholder if using custom)
        # AcrylicWindow provides a standard basic layout where titlebar is at top. We use a QVBoxLayout.

        # In AcrylicWindow, we shouldn't replace its layout, but instead set a central widget or add to it.
        # But QWidget (the base of AcrylicWindow) allows standard QLayout. Wait, FramelessWindow actually requires us to be careful not to hide titlebar completely if we still want it.

        # Create a content container that goes under the native title bar.
        # Actually AcrylicWindow inherits from FramelessWindow which manages its own titleBar.
        # It's better to just set layout on self and give a top margin for title bar.
        self.titleBar.raise_()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, self.titleBar.height(), 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar_container = QWidget()
        toolbar_container.setMaximumHeight(64)
        toolbar_container.setObjectName("toolbar")

        toolbar = QHBoxLayout(toolbar_container)
        toolbar.setContentsMargins(20, 10, 20, 10)
        toolbar.setSpacing(12)

        self.btn_new = PushButton("✚ 新建方案")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.clicked.connect(self.new_profile)

        self.btn_del = PushButton("🗑 删除")
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(self.del_profile)

        self.btn_apply = PrimaryPushButton("🚀 立即应用到系统")
        self.btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply.clicked.connect(self.apply_hosts)

        toolbar.addWidget(self.btn_new)
        toolbar.addWidget(self.btn_del)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_apply)
        main_layout.addWidget(toolbar_container)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("mainSplitter")

        # 1. Left Pane
        left_widget = QWidget()
        left_widget.setObjectName("leftPane")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.list_widget = ListWidget()
        self.list_widget.setObjectName("sidebarList")
        self.list_widget.currentRowChanged.connect(self.on_profile_selected)
        left_layout.addWidget(self.list_widget)

        list_toolbar = QHBoxLayout()
        list_toolbar.setContentsMargins(15, 12, 15, 15)
        self.btn_import = PushButton("导入")
        self.btn_import.clicked.connect(self.import_profiles)
        self.btn_export = PushButton("导出")
        self.btn_export.clicked.connect(self.export_profiles)
        list_toolbar.addWidget(self.btn_import)
        list_toolbar.addWidget(self.btn_export)
        left_layout.addLayout(list_toolbar)
        self.splitter.addWidget(left_widget)

        # 2. Middle Pane (Editor)
        middle_widget = QWidget()
        middle_widget.setObjectName("middlePane")
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        self.text_editor = CodeEditor()
        self.text_editor.textChanged.connect(self.on_text_changed)
        self.highlighter = HostsSyntaxHighlighter(self.text_editor.document())
        middle_layout.addWidget(self.text_editor)
        self.splitter.addWidget(middle_widget)

        # 3. Right Pane (Settings)
        right_widget = QWidget()
        right_widget.setObjectName("rightPane")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(24, 24, 24, 24)

        settings_header = QLabel("📝 方案属性")
        settings_header.setStyleSheet("font-size: 18px; font-weight: bold;")
        right_layout.addWidget(settings_header)
        right_layout.addSpacing(20)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        type_group_widget = QWidget()
        type_layout = QHBoxLayout(type_group_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)
        self.rb_local = RadioButton("本地模式")
        self.rb_local.setChecked(True)
        self.rb_remote = RadioButton("远程拉取")

        self.rb_local.toggled.connect(self.on_type_changed)
        self.rb_remote.toggled.connect(self.on_type_changed)

        type_layout.addWidget(self.rb_local)
        type_layout.addWidget(self.rb_remote)
        type_layout.addStretch()

        self.title_edit = LineEdit()
        self.title_edit.setFixedHeight(36)
        self.title_edit.textChanged.connect(self.on_title_changed)

        lbl1 = QLabel("功能类型")
        lbl1.setStyleSheet("font-size: 13px; font-weight: bold;")
        lbl2 = QLabel("方案标题")
        lbl2.setStyleSheet("font-size: 13px; font-weight: bold;")
        form_layout.addRow(lbl1, type_group_widget)
        form_layout.addRow(lbl2, self.title_edit)

        self.url_edit = LineEdit()
        self.url_edit.setFixedHeight(36)
        self.url_edit.setPlaceholderText("https://...")
        self.url_edit.hide()
        self.url_edit.textChanged.connect(self.on_url_changed)

        self.btn_update_remote = PushButton("⬇️ 立即拉取更新")
        self.btn_update_remote.hide()
        self.btn_update_remote.clicked.connect(self.update_remote_hosts)

        self.lbl_url = QLabel("资源 URL")
        self.lbl_url.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.lbl_url.hide()
        form_layout.addRow(self.lbl_url, self.url_edit)
        form_layout.addRow("", self.btn_update_remote)

        right_layout.addLayout(form_layout)
        right_layout.addStretch()
        self.splitter.addWidget(right_widget)

        self.splitter.setSizes([260, 1000, 320])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        main_layout.addWidget(self.splitter)

    def update_style(self):
        from src.core.config import config_manager

        theme_name = config_manager.get_theme_name()
        dark = theme_name == "Dark"

        if dark:
            setTheme(Theme.DARK)
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=True)
            self.titleBar.setStyleSheet("QFrame { background: transparent; }")
            bg_left = "rgba(0, 0, 0, 0.2)"
            bg_mid = "transparent"
            bg_right = "rgba(30, 32, 43, 0.4)"
            border = "rgba(255, 255, 255, 0.1)"
            text = "#E2E4EB"
            self.highlighter.set_colors(QColor(108, 114, 230), QColor(106, 153, 85))
        else:
            setTheme(Theme.LIGHT)
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=False)
            self.titleBar.setStyleSheet("QFrame { background: transparent; }")
            bg_left = "rgba(255, 255, 255, 0.4)"
            bg_mid = "transparent"
            bg_right = "rgba(240, 244, 255, 0.5)"
            border = "rgba(0, 0, 0, 0.05)"
            text = "#2C2C3A"
            self.highlighter.set_colors(QColor(41, 128, 185), QColor(127, 140, 141))

        theme = config_manager.get_theme()
        self.text_editor.set_theme(theme, dark=dark)

        qss = f"""
            HostsWindow {{
                background-color: transparent;
                font-family: "Microsoft YaHei UI", sans-serif;
            }}
            #toolbar {{
                background-color: transparent;
                border-bottom: 1px solid {border};
            }}
            #leftPane {{
                background-color: {bg_left};
                border-right: 1px solid {border};
            }}
            #middlePane {{
                background-color: {bg_mid};
            }}
            #rightPane {{
                background-color: {bg_right};
                border-left: 1px solid {border};
            }}
            QSplitter::handle {{
                background-color: transparent;
            }}
            #sidebarList {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            #sidebarList::item {{
                border-radius: 8px;
                margin: 4px 10px;
                color: {text};
            }}
            #sidebarList::item:selected {{
                background-color: rgba(68, 138, 255, 0.15);
                font-weight: bold;
            }}
            #sidebarList::item:hover:!selected {{
                background-color: rgba(100, 100, 100, 0.1);
            }}
            QLabel {{
                color: {text};
            }}
        """
        self.setStyleSheet(qss)

    def load_profiles(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "r", encoding="utf-8") as f:
                    raw_profiles = json.load(f)
                    self.profiles = {}
                    for k, v in raw_profiles.items():
                        if isinstance(v, str):
                            self.profiles[k] = {
                                "title": k,
                                "content": v,
                                "enabled": False,
                                "type": "local",
                            }
                        elif isinstance(v, dict):
                            if "title" not in v:
                                v["title"] = k
                            if "type" not in v:
                                v["type"] = "local"
                            self.profiles[k] = v
                        else:
                            self.profiles[k] = {
                                "title": k,
                                "content": str(v),
                                "enabled": False,
                                "type": "local",
                            }
            except Exception as e:
                print(f"Error loading hosts profiles: {e}")
                self.profiles = {}

        sys_hosts = ""
        try:
            if os.path.exists(HOSTS_PATH):
                with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                    sys_hosts = f.read().strip()
        except Exception:
            pass

        if "系统 Hosts" not in self.profiles:
            self.profiles["系统 Hosts"] = {
                "title": "系统 Hosts",
                "content": sys_hosts,
                "enabled": False,
                "type": "local",
            }
        else:
            self.profiles["系统 Hosts"]["content"] = sys_hosts

        self.save_profiles()
        self.update_list()
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def save_profiles(self):
        try:
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving hosts profiles: {e}")

    def update_list(self):
        self.list_widget.clear()

        keys = list(self.profiles.keys())
        if "系统 Hosts" in keys:
            keys.remove("系统 Hosts")
            keys.insert(0, "系统 Hosts")

        for pid in keys:
            data = self.profiles[pid]
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, pid)

            is_sys = pid == "系统 Hosts"
            widget = ProfileItemWidget(
                pid,
                data.get("title", pid),
                is_system=is_sys,
                enabled=data.get("enabled", False),
            )

            widget.switch.checkedChanged.connect(
                lambda checked, p=pid: self.on_switch_toggled(p, checked)
            )

            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

    def new_profile(self):
        pid = f"profile_{uuid.uuid4().hex[:8]}"
        title = f"New Profile ({pid[-4:]})"
        self.profiles[pid] = {
            "title": title,
            "content": "# Local Hosts\n",
            "enabled": False,
            "type": "local",
        }
        self.save_profiles()
        self.update_list()

        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == pid:
                self.list_widget.setCurrentItem(it)
                break

    def del_profile(self):
        if not self.current_profile_id or self.current_profile_id == "系统 Hosts":
            QMessageBox.information(self, "提示", "系统默认 Hosts 不能删除。")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除此 Hosts 方案吗?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self.profiles[self.current_profile_id]
            self.save_profiles()
            self.update_list()

    def on_switch_toggled(self, pid, checked):
        if pid in self.profiles:
            self.profiles[pid]["enabled"] = checked
            self.save_profiles()

    def on_profile_selected(self, index):
        if index < 0 or index >= self.list_widget.count():
            return

        item = self.list_widget.item(index)
        pid = item.data(Qt.ItemDataRole.UserRole)
        self.current_profile_id = pid
        data = self.profiles.get(pid, {})

        self._prevent_save = True
        self.text_editor.setPlainText(data.get("content", ""))
        self.title_edit.setText(data.get("title", pid))
        self.title_edit.setEnabled(pid != "系统 Hosts")

        is_remote = data.get("type", "local") == "remote"
        if is_remote:
            self.rb_remote.setChecked(True)
        else:
            self.rb_local.setChecked(True)

        self.url_edit.setText(data.get("url", ""))
        self.on_type_changed()

        self.rb_local.setEnabled(pid != "系统 Hosts")
        self.rb_remote.setEnabled(pid != "系统 Hosts")

        self._prevent_save = False

    def on_text_changed(self):
        if (
            not self._prevent_save
            and self.current_profile_id
            and self.current_profile_id in self.profiles
        ):
            self.profiles[self.current_profile_id]["content"] = (
                self.text_editor.toPlainText()
            )
            self.save_profiles()

    def on_title_changed(self, text):
        if (
            not self._prevent_save
            and self.current_profile_id
            and self.current_profile_id in self.profiles
        ):
            self.profiles[self.current_profile_id]["title"] = text
            self.save_profiles()

            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == self.current_profile_id:
                    widget = self.list_widget.itemWidget(it)
                    if isinstance(widget, ProfileItemWidget):
                        widget.title_label.setText(text)
                    break

    def on_type_changed(self):
        is_remote = self.rb_remote.isChecked()

        self.lbl_url.setVisible(is_remote)
        self.url_edit.setVisible(is_remote)
        self.btn_update_remote.setVisible(is_remote)
        self.text_editor.setReadOnly(is_remote)

        if (
            not self._prevent_save
            and self.current_profile_id
            and self.current_profile_id in self.profiles
        ):
            new_type = "remote" if is_remote else "local"
            if self.profiles[self.current_profile_id].get("type") != new_type:
                self.profiles[self.current_profile_id]["type"] = new_type
                self.save_profiles()

    def on_url_changed(self, text):
        if (
            not self._prevent_save
            and self.current_profile_id
            and self.current_profile_id in self.profiles
        ):
            self.profiles[self.current_profile_id]["url"] = text
            self.save_profiles()

    def update_remote_hosts(self):
        if not self.current_profile_id or self.current_profile_id not in self.profiles:
            return

        url = self.profiles[self.current_profile_id].get("url", "").strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先输入有效的远程 Hosts 地址(URL)。")
            return

        import urllib.request
        import urllib.error

        self.btn_update_remote.setText("拉取中...")
        self.btn_update_remote.setEnabled(False)
        self.repaint()

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode("utf-8")

            self.profiles[self.current_profile_id]["content"] = content
            self.save_profiles()

            self._prevent_save = True
            self.text_editor.setPlainText(content)
            self._prevent_save = False

            QMessageBox.information(self, "成功", "远程 Hosts 方案已成功拉取并更新。")
        except Exception as e:
            QMessageBox.critical(self, "更新失败", f"发生错误: {str(e)}")
        finally:
            self.btn_update_remote.setText("⬇️ 立即拉取更新")
            self.btn_update_remote.setEnabled(True)

    def apply_hosts(self):
        base_system_hosts = ""
        if "系统 Hosts" in self.profiles:
            content = self.profiles["系统 Hosts"].get("content", "")
            if XTOOLS_START_MARKER in content and XTOOLS_END_MARKER in content:
                start_idx = content.find(XTOOLS_START_MARKER)
                end_idx = content.find(XTOOLS_END_MARKER) + len(XTOOLS_END_MARKER)
                before = content[:start_idx].rstrip()
                after = content[end_idx:].lstrip()
                base_system_hosts = before
                if before and after:
                    base_system_hosts += "\n\n"
                base_system_hosts += after
            else:
                base_system_hosts = content.strip()
        else:
            try:
                if os.path.exists(HOSTS_PATH):
                    with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                        content = f.read()
                        if (
                            XTOOLS_START_MARKER in content
                            and XTOOLS_END_MARKER in content
                        ):
                            start_idx = content.find(XTOOLS_START_MARKER)
                            end_idx = content.find(XTOOLS_END_MARKER) + len(
                                XTOOLS_END_MARKER
                            )
                            base_system_hosts = (
                                content[:start_idx] + "\n" + content[end_idx:]
                            ).strip()
                        else:
                            base_system_hosts = content.strip()
            except Exception:
                pass

        injected_content = ""
        for pid, data in self.profiles.items():
            if pid == "系统 Hosts":
                continue
            if data.get("enabled", False):
                injected_content += f"\n# --- Profile: {data.get('title', pid)} ---\n"
                injected_content += data.get("content", "") + "\n"

        if not injected_content.strip():
            QMessageBox.information(
                self, "提示", "没有选中任何自定义启用的方案，将只保存原生系统 Hosts。"
            )
            final_content = base_system_hosts
        else:
            final_content = base_system_hosts
            if final_content:
                final_content += "\n\n"
            final_content += f"{XTOOLS_START_MARKER}\n{injected_content.strip()}\n{XTOOLS_END_MARKER}\n"

        import subprocess

        temp_fd, temp_path = tempfile.mkstemp(suffix=".txt", text=True)
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(final_content)

        result_fd, result_path = tempfile.mkstemp(suffix=".res", text=True)
        os.close(result_fd)

        if hasattr(self, "file_watcher") and HOSTS_PATH in self.file_watcher.files():
            self.file_watcher.removePath(HOSTS_PATH)

        self._is_applying = True

        ps_script_fd, ps_script_path = tempfile.mkstemp(suffix=".ps1", text=True)
        with os.fdopen(ps_script_fd, "w", encoding="utf-8") as f:
            f.write(f"""$ErrorActionPreference = 'Stop'
try {{
    Copy-Item -Path '{temp_path}' -Destination '{HOSTS_PATH}' -Force
    Out-File -FilePath '{result_path}' -InputObject 'SUCCESS' -Encoding utf8
    exit 0
}} catch {{
    Out-File -FilePath '{result_path}' -InputObject $_.Exception.Message -Encoding utf8
    exit 1
}}
""")

        success = False
        error_detail = ""
        try:
            cmd = f"Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{ps_script_path}\"' -Verb RunAs -Wait -WindowStyle Hidden"
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    cmd,
                ],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8-sig") as rf:
                    result_text = rf.read().strip()
                    if "SUCCESS" in result_text:
                        success = True
                    else:
                        error_detail = result_text if result_text else "未知执行错误"
            else:
                error_detail = "无法获取执行结果文件（可能是用户拒绝了 UAC 请求）"
        except Exception as e:
            error_detail = str(e)
            success = False

        try:
            os.unlink(ps_script_path)
        except Exception:
            pass
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        try:
            os.unlink(result_path)
        except Exception:
            pass

        if (
            hasattr(self, "file_watcher")
            and os.path.exists(HOSTS_PATH)
            and HOSTS_PATH not in self.file_watcher.files()
        ):
            self.file_watcher.addPath(HOSTS_PATH)

        self._is_applying = False

        if success:
            if "系统 Hosts" in self.profiles:
                self.profiles["系统 Hosts"]["content"] = final_content
                self.save_profiles()
                if self.current_profile_id == "系统 Hosts":
                    self._prevent_save = True
                    self.text_editor.setPlainText(final_content)
                    self._prevent_save = False
            QMessageBox.information(
                self,
                "成功",
                "已叠加启用的方案并申请写入系统 Hosts。\n如果赋予了管理员权限，配置即刻生效。",
            )
        else:
            QMessageBox.warning(
                self,
                "错误",
                f"需要管理员权限才能修改 Hosts 文件。\n详情: {error_detail}",
            )

    def import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 Hosts 方案", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                imported = json.load(f)
                for k, v in imported.items():
                    pid = f"imported_{uuid.uuid4().hex[:6]}"
                    if isinstance(v, str):
                        self.profiles[pid] = {
                            "title": f"Imported {k}",
                            "content": v,
                            "enabled": False,
                            "type": "local",
                            "url": "",
                        }
                    elif isinstance(v, dict):
                        if "title" not in v:
                            v["title"] = f"Imported {k}"
                        if "type" not in v:
                            v["type"] = "local"
                        if "url" not in v:
                            v["url"] = ""
                        self.profiles[pid] = v
            self.save_profiles()
            self.update_list()
            QMessageBox.information(self, "成功", "方案导入成功！")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导入失败: {e}")

    def export_profiles(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Hosts 方案", "hosts_backup.json", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "成功", "方案导出成功！")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"导出失败: {e}")

    def on_hosts_file_changed(self, path):
        if self._is_applying:
            return
        try:
            if os.path.exists(HOSTS_PATH):
                with open(HOSTS_PATH, "r", encoding="utf-8") as f:
                    sys_hosts = f.read().strip()
                if "系统 Hosts" in self.profiles:
                    if self.profiles["系统 Hosts"].get("content") != sys_hosts:
                        self.profiles["系统 Hosts"]["content"] = sys_hosts
                        self.save_profiles()
                        if self.current_profile_id == "系统 Hosts":
                            self._prevent_save = True
                            scroll_val = self.text_editor.verticalScrollBar().value()
                            self.text_editor.setPlainText(sys_hosts)
                            self.text_editor.verticalScrollBar().setValue(scroll_val)
                            self._prevent_save = False
        except Exception as e:
            print(f"Error handling external hosts file modification: {e}")
