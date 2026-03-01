from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QLineEdit,
    QPushButton,
    QFileDialog,
)
from qfluentwidgets import (
    FluentWindow,
    SettingCardGroup,
    SwitchSettingCard,
    PrimaryPushSettingCard,
    PushSettingCard,
    PlainTextEdit,
    ScrollArea,
    FluentIcon as FI,
    SettingCard,
    ComboBox,
    NavigationItemPosition,
    LargeTitleLabel,
)
from src.core.hotkey_manager import VK_MAP
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QKeyEvent, QIcon
import os
import json
import sys

from src.core.metrics import metrics_store
from src.core.workflow_schema import validate_workflow_id
from src.core.workflow_steps_codec import (
    find_unknown_placeholders,
    format_workflow_steps_text as _format_workflow_steps_text,
    parse_workflow_steps_text as _parse_workflow_steps_text,
)


ALLOWED_WORKFLOW_VARS = {"clipboard", "prev", "input"}


def parse_workflow_steps_text(text) -> list[dict]:
    return _parse_workflow_steps_text(text)


def format_workflow_steps_text(steps) -> str:
    return _format_workflow_steps_text(steps)


class HotkeyRecordCard(PushSettingCard):
    hotkey_changed = pyqtSignal(str)

    def __init__(
        self, title, action_key, config_manager, icon=FI.COMMAND_PROMPT, parent=None
    ):
        super().__init__("未设置", icon, title, "点击右侧按钮开始录制快捷键", parent)
        self.config_manager = config_manager
        self.action_key = action_key
        self._recording = False

        self.button.clicked.connect(self.start_recording)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.load_hotkey()

    def load_hotkey(self):
        hk = self.config_manager.get_hotkey(self.action_key)
        self._hotkey = hk
        self._update_display()

    def _update_display(self):
        if self._recording:
            self.button.setText("⏺ 录制中...")
        elif self._hotkey:
            self.button.setText(self._format_hotkey(self._hotkey))
        else:
            self.button.setText("未设置")

    @staticmethod
    def _format_hotkey(hotkey_str: str) -> str:
        if not hotkey_str:
            return ""
        parts = hotkey_str.lower().split("+")
        return " + ".join(p.strip().capitalize() for p in parts)

    def start_recording(self):
        self._recording = True
        self._update_display()
        self.setFocus()

    def get_hotkey(self) -> str:
        return self._hotkey

    def set_hotkey(self, hotkey_str: str):
        self._hotkey = hotkey_str
        self._update_display()

    def keyPressEvent(self, event: QKeyEvent):
        if not self._recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Meta,
        ):
            return

        if key == Qt.Key.Key_Escape:
            self._recording = False
            self._update_display()
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("win")

        key_char = event.text().lower()
        key_name = None

        if key_char and key_char in VK_MAP:
            key_name = key_char
        else:
            for name, vk in VK_MAP.items():
                qt_key_name = f"Key_{name.capitalize()}"
                if hasattr(Qt.Key, qt_key_name) and getattr(Qt.Key, qt_key_name) == key:
                    key_name = name
                    break
            if key_name is None:
                for i in range(1, 13):
                    if key == getattr(Qt.Key, f"Key_F{i}"):
                        key_name = f"f{i}"
                        break

        if key_name is None:
            return

        if not parts and not key_name.startswith("f"):
            return

        parts.append(key_name)
        new_hotkey = "+".join(parts)

        self._hotkey = new_hotkey
        self._recording = False
        self._update_display()
        self.hotkey_changed.emit(new_hotkey)

    def focusOutEvent(self, event):
        if self._recording:
            self._recording = False
            self._update_display()
        super().focusOutEvent(event)


class ScrollWidget(ScrollArea):
    """A generic scrollable widget page for Settings"""

    def __init__(self, title, obj_name, parent=None):
        super().__init__(parent)
        self.view = QWidget(self)
        self.vBoxLayout = QVBoxLayout(self.view)

        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)
        self.vBoxLayout.setSpacing(16)

        self.titleLabel = LargeTitleLabel(title, self.view)
        self.titleLabel.setObjectName("pageTitle")
        # Give it a nice bold appearance and space below
        font = self.titleLabel.font()
        font.setPixelSize(28)
        font.setBold(True)
        self.titleLabel.setFont(font)
        self.titleLabel.setStyleSheet("margin-bottom: 12px;")

        self.vBoxLayout.addWidget(self.titleLabel)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName(obj_name)

        self.setStyleSheet(
            "ScrollWidget { background-color: transparent; border: none; } "
            "QScrollArea { border: none; background-color: transparent; }"
        )
        self.view.setStyleSheet("QWidget { background-color: transparent; }")

    def addGroup(self, group):
        self.vBoxLayout.addWidget(group)

    def addStretch(self):
        self.vBoxLayout.addStretch(1)


class SettingsWindow(FluentWindow):
    settings_changed = pyqtSignal()
    hotkeys_changed = pyqtSignal()

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager

        logo_path = self._resolve_resource_path("logo.png")
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        self.setWindowTitle("X-Tools 设置")
        self.setMinimumSize(960, 680)

        # Enable acrylic/mica effect natively via FluentWindow
        self.windowEffect.setMicaEffect(
            self.winId(), isDarkMode=self.config_manager.get_theme_name() == "Dark"
        )

        self.init_pages()
        self.load_settings()

    def _resolve_resource_path(self, filename):
        if getattr(sys, "frozen", False):
            base_path = os.path.dirname(sys.executable)
            possible_paths = [
                os.path.join(base_path, filename),
                os.path.join(base_path, "_internal", filename),
            ]
        else:
            possible_paths = [
                os.path.join(os.path.dirname(__file__), filename),
                os.path.join(os.getcwd(), filename),
            ]
        for p in possible_paths:
            if os.path.exists(p):
                return p
        return None

    def init_pages(self):
        # ─── Page 0: General ───
        self.page_gen = ScrollWidget("通用设置", "page_general", self)
        gen_group = SettingCardGroup("应用启动行为", self.page_gen)

        self.startup_check = SwitchSettingCard(
            FI.POWER_BUTTON,
            "开机自动启动",
            "在 Windows 启动时自动运行 X-Tools 并在后台驻留",
            parent=gen_group,
        )
        self.startup_check.checkedChanged.connect(self.on_startup_changed)
        gen_group.addSettingCard(self.startup_check)
        self.page_gen.addGroup(gen_group)

        screenshot_group = SettingCardGroup("截图自动化", self.page_gen)

        self.screenshot_auto_copy_card = SwitchSettingCard(
            FI.COPY,
            "自动复制截图",
            "完成截图动作后自动写入剪贴板",
            parent=screenshot_group,
        )
        self.screenshot_auto_copy_card.checkedChanged.connect(
            lambda state: self.on_config_switch_changed("screenshot_auto_copy", state)
        )
        screenshot_group.addSettingCard(self.screenshot_auto_copy_card)

        self.screenshot_auto_pin_card = SwitchSettingCard(
            FI.PIN,
            "自动贴图",
            "完成截图动作后自动创建贴图窗口",
            parent=screenshot_group,
        )
        self.screenshot_auto_pin_card.checkedChanged.connect(
            lambda state: self.on_config_switch_changed("screenshot_auto_pin", state)
        )
        screenshot_group.addSettingCard(self.screenshot_auto_pin_card)

        self.screenshot_auto_save_card = SwitchSettingCard(
            FI.SAVE,
            "自动保存截图",
            "完成截图动作后自动保存 PNG 文件",
            parent=screenshot_group,
        )
        self.screenshot_auto_save_card.checkedChanged.connect(
            lambda state: self.on_config_switch_changed("screenshot_auto_save", state)
        )
        screenshot_group.addSettingCard(self.screenshot_auto_save_card)

        self.screenshot_dir_card = SettingCard(
            FI.FOLDER,
            "保存目录",
            "自动保存截图的输出目录",
            screenshot_group,
        )
        self.screenshot_dir_edit = QLineEdit(self.screenshot_dir_card)
        self.screenshot_dir_edit.setReadOnly(True)
        self.screenshot_dir_edit.setMinimumWidth(280)
        self.screenshot_dir_edit.setMaximumWidth(380)
        self.screenshot_dir_btn = QPushButton("选择")
        self.screenshot_dir_btn.clicked.connect(self.on_pick_screenshot_dir)
        self.screenshot_dir_card.hBoxLayout.addWidget(
            self.screenshot_dir_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_dir_card.hBoxLayout.addWidget(
            self.screenshot_dir_btn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_dir_card.hBoxLayout.addSpacing(16)
        screenshot_group.addSettingCard(self.screenshot_dir_card)

        self.screenshot_tpl_card = SettingCard(
            FI.TAG,
            "文件名模板",
            "支持 {date} {time} {datetime} 占位符",
            screenshot_group,
        )
        self.screenshot_tpl_edit = QLineEdit(self.screenshot_tpl_card)
        self.screenshot_tpl_edit.setMinimumWidth(220)
        self.screenshot_tpl_edit.setMaximumWidth(320)
        self.screenshot_tpl_save_btn = QPushButton("保存")
        self.screenshot_tpl_save_btn.clicked.connect(self.on_save_screenshot_template)
        self.screenshot_tpl_card.hBoxLayout.addWidget(
            self.screenshot_tpl_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_tpl_card.hBoxLayout.addWidget(
            self.screenshot_tpl_save_btn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.screenshot_tpl_card.hBoxLayout.addSpacing(16)
        screenshot_group.addSettingCard(self.screenshot_tpl_card)

        self.page_gen.addGroup(screenshot_group)
        self.page_gen.addStretch()

        # ─── Page 1: Appearance ───
        self.page_app = ScrollWidget("外观样式", "page_appearance", self)
        app_group = SettingCardGroup("界面与视觉", self.page_app)

        self.theme_combo_card = SettingCard(
            FI.BRUSH, "界面主题", "选择全量界面的配色风格", app_group
        )
        self.theme_combo = ComboBox(self.theme_combo_card)
        self.theme_combo.addItems(
            ["Dark", "Light"]
            + [
                k
                for k in self.config_manager.themes.keys()
                if k not in ["Dark", "Light"]
            ]
        )
        self.theme_combo.setCurrentText(self.config_manager.get_theme_name())
        self.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        self.theme_combo_card.hBoxLayout.addWidget(
            self.theme_combo, 0, Qt.AlignmentFlag.AlignRight
        )
        self.theme_combo_card.hBoxLayout.addSpacing(16)

        app_group.addSettingCard(self.theme_combo_card)

        # Editor for raw JSON themes underneath
        raw_theme_group = SettingCardGroup("主题 JSON 配置 (高级)", self.page_app)
        # Using a layout to add PlainTextEdit
        self.theme_editor = PlainTextEdit(self.page_app.view)
        self.theme_editor.setMinimumHeight(200)
        self.theme_editor.setStyleSheet("font-family: 'Consolas', monospace;")
        raw_theme_group.layout().addWidget(self.theme_editor)

        save_btn = PrimaryPushSettingCard(
            "应用保存",
            FI.SAVE,
            "保存高级主题配置",
            "编辑上方的 JSON 后点击此按钮生效",
            parent=raw_theme_group,
        )
        save_btn.clicked.connect(self.on_save_themes)
        raw_theme_group.addSettingCard(save_btn)

        self.page_app.addGroup(app_group)
        self.page_app.addGroup(raw_theme_group)
        self.page_app.addStretch()

        # ─── Page 2: Plugins ───
        self.page_plugins = ScrollWidget("插件管理", "page_plugins", self)
        plugins_group = SettingCardGroup("启用的扩展功能", self.page_plugins)

        from src.core.plugin_manager import plugin_manager

        for plugin in plugin_manager.get_plugins(enabled_only=False):
            desc = (
                plugin.get_description()
                + f" (触发词: {', '.join(plugin.get_keywords())})"
            )
            card = SwitchSettingCard(
                FI.APPLICATION, plugin.get_name(), desc, parent=plugins_group
            )
            card.setChecked(plugin_manager.is_plugin_enabled(plugin.get_name()))
            card.checkedChanged.connect(
                lambda state, name=plugin.get_name(): plugin_manager.set_plugin_enabled(
                    name, state
                )
            )
            plugins_group.addSettingCard(card)

        self.page_plugins.addGroup(plugins_group)
        self.page_plugins.addStretch()

        # ─── Page 3: Hotkeys ───
        self.page_hotkeys = ScrollWidget("快捷键", "page_hotkeys", self)
        hotkeys_group = SettingCardGroup("全局操作快捷键", self.page_hotkeys)

        self._hotkey_cards = {}
        actions = [
            ("toggle_window", "唤起 / 隐藏主搜索窗口", FI.SEARCH),
            ("screenshot", "立即进行屏幕截图并在编辑后复制", FI.PHOTO),
            ("pin_clipboard", "将目前系统剪切板贴在屏幕最上层", FI.PIN),
        ]

        for action_key, label_text, icon in actions:
            card = HotkeyRecordCard(
                label_text,
                action_key,
                self.config_manager,
                icon=icon,
                parent=hotkeys_group,
            )
            self._hotkey_cards[action_key] = card
            hotkeys_group.addSettingCard(card)

        self.page_hotkeys.addGroup(hotkeys_group)

        action_group = SettingCardGroup("操作", self.page_hotkeys)

        save_hk_btn = PrimaryPushSettingCard(
            "保存",
            FI.ACCEPT,
            "保存快捷键配置",
            "录制完毕后，点击保存使全局热键生效",
            parent=action_group,
        )
        save_hk_btn.clicked.connect(self.on_save_hotkeys)
        action_group.addSettingCard(save_hk_btn)

        reset_btn = PushSettingCard(
            "恢复",
            FI.SYNC,
            "恢复默认值",
            "清空现有设置，恢复回初始快捷键",
            parent=action_group,
        )
        reset_btn.clicked.connect(self.on_reset_hotkeys)
        action_group.addSettingCard(reset_btn)

        self.page_hotkeys.addGroup(action_group)
        self.page_hotkeys.addStretch()

        # ─── Page 4: Workflows ───
        self.page_workflows = ScrollWidget("宏", "page_workflows", self)

        workflow_list_group = SettingCardGroup("工作流列表", self.page_workflows)

        self.workflow_selector_card = SettingCard(
            FI.ROBOT,
            "选择工作流",
            "从已有宏中选择并编辑",
            workflow_list_group,
        )
        self.workflow_selector = ComboBox(self.workflow_selector_card)
        self.workflow_selector.setMinimumWidth(220)
        self.workflow_selector.currentTextChanged.connect(self.on_workflow_selected)
        self.workflow_selector_card.hBoxLayout.addWidget(
            self.workflow_selector, 0, Qt.AlignmentFlag.AlignRight
        )

        self.workflow_new_btn = QPushButton("新建")
        self.workflow_new_btn.clicked.connect(self.on_new_workflow)
        self.workflow_selector_card.hBoxLayout.addWidget(
            self.workflow_new_btn, 0, Qt.AlignmentFlag.AlignRight
        )

        self.workflow_delete_btn = QPushButton("删除")
        self.workflow_delete_btn.clicked.connect(self.on_delete_workflow)
        self.workflow_selector_card.hBoxLayout.addWidget(
            self.workflow_delete_btn, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_selector_card.hBoxLayout.addSpacing(16)
        workflow_list_group.addSettingCard(self.workflow_selector_card)

        workflow_form_group = SettingCardGroup("工作流编辑", self.page_workflows)

        self.workflow_id_card = SettingCard(
            FI.TAG,
            "ID",
            "仅支持小写字母、数字和连字符（-）",
            workflow_form_group,
        )
        self.workflow_id_edit = QLineEdit(self.workflow_id_card)
        self.workflow_id_edit.setMinimumWidth(280)
        self.workflow_id_edit.setMaximumWidth(420)
        self.workflow_id_card.hBoxLayout.addWidget(
            self.workflow_id_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_id_card.hBoxLayout.addSpacing(16)
        workflow_form_group.addSettingCard(self.workflow_id_card)

        self.workflow_name_card = SettingCard(
            FI.EDIT,
            "名称",
            "用于在搜索结果中显示",
            workflow_form_group,
        )
        self.workflow_name_edit = QLineEdit(self.workflow_name_card)
        self.workflow_name_edit.setMinimumWidth(280)
        self.workflow_name_edit.setMaximumWidth(420)
        self.workflow_name_card.hBoxLayout.addWidget(
            self.workflow_name_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_name_card.hBoxLayout.addSpacing(16)
        workflow_form_group.addSettingCard(self.workflow_name_card)

        self.workflow_desc_card = SettingCard(
            FI.INFO,
            "描述",
            "可选，帮助说明宏用途",
            workflow_form_group,
        )
        self.workflow_desc_edit = QLineEdit(self.workflow_desc_card)
        self.workflow_desc_edit.setMinimumWidth(280)
        self.workflow_desc_edit.setMaximumWidth(420)
        self.workflow_desc_card.hBoxLayout.addWidget(
            self.workflow_desc_edit, 0, Qt.AlignmentFlag.AlignRight
        )
        self.workflow_desc_card.hBoxLayout.addSpacing(16)
        workflow_form_group.addSettingCard(self.workflow_desc_card)

        workflow_steps_group = SettingCardGroup("步骤", self.page_workflows)
        self.workflow_steps_edit = PlainTextEdit(self.page_workflows.view)
        self.workflow_steps_edit.setPlaceholderText(
            "每行一条：command | pick（pick 可省略）\n例如：url {clipboard} | 编码结果"
        )
        self.workflow_steps_edit.setMinimumHeight(220)
        self.workflow_steps_edit.setStyleSheet("font-family: 'Consolas', monospace;")
        workflow_steps_layout = workflow_steps_group.layout()
        if workflow_steps_layout is not None:
            workflow_steps_layout.addWidget(self.workflow_steps_edit)

        workflow_actions_group = SettingCardGroup("操作", self.page_workflows)
        save_workflow_btn = PrimaryPushSettingCard(
            "保存",
            FI.SAVE,
            "保存当前宏",
            "保存后立即写入配置文件",
            parent=workflow_actions_group,
        )
        save_workflow_btn.clicked.connect(self.on_save_workflow)
        workflow_actions_group.addSettingCard(save_workflow_btn)

        self.page_workflows.addGroup(workflow_list_group)
        self.page_workflows.addGroup(workflow_form_group)
        self.page_workflows.addGroup(workflow_steps_group)
        self.page_workflows.addGroup(workflow_actions_group)
        self.page_workflows.addStretch()

        self._workflows_cache = []
        self._selected_workflow_id = ""
        self._syncing_workflow_selector = False

        # ─── Page 5: Diagnostics ───
        self.page_metrics = ScrollWidget("性能诊断", "page_metrics", self)
        metrics_group = SettingCardGroup("运行指标", self.page_metrics)

        self.metrics_text = PlainTextEdit(self.page_metrics.view)
        self.metrics_text.setReadOnly(True)
        self.metrics_text.setMinimumHeight(300)
        self.metrics_text.setStyleSheet("font-family: 'Consolas', monospace;")
        metrics_layout = metrics_group.layout()
        if metrics_layout is not None:
            metrics_layout.addWidget(self.metrics_text)

        refresh_metrics_btn = PrimaryPushSettingCard(
            "刷新",
            FI.SYNC,
            "刷新统计数据",
            "查看启动、搜索、OCR 耗时分布",
            parent=metrics_group,
        )
        refresh_metrics_btn.clicked.connect(self.refresh_metrics)
        metrics_group.addSettingCard(refresh_metrics_btn)

        clear_metrics_btn = PushSettingCard(
            "清空",
            FI.CANCEL,
            "清空统计数据",
            "删除本地性能统计记录",
            parent=metrics_group,
        )
        clear_metrics_btn.clicked.connect(self.on_clear_metrics)
        metrics_group.addSettingCard(clear_metrics_btn)

        self.page_metrics.addGroup(metrics_group)
        self.page_metrics.addStretch()

        # ─── Add Interfaces ───
        self.addSubInterface(self.page_gen, FI.SETTING, "通用")
        self.addSubInterface(self.page_app, FI.BRUSH, "外观")
        self.addSubInterface(self.page_plugins, FI.APPLICATION, "插件")
        self.addSubInterface(self.page_hotkeys, FI.COMMAND_PROMPT, "快捷键")
        self.addSubInterface(self.page_workflows, FI.ROBOT, "宏")
        self.addSubInterface(self.page_metrics, FI.SYNC, "诊断")

    def load_settings(self):
        config = self.config_manager.config

        self.startup_check.setChecked(config.get("run_on_startup", False))
        self.screenshot_auto_copy_card.setChecked(
            config.get("screenshot_auto_copy", False)
        )
        self.screenshot_auto_pin_card.setChecked(
            config.get("screenshot_auto_pin", False)
        )
        self.screenshot_auto_save_card.setChecked(
            config.get("screenshot_auto_save", False)
        )
        self.screenshot_dir_edit.setText(
            config.get("screenshot_save_dir", os.path.expanduser("~"))
        )
        self.screenshot_tpl_edit.setText(
            config.get("screenshot_filename_template", "x-tools_{date}_{time}")
        )

        json_str = json.dumps(self.config_manager.themes, indent=4, ensure_ascii=False)
        self.theme_editor.setPlainText(json_str)
        self.load_workflow_settings()
        self.refresh_metrics()

    def on_config_switch_changed(self, key, state):
        self.config_manager.set_value(key, bool(state))

    def on_pick_screenshot_dir(self):
        current = self.config_manager.get_value(
            "screenshot_save_dir", os.path.expanduser("~")
        )
        folder = QFileDialog.getExistingDirectory(self, "选择截图保存目录", current)
        if not folder:
            return
        self.screenshot_dir_edit.setText(folder)
        self.config_manager.set_value("screenshot_save_dir", folder)

    def on_save_screenshot_template(self):
        template = self.screenshot_tpl_edit.text().strip()
        if not template:
            QMessageBox.warning(self, "提示", "文件名模板不能为空")
            return
        self.config_manager.set_value("screenshot_filename_template", template)
        QMessageBox.information(self, "成功", "截图文件名模板已保存")

    def refresh_metrics(self):
        text = metrics_store.format_summary(
            [
                "startup.total",
                "search.global",
                "search.inline_plugin",
                "ocr.inference",
                "screenshot.save",
            ]
        )
        self.metrics_text.setPlainText(text)

    def on_clear_metrics(self):
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确认清空所有性能统计数据吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            metrics_store.clear()
            self.refresh_metrics()

    def load_workflow_settings(self):
        self._workflows_cache = self.config_manager.get_workflows()
        workflow_ids = [str(w.get("id", "")).strip() for w in self._workflows_cache]

        self._syncing_workflow_selector = True
        self.workflow_selector.clear()
        self.workflow_selector.addItems([wid for wid in workflow_ids if wid])
        self._syncing_workflow_selector = False

        if workflow_ids:
            self.workflow_selector.setCurrentText(workflow_ids[0])
            self.on_workflow_selected(workflow_ids[0])
        else:
            self.on_new_workflow()

    def on_workflow_selected(self, workflow_id):
        if self._syncing_workflow_selector:
            return

        workflow_id = str(workflow_id).strip()
        current = None
        for workflow in self._workflows_cache:
            if str(workflow.get("id", "")).strip() == workflow_id:
                current = workflow
                break

        if current is None:
            return

        self._selected_workflow_id = str(current.get("id", "")).strip()
        self.workflow_id_edit.setText(self._selected_workflow_id)
        self.workflow_name_edit.setText(str(current.get("name", "")).strip())
        self.workflow_desc_edit.setText(str(current.get("description", "")).strip())
        self.workflow_steps_edit.setPlainText(
            format_workflow_steps_text(current.get("steps", []))
        )

    def on_new_workflow(self):
        self._selected_workflow_id = ""
        self.workflow_id_edit.clear()
        self.workflow_name_edit.clear()
        self.workflow_desc_edit.clear()
        self.workflow_steps_edit.clear()
        self.workflow_id_edit.setFocus()

    def on_delete_workflow(self):
        target_id = self._selected_workflow_id or str(
            self.workflow_selector.currentText()
        )
        target_id = str(target_id).strip()
        if not target_id:
            QMessageBox.warning(self, "提示", "请先选择要删除的宏")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除宏 '{target_id}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        workflows = self.config_manager.get_workflows()
        workflows = [
            w
            for w in workflows
            if str(w.get("id", "")).strip().lower() != target_id.lower()
        ]
        self.config_manager.set_workflows(workflows)
        self.load_workflow_settings()
        QMessageBox.information(self, "成功", "宏已删除")

    def on_save_workflow(self):
        workflow_id = self.workflow_id_edit.text().strip().lower()
        name = self.workflow_name_edit.text().strip()
        description = self.workflow_desc_edit.text().strip()
        steps = parse_workflow_steps_text(self.workflow_steps_edit.toPlainText())

        if not validate_workflow_id(workflow_id):
            QMessageBox.warning(
                self, "提示", "宏 ID 格式无效，请使用小写字母、数字和连字符"
            )
            return
        if not name:
            QMessageBox.warning(self, "提示", "宏名称不能为空")
            return

        seen_ids = {
            str(w.get("id", "")).strip().lower()
            for w in self._workflows_cache
            if isinstance(w, dict)
        }
        selected_id = str(self._selected_workflow_id).strip().lower()
        if workflow_id in seen_ids and workflow_id != selected_id:
            QMessageBox.warning(self, "提示", f"宏 ID '{workflow_id}' 已存在")
            return

        cleaned_steps = []
        for index, step in enumerate(steps, start=1):
            command = str(step.get("command", "")).strip()
            pick = str(step.get("pick", "")).strip()
            if not command:
                continue

            unsupported = sorted(
                set(find_unknown_placeholders(command, ALLOWED_WORKFLOW_VARS)).union(
                    find_unknown_placeholders(pick, ALLOWED_WORKFLOW_VARS)
                )
            )
            if unsupported:
                bad = ", ".join("{" + v + "}" for v in unsupported)
                QMessageBox.warning(
                    self,
                    "提示",
                    f"第 {index} 步包含不支持的变量: {bad}\n仅允许 {{clipboard}} / {{prev}} / {{input}}",
                )
                return

            step_payload = {"command": command}
            if pick:
                step_payload["pick"] = pick
            cleaned_steps.append(step_payload)

        if not cleaned_steps:
            QMessageBox.warning(self, "提示", "至少需要一条有效步骤")
            return

        payload = {
            "id": workflow_id,
            "name": name,
            "description": description,
            "steps": cleaned_steps,
        }

        workflows = self.config_manager.get_workflows()
        replaced = False
        for i, item in enumerate(workflows):
            current_id = str(item.get("id", "")).strip().lower()
            if current_id == selected_id:
                workflows[i] = payload
                replaced = True
                break

        if not replaced:
            workflows.append(payload)

        self.config_manager.set_workflows(workflows)
        self.load_workflow_settings()
        self.workflow_selector.setCurrentText(workflow_id)
        self.on_workflow_selected(workflow_id)
        QMessageBox.information(self, "成功", "宏已保存")

    def on_theme_changed(self, text):
        self.config_manager.config["theme"] = text
        self.config_manager.save_config()
        # The app style will reload
        self.settings_changed.emit()

    def on_startup_changed(self, state):
        success = self.config_manager.set_startup(state)
        if not success:
            self.startup_check.setChecked(not state)

    def on_save_themes(self):
        try:
            new_themes = json.loads(self.theme_editor.toPlainText())
            if not isinstance(new_themes, dict):
                raise ValueError("JSON must be an object/dict")

            current = self.config_manager.config.get("theme", "Dark")
            if current not in new_themes:
                current = list(new_themes.keys())[0] if new_themes else "Dark"
                self.config_manager.config["theme"] = current

            self.config_manager.themes = new_themes
            self.config_manager.save_themes()

            # Refresh Options manually if needed, simplified here
            self.settings_changed.emit()
            QMessageBox.information(self, "成功", "主题配置已应用并保存！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"JSON 格式无效: {str(e)}")

    def on_save_hotkeys(self):
        values = []
        for action_key, card in self._hotkey_cards.items():
            hk = card.get_hotkey()
            if hk:
                if hk in values:
                    QMessageBox.warning(self, "冲突", f"快捷键 '{hk}' 被多次使用。")
                    return
                values.append(hk)

        for action_key, card in self._hotkey_cards.items():
            self.config_manager.set_hotkey(action_key, card.get_hotkey())

        self.hotkeys_changed.emit()
        QMessageBox.information(self, "成功", "快捷键已保存并生效。")

    def on_reset_hotkeys(self):
        from src.core.config import DEFAULT_HOTKEYS

        for action_key, card in self._hotkey_cards.items():
            default_val = DEFAULT_HOTKEYS.get(action_key, "")
            card.set_hotkey(default_val)
