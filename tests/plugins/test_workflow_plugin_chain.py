import unittest
from contextlib import ExitStack
from unittest.mock import patch

from src.plugins.workflow_tool import WorkflowPlugin


class _FakeUrl:
    def __init__(self):
        self.calls = []

    def get_keywords(self):
        return ["url"]

    def execute(self, query):
        self.calls.append(query)
        return [
            {
                "name": f"编码结果: E({query})",
                "path": f"E({query})",
                "type": "copy_result",
            }
        ]


class _FakeHash:
    def __init__(self):
        self.calls = []

    def get_keywords(self):
        return ["hash"]

    def execute(self, query):
        self.calls.append(query)
        return [
            {
                "name": f"MD5: H({query})",
                "path": f"H({query})",
                "type": "copy_result",
            }
        ]


class _FakeUrlWithChoices:
    def __init__(self):
        self.calls = []

    def get_keywords(self):
        return ["url"]

    def execute(self, query):
        self.calls.append(query)
        return [
            {"name": "编码结果: fallback", "path": "fallback", "type": "copy_result"},
            {
                "name": f"编码结果: E({query})",
                "path": f"E({query})",
                "type": "copy_result",
            },
        ]


class _FakeBroken:
    def get_keywords(self):
        return ["broken"]

    def execute(self, query):
        raise RuntimeError(f"boom:{query}")


class TestWorkflowPluginChain(unittest.TestCase):
    def _run_action(
        self,
        workflow,
        plugins,
        clipboard_text="abc",
        copy_result=True,
        workflow_id=None,
        bypass_normalization=False,
    ):
        plugin = WorkflowPlugin()
        action_id = workflow_id or workflow["id"]

        with ExitStack() as stack:
            if bypass_normalization:
                stack.enter_context(
                    patch.object(
                        WorkflowPlugin, "_get_workflows", return_value=[workflow]
                    )
                )
            else:
                stack.enter_context(
                    patch(
                        "src.plugins.workflow_tool.config_manager.get_workflows",
                        return_value=[workflow],
                    )
                )
            stack.enter_context(
                patch(
                    "src.plugins.workflow_tool.plugin_manager.get_plugins",
                    return_value=plugins,
                )
            )
            stack.enter_context(
                patch.object(
                    WorkflowPlugin, "_clipboard_text", return_value=clipboard_text
                )
            )
            copy_mock = stack.enter_context(
                patch.object(WorkflowPlugin, "_copy_text", return_value=copy_result)
            )
            msg = plugin.handle_action(action_id)

        return msg, copy_mock

    def test_clipboard_to_prev_chain(self):
        workflows = [
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
        fake_url = _FakeUrl()
        fake_hash = _FakeHash()

        msg, copy_mock = self._run_action(workflows[0], [fake_url, fake_hash])

        self.assertIn("工作流完成", msg)
        self.assertEqual(fake_url.calls, ["abc"])
        self.assertEqual(fake_hash.calls, ["E(abc)"])
        copy_mock.assert_called_once_with("H(E(abc))")

    def test_pick_supports_template_rendering(self):
        workflow = {
            "id": "clip-url-md5",
            "name": "x",
            "description": "x",
            "steps": [
                {
                    "command": "url {clipboard}",
                    "pick": "编码结果: E({clipboard})",
                },
                {"command": "hash {prev}", "pick": "MD5"},
            ],
        }
        fake_url = _FakeUrlWithChoices()
        fake_hash = _FakeHash()

        msg, copy_mock = self._run_action(workflow, [fake_url, fake_hash])

        self.assertIn("工作流完成", msg)
        self.assertEqual(fake_url.calls, ["abc"])
        self.assertEqual(fake_hash.calls, ["E(abc)"])
        copy_mock.assert_called_once_with("H(E(abc))")

    def test_execute_lists_workflows_from_config(self):
        plugin = WorkflowPlugin()
        workflows = [
            {
                "id": "custom-workflow",
                "name": "Custom",
                "description": "From config",
                "steps": [{"command": "url {clipboard}"}],
            }
        ]

        with patch(
            "src.plugins.workflow_tool.config_manager.get_workflows",
            return_value=workflows,
        ):
            results = plugin.execute("wf")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "workflow_run")
        self.assertEqual(results[0]["path"], "custom-workflow")
        self.assertEqual(results[0]["workflow_desc"], "From config")

    def test_execute_keeps_input_suffix_in_action_path(self):
        plugin = WorkflowPlugin()
        workflows = [
            {
                "id": "clip-url-md5",
                "name": "Clip Url Md5",
                "description": "From config",
                "steps": [{"command": "url {clipboard}"}],
            }
        ]

        with patch(
            "src.plugins.workflow_tool.config_manager.get_workflows",
            return_value=workflows,
        ):
            results = plugin.execute("wf clip-url-md5 hello world")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "workflow_run")
        self.assertEqual(results[0]["path"], "clip-url-md5 hello world")

    def test_handle_action_fails_when_plugin_missing(self):
        workflow = {
            "id": "clip-url",
            "name": "x",
            "description": "x",
            "steps": [{"command": "url {clipboard}", "pick": "编码结果"}],
        }

        msg, copy_mock = self._run_action(workflow, [])

        self.assertIn("工作流失败: 第1步未找到插件", msg)
        copy_mock.assert_not_called()

    def test_handle_action_fails_when_step_command_empty(self):
        workflow = {
            "id": "bad-step",
            "name": "x",
            "description": "x",
            "steps": [{"command": "   "}],
        }

        msg, copy_mock = self._run_action(
            workflow, [_FakeUrl()], bypass_normalization=True
        )

        self.assertIn("工作流失败: 第1步命令为空", msg)
        copy_mock.assert_not_called()

    def test_handle_action_fails_when_execute_raises(self):
        workflow = {
            "id": "broken-flow",
            "name": "x",
            "description": "x",
            "steps": [{"command": "broken {clipboard}"}],
        }

        msg, copy_mock = self._run_action(workflow, [_FakeBroken()])

        self.assertIn("工作流失败: 第1步执行异常", msg)
        copy_mock.assert_not_called()

    def test_handle_action_fails_on_empty_or_non_list_results(self):
        class _EmptyResultPlugin:
            def get_keywords(self):
                return ["url"]

            def execute(self, query):
                return []

        class _NonListResultPlugin:
            def get_keywords(self):
                return ["url"]

            def execute(self, query):
                return "bad"

        workflow = {
            "id": "bad-result",
            "name": "x",
            "description": "x",
            "steps": [{"command": "url {clipboard}"}],
        }

        msg_empty, copy_empty = self._run_action(workflow, [_EmptyResultPlugin()])
        msg_nonlist, copy_nonlist = self._run_action(workflow, [_NonListResultPlugin()])

        self.assertIn("工作流失败: 第1步未匹配到结果", msg_empty)
        self.assertIn("工作流失败: 第1步未匹配到结果", msg_nonlist)
        copy_empty.assert_not_called()
        copy_nonlist.assert_not_called()

    def test_handle_action_fails_when_result_path_empty(self):
        class _EmptyPathPlugin:
            def get_keywords(self):
                return ["url"]

            def execute(self, query):
                return [{"name": "编码结果: x", "path": "", "type": "copy_result"}]

        workflow = {
            "id": "empty-path",
            "name": "x",
            "description": "x",
            "steps": [{"command": "url {clipboard}", "pick": "编码结果"}],
        }

        msg, copy_mock = self._run_action(workflow, [_EmptyPathPlugin()])

        self.assertIn("工作流失败: 第1步结果为空", msg)
        copy_mock.assert_not_called()

    def test_handle_action_fails_when_clipboard_write_fails(self):
        workflow = {
            "id": "clip-url",
            "name": "x",
            "description": "x",
            "steps": [{"command": "url {clipboard}", "pick": "编码结果"}],
        }

        msg, copy_mock = self._run_action(workflow, [_FakeUrl()], copy_result=False)

        self.assertEqual(msg, "工作流失败: 无法写入剪贴板")
        copy_mock.assert_called_once_with("E(abc)")

    def test_handle_action_skips_malformed_result_items(self):
        class _MalformedResultsPlugin:
            def get_keywords(self):
                return ["url"]

            def execute(self, query):
                return [None, 1, "bad"]

        workflow = {
            "id": "malformed",
            "name": "x",
            "description": "x",
            "steps": [{"command": "url {clipboard}", "pick": "编码结果"}],
        }

        msg, copy_mock = self._run_action(workflow, [_MalformedResultsPlugin()])

        self.assertIn("工作流失败: 第1步未匹配到结果", msg)
        copy_mock.assert_not_called()
