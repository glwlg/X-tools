from PyQt6.QtWidgets import QApplication

from src.core.config import config_manager
from src.core.plugin_base import PluginBase
from src.core.plugin_manager import plugin_manager
from src.core.workflow_schema import normalize_workflows


ALLOWED_TEMPLATE_VARS = ("clipboard", "prev", "input")


class WorkflowPlugin(PluginBase):
    def __init__(self):
        pass

    def get_name(self):
        return "工作流宏"

    def get_description(self):
        return "将多步操作合并为一个命令执行"

    def get_keywords(self):
        return ["wf", "workflow", "flow", "macro"]

    def get_command_schema(self):
        return {
            "usage": "wf <workflow-id>",
            "examples": ["wf clip-md5", "workflow now-timestamp", "flow"],
            "params": [
                {
                    "name": "workflow_id",
                    "label": "工作流标识",
                    "placeholder": "clip-md5 / clip-url-encode / now-timestamp",
                    "required": False,
                }
            ],
        }

    def is_direct_action(self):
        return True

    def execute(self, query):
        workflows = normalize_workflows(config_manager.get_workflows())

        text = str(query).strip()
        lowered = text.lower()
        if lowered in self.get_keywords():
            text = ""
        else:
            for keyword in self.get_keywords():
                prefix = f"{keyword} "
                if lowered.startswith(prefix):
                    text = text[len(prefix) :].strip()
                    lowered = text.lower()
                    break

        if lowered.startswith("run "):
            text = text[4:].strip()

        matched = []
        if not text:
            for wf in workflows:
                matched.append((wf, str(wf.get("id", ""))))
        else:
            needle = text.lower()
            first, _, rest = text.partition(" ")
            first_lower = first.strip().lower()
            input_suffix = rest.strip()
            for wf in workflows:
                workflow_id = str(wf.get("id", "")).strip()
                workflow_id_lower = workflow_id.lower()
                if first_lower and first_lower == workflow_id_lower:
                    action_path = workflow_id
                    if input_suffix:
                        action_path = f"{workflow_id} {input_suffix}"
                    matched.append((wf, action_path))
                    continue

                if (
                    needle in workflow_id_lower
                    or needle in str(wf.get("name", "")).lower()
                    or needle in str(wf.get("description", "")).lower()
                ):
                    matched.append((wf, workflow_id))

        return [
            {
                "name": f"执行工作流: {wf['name']} ({wf['id']})",
                "path": action_path,
                "type": "workflow_run",
                "workflow_desc": wf["description"],
            }
            for wf, action_path in matched
        ]

    @staticmethod
    def _clipboard_text():
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return ""
        return clipboard.text().strip()

    @staticmethod
    def _copy_text(value):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(str(value))
        return True

    @staticmethod
    def _render_template(template, context):
        rendered = str(template)
        for key in ALLOWED_TEMPLATE_VARS:
            rendered = rendered.replace("{" + key + "}", str(context.get(key, "")))
        return rendered.strip()

    @staticmethod
    def _parse_command(command):
        parts = str(command).strip().split(None, 1)
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    @staticmethod
    def _find_plugin_for_keyword(keyword):
        word = str(keyword).strip().lower()
        if not word:
            return None

        for plugin in plugin_manager.get_plugins(enabled_only=True):
            keywords = [str(item).strip().lower() for item in plugin.get_keywords()]
            if word in keywords:
                return plugin
        return None

    @staticmethod
    def _pick_result(results, prefix=""):
        if not isinstance(results, list):
            return None

        candidates = [item for item in results if isinstance(item, dict)]
        if not candidates:
            return None

        pick = str(prefix).strip().lower()
        if pick:
            for item in candidates:
                name = str(item.get("name", "")).lower()
                if name.startswith(pick):
                    return item

        return candidates[0]

    @staticmethod
    def _get_workflows():
        return normalize_workflows(config_manager.get_workflows())

    def handle_action(self, workflow_id):
        action_text = str(workflow_id).strip()
        if not action_text:
            return "未找到对应工作流"

        action_parts = action_text.split(None, 1)
        key = action_parts[0].strip().lower()
        input_text = action_parts[1].strip() if len(action_parts) > 1 else ""

        workflow = None
        for item in self._get_workflows():
            if str(item.get("id", "")).strip().lower() == key:
                workflow = item
                break

        if workflow is None:
            return "未找到对应工作流"

        context = {
            "clipboard": self._clipboard_text(),
            "prev": "",
            "input": input_text,
        }

        steps = workflow.get("steps", [])
        for index, step in enumerate(steps, start=1):
            rendered = self._render_template(step.get("command", ""), context)
            keyword, args = self._parse_command(rendered)

            if not keyword:
                return f"工作流失败: 第{index}步命令为空"

            plugin = self._find_plugin_for_keyword(keyword)
            if plugin is None:
                return f"工作流失败: 第{index}步未找到插件 ({keyword})"

            try:
                results = plugin.execute(args)
            except Exception as exc:
                return f"工作流失败: 第{index}步执行异常 ({keyword}): {exc}"

            pick_prefix = self._render_template(step.get("pick", ""), context)
            chosen = self._pick_result(results, pick_prefix)
            if not chosen:
                return f"工作流失败: 第{index}步未匹配到结果"
            if not isinstance(chosen, dict):
                return f"工作流失败: 第{index}步结果格式无效"

            output = str(chosen.get("path", "")).strip()
            if not output:
                return f"工作流失败: 第{index}步结果为空"
            context["prev"] = output

        if not context["prev"]:
            return "工作流失败: 没有可复制结果"
        if not self._copy_text(context["prev"]):
            return "工作流失败: 无法写入剪贴板"

        workflow_name = str(workflow.get("name") or workflow.get("id") or "")
        return f"工作流完成：{workflow_name}（共 {len(steps)} 步）"

    def on_enter(self):
        pass

    def on_exit(self):
        pass
