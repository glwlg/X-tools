# Macro Settings V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Settings-based workflow macro manager that supports user-defined command chains and executes them through the existing `wf` entrypoint.

**Architecture:** Keep UI and execution concerns separated: `SettingsWindow` only edits validated workflow config, while `WorkflowPlugin` reads config and runs the chain engine at runtime. Add a small shared schema/helper module for normalization and validation so config loading, UI save, and plugin execution use one contract.

**Tech Stack:** Python 3.12, PyQt6/qfluentwidgets, existing plugin system (`PluginBase`/`plugin_manager`), built-in `unittest` and `unittest.mock`.

---

### Task 1: Add Shared Workflow Schema Helpers

**Files:**
- Create: `src/core/workflow_schema.py`
- Create: `tests/__init__.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_workflow_schema.py`

**Step 1: Write the failing test**

```python
import unittest

from src.core.workflow_schema import normalize_workflows, validate_workflow_id


class TestWorkflowSchema(unittest.TestCase):
    def test_normalize_invalid_payload_returns_default(self):
        workflows = normalize_workflows({"bad": "value"})
        self.assertGreaterEqual(len(workflows), 1)
        self.assertIn("id", workflows[0])
        self.assertIn("steps", workflows[0])

    def test_validate_workflow_id(self):
        self.assertTrue(validate_workflow_id("clip-url-md5"))
        self.assertFalse(validate_workflow_id("ClipURL"))
        self.assertFalse(validate_workflow_id("bad id"))
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.core.test_workflow_schema.TestWorkflowSchema -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.workflow_schema'`

**Step 3: Write minimal implementation**

```python
# src/core/workflow_schema.py
import copy
import re

WORKFLOW_ID_RE = re.compile(r"^[a-z0-9-]+$")

DEFAULT_WORKFLOWS = [
    {
        "id": "clip-md5",
        "name": "剪贴板文本 -> MD5",
        "description": "读取剪贴板文本并复制其 MD5 值",
        "steps": [
            {"command": "hash {clipboard}", "pick": "MD5"},
        ],
    },
    {
        "id": "clip-url-encode",
        "name": "剪贴板文本 -> URL 编码",
        "description": "读取剪贴板文本并复制 URL 编码结果",
        "steps": [
            {"command": "url {clipboard}", "pick": "编码结果"},
        ],
    },
    {
        "id": "clip-base64-encode",
        "name": "剪贴板文本 -> Base64 编码",
        "description": "读取剪贴板文本并复制 Base64 编码结果",
        "steps": [
            {"command": "base64 {clipboard}", "pick": "编码结果"},
        ],
    },
    {
        "id": "now-timestamp",
        "name": "当前时间 -> 时间戳",
        "description": "生成当前 Unix 时间戳并复制到剪贴板",
        "steps": [
            {"command": "timestamp now", "pick": "当前时间戳"},
        ],
    },
]


def validate_workflow_id(value: str) -> bool:
    return bool(value and WORKFLOW_ID_RE.fullmatch(str(value).strip()))


def normalize_workflows(raw) -> list[dict]:
    if not isinstance(raw, list):
        return copy.deepcopy(DEFAULT_WORKFLOWS)

    normalized = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        wf_id = str(item.get("id", "")).strip().lower()
        name = str(item.get("name", "")).strip()
        desc = str(item.get("description", "")).strip()
        steps = item.get("steps", [])
        if not validate_workflow_id(wf_id) or not name or wf_id in seen:
            continue
        if not isinstance(steps, list) or not steps:
            continue
        clean_steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            command = str(step.get("command", "")).strip()
            pick = str(step.get("pick", "")).strip()
            if not command:
                continue
            payload = {"command": command}
            if pick:
                payload["pick"] = pick
            clean_steps.append(payload)
        if not clean_steps:
            continue
        normalized.append(
            {
                "id": wf_id,
                "name": name,
                "description": desc,
                "steps": clean_steps,
            }
        )
        seen.add(wf_id)

    return normalized or copy.deepcopy(DEFAULT_WORKFLOWS)
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.core.test_workflow_schema.TestWorkflowSchema -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/core/workflow_schema.py tests/__init__.py tests/core/__init__.py tests/core/test_workflow_schema.py
git commit -m "feat: add workflow schema normalization and defaults"
```

### Task 2: Wire Workflow Config into ConfigManager

**Files:**
- Modify: `src/core/config.py`
- Create: `tests/core/test_config_workflows.py`

**Step 1: Write the failing test**

```python
import unittest

from src.core.config import DEFAULT_CONFIG


class TestWorkflowConfig(unittest.TestCase):
    def test_default_config_contains_workflows(self):
        self.assertIn("workflows", DEFAULT_CONFIG)
        self.assertIsInstance(DEFAULT_CONFIG["workflows"], list)
        self.assertGreaterEqual(len(DEFAULT_CONFIG["workflows"]), 1)
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.core.test_config_workflows.TestWorkflowConfig.test_default_config_contains_workflows -v`
Expected: FAIL with `AssertionError: 'workflows' not found in DEFAULT_CONFIG`

**Step 3: Write minimal implementation**

```python
# src/core/config.py (imports)
from src.core.workflow_schema import DEFAULT_WORKFLOWS, normalize_workflows

# src/core/config.py (DEFAULT_CONFIG)
DEFAULT_CONFIG = {
    "run_on_startup": False,
    "theme": "Dark",
    "plugins_enabled": {},
    "hotkeys": DEFAULT_HOTKEYS.copy(),
    "screenshot_auto_save": False,
    "screenshot_auto_copy": False,
    "screenshot_auto_pin": False,
    "screenshot_save_dir": os.path.join(os.path.expanduser("~"), "Pictures", "x-tools-screenshots"),
    "screenshot_filename_template": "x-tools_{date}_{time}",
    "workflows": [wf.copy() for wf in DEFAULT_WORKFLOWS],
}

# src/core/config.py (load_config)
merged = DEFAULT_CONFIG.copy()
merged.update(loaded)
merged["workflows"] = normalize_workflows(merged.get("workflows"))
```

Also add helper methods:

```python
def get_workflows(self):
    return normalize_workflows(self.config.get("workflows"))


def set_workflows(self, workflows):
    self.config["workflows"] = normalize_workflows(workflows)
    self.save_config()
```

**Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.core.test_workflow_schema tests.core.test_config_workflows -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/core/config.py tests/core/test_config_workflows.py
git commit -m "feat: persist workflows in app config"
```

### Task 3: Implement Command-Chain Execution in WorkflowPlugin

**Files:**
- Modify: `src/plugins/workflow_tool.py`
- Create: `tests/plugins/__init__.py`
- Create: `tests/plugins/test_workflow_plugin_chain.py`

**Step 1: Write the failing test**

```python
import unittest
from unittest.mock import patch

from src.plugins.workflow_tool import WorkflowPlugin


class _FakeUrl:
    def get_keywords(self):
        return ["url"]
    def execute(self, query):
        return [{"name": f"编码结果: E({query})", "path": f"E({query})", "type": "copy_result"}]


class _FakeHash:
    def get_keywords(self):
        return ["hash"]
    def execute(self, query):
        return [{"name": f"MD5: H({query})", "path": f"H({query})", "type": "copy_result"}]


class TestWorkflowPluginChain(unittest.TestCase):
    def test_clipboard_to_prev_chain(self):
        plugin = WorkflowPlugin()
        plugin._workflows = [
            {
                "id": "clip-url-md5",
                "name": "x",
                "description": "x",
                "steps": [
                    {"command": "url {clipboard}", "pick": "编码结果"},
                    {"command": "hash {prev}", "pick": "MD5"},
                ],
            }
        ]

        with patch("src.plugins.workflow_tool.plugin_manager.get_plugins", return_value=[_FakeUrl(), _FakeHash()]):
            with patch.object(WorkflowPlugin, "_clipboard_text", return_value="abc"):
                with patch.object(WorkflowPlugin, "_copy_text", return_value=True):
                    msg = plugin.handle_action("clip-url-md5")

        self.assertIn("工作流完成", msg)
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.plugins.test_workflow_plugin_chain.TestWorkflowPluginChain.test_clipboard_to_prev_chain -v`
Expected: FAIL (plugin still uses hardcoded runners, not `steps`)

**Step 3: Write minimal implementation**

```python
# src/plugins/workflow_tool.py (new helpers)
from src.core.config import config_manager
from src.core.workflow_schema import normalize_workflows

ALLOWED_VARS = {"clipboard", "prev", "input"}


def _render_template(self, template: str, ctx: dict[str, str]) -> str:
    output = template
    for key in ALLOWED_VARS:
        output = output.replace("{" + key + "}", str(ctx.get(key, "")))
    return output.strip()


def _find_plugin_for_keyword(self, keyword: str):
    word = str(keyword).strip().lower()
    for plugin in plugin_manager.get_plugins(enabled_only=True):
        kws = [str(i).strip().lower() for i in plugin.get_keywords() if str(i).strip()]
        if word in kws:
            return plugin
    return None


def _pick_result_item(self, results, pick):
    if not isinstance(results, list) or not results:
        return None
    if pick:
        for item in results:
            if str(item.get("name", "")).lower().startswith(str(pick).lower()):
                return item
    return results[0]


def handle_action(self, workflow_id):
    workflows = normalize_workflows(config_manager.get_value("workflows", []))
    by_id = {str(w["id"]).lower(): w for w in workflows}
    wf = by_id.get(str(workflow_id).strip().lower())
    if wf is None:
        return "未找到对应工作流"

    ctx = {"clipboard": self._clipboard_text(), "prev": "", "input": ""}
    for idx, step in enumerate(wf.get("steps", []), start=1):
        cmd = self._render_template(str(step.get("command", "")), ctx)
        if not cmd:
            return f"工作流失败: 第{idx}步命令为空"

        parts = cmd.split(None, 1)
        if not parts:
            return f"工作流失败: 第{idx}步命令为空"
        keyword = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        target = self._find_plugin_for_keyword(keyword)
        if target is None:
            return f"工作流失败: 第{idx}步未找到插件 ({keyword})"

        results = target.execute(arg)
        item = self._pick_result_item(results, step.get("pick", ""))
        if not item:
            return f"工作流失败: 第{idx}步未匹配到结果"

        out = str(item.get("path", "")).strip()
        if not out:
            return f"工作流失败: 第{idx}步结果为空"
        ctx["prev"] = out

    if not ctx["prev"] or not self._copy_text(ctx["prev"]):
        return "工作流失败: 无法写入剪贴板"
    return f"工作流完成：{wf.get('name', wf.get('id', ''))}（共 {len(wf.get('steps', []))} 步）"
```

Also update `execute()` list rendering to read workflows from config each time.

**Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.plugins.test_workflow_plugin_chain -v`
Expected: PASS

Run: `uv run python -m unittest tests.core.test_workflow_schema tests.core.test_config_workflows tests.plugins.test_workflow_plugin_chain -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/plugins/workflow_tool.py tests/plugins/__init__.py tests/plugins/test_workflow_plugin_chain.py
git commit -m "feat: execute workflows as configurable command chains"
```

### Task 4: Add Workflow Management Page in Settings

**Files:**
- Modify: `src/ui/settings_window.py`
- Create: `tests/ui/__init__.py`
- Create: `tests/ui/test_workflow_steps_codec.py`

**Step 1: Write the failing test**

```python
import unittest

from src.ui.settings_window import parse_workflow_steps_text, format_workflow_steps_text


class TestWorkflowStepsCodec(unittest.TestCase):
    def test_roundtrip_steps_text(self):
        text = "url {clipboard} | 编码结果\nhash {prev} | MD5"
        steps = parse_workflow_steps_text(text)
        self.assertEqual(steps[0]["command"], "url {clipboard}")
        self.assertEqual(steps[0]["pick"], "编码结果")
        out = format_workflow_steps_text(steps)
        self.assertIn("hash {prev}", out)
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.ui.test_workflow_steps_codec.TestWorkflowStepsCodec -v`
Expected: FAIL with `ImportError` for missing helper functions

**Step 3: Write minimal implementation**

```python
# src/ui/settings_window.py (module-level helpers)
ALLOWED_WORKFLOW_VARS = {"{clipboard}", "{prev}", "{input}"}


def parse_workflow_steps_text(text: str) -> list[dict]:
    steps = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "|" in line:
            command, pick = line.split("|", 1)
            command = command.strip()
            pick = pick.strip()
        else:
            command, pick = line, ""
        payload = {"command": command}
        if pick:
            payload["pick"] = pick
        steps.append(payload)
    return steps


def format_workflow_steps_text(steps: list[dict]) -> str:
    lines = []
    for step in steps:
        command = str(step.get("command", "")).strip()
        if not command:
            continue
        pick = str(step.get("pick", "")).strip()
        lines.append(f"{command} | {pick}" if pick else command)
    return "\n".join(lines)
```

Then add page + handlers in `SettingsWindow`:

1. `self.page_workflows = ScrollWidget("宏", "page_workflows", self)`
2. Add cards/buttons for New/Save/Delete.
3. Load data from `config_manager.get_workflows()`.
4. Save with validation (`id` format, unique, at least one step, allowed template vars).
5. Register nav item: `self.addSubInterface(self.page_workflows, FI.ROBOT, "宏")`.

**Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest tests.ui.test_workflow_steps_codec -v`
Expected: PASS

Run: `uv run python -m unittest tests.core.test_workflow_schema tests.core.test_config_workflows tests.plugins.test_workflow_plugin_chain tests.ui.test_workflow_steps_codec -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/ui/settings_window.py tests/ui/__init__.py tests/ui/test_workflow_steps_codec.py
git commit -m "feat: add workflow management page in settings"
```

### Task 5: Documentation and Integration Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-03-01-macro-settings-design.md` (optional minor updates if implementation differs)

**Step 1: Write failing integration checklist (as executable notes)**

```text
1) Open Settings -> 宏 page exists
2) Create workflow clip-url-md5 with two steps
3) Search 'wf clip-url-md5' and execute
4) Clipboard equals expected chained output
```

**Step 2: Run verification flow and capture failure before fix (if any)**

Run: `uv run main.py`
Expected: If mismatch, record exact failure step and return to corresponding task.

**Step 3: Update docs to final behavior**

```markdown
- README “工作流宏命令” section now includes:
  - Settings-based macro CRUD
  - Command chain format (`command | pick`)
  - Variables `{clipboard}` / `{prev}` / `{input}`
```

**Step 4: Run final checks**

Run: `uv run python -m unittest tests.core.test_workflow_schema tests.core.test_config_workflows tests.plugins.test_workflow_plugin_chain tests.ui.test_workflow_steps_codec -v`
Expected: PASS

Run (headless smoke): `uv run python -c "from src.core.config import config_manager; from src.plugins.workflow_tool import WorkflowPlugin; w=WorkflowPlugin(); config_manager.set_workflows([{'id':'clip-url-md5','name':'clip-url-md5','description':'smoke','steps':[{'command':'url {clipboard}','pick':'编码结果'},{'command':'hash {prev}','pick':'MD5'}]}]); print('LIST_OK' if any(i.get('path')=='clip-url-md5' for i in w.execute('')) else 'LIST_FAIL')"`
Expected: output contains `LIST_OK`

Manual acceptance checklist:
1) Open Settings -> `宏` page exists.
2) Create workflow `clip-url-md5` with two steps:
   - `url {clipboard} | 编码结果`
   - `hash {prev} | MD5`
3) In search box run `wf clip-url-md5` and execute result.
4) Clipboard value equals expected chained output.
5) Delete workflow and verify `wf clip-url-md5` no longer appears.

**Step 5: Commit**

```bash
git add README.md docs/plans/2026-03-01-macro-settings-design.md
git commit -m "docs: document configurable workflow macros"
```

### Definition of Done

1. Settings has a dedicated `宏` page with create/edit/delete.
2. `wf` command can discover and run user-defined command-chain macros.
3. `{clipboard}` and `{prev}` work reliably in chained execution.
4. Errors are surfaced with clear step-level messages.
5. All newly added tests pass.
