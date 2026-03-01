import unittest

from src.core.workflow_schema import (
    DEFAULT_WORKFLOWS,
    normalize_workflows,
    validate_workflow_id,
)


class TestWorkflowSchema(unittest.TestCase):
    def test_normalize_invalid_payload_returns_default(self):
        workflows = normalize_workflows({"bad": "value"})
        self.assertEqual(workflows, DEFAULT_WORKFLOWS)
        self.assertIsNot(workflows, DEFAULT_WORKFLOWS)

    def test_non_string_fields_are_rejected(self):
        workflows = normalize_workflows(
            [
                {
                    "id": None,
                    "name": "Valid",
                    "description": "desc",
                    "steps": [{"command": "hash x", "pick": "MD5"}],
                },
                {
                    "id": "valid-id",
                    "name": None,
                    "description": "desc",
                    "steps": [{"command": "hash x", "pick": "MD5"}],
                },
                {
                    "id": "valid-2",
                    "name": "Name",
                    "description": None,
                    "steps": [{"command": "hash x", "pick": None}],
                },
            ]
        )

        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]["id"], "valid-2")
        self.assertEqual(workflows[0]["description"], "")
        self.assertEqual(workflows[0]["steps"], [{"command": "hash x"}])

    def test_duplicate_ids_are_removed_case_insensitive(self):
        workflows = normalize_workflows(
            [
                {
                    "id": "Clip-MD5",
                    "name": "A",
                    "description": "one",
                    "steps": [{"command": "hash {clipboard}", "pick": "MD5"}],
                },
                {
                    "id": "clip-md5",
                    "name": "B",
                    "description": "two",
                    "steps": [{"command": "hash {clipboard}", "pick": "MD5"}],
                },
            ]
        )

        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]["id"], "clip-md5")
        self.assertEqual(workflows[0]["name"], "A")

    def test_validate_workflow_id_edge_cases(self):
        self.assertFalse(validate_workflow_id("-"))
        self.assertFalse(validate_workflow_id("a-"))
        self.assertFalse(validate_workflow_id("-a"))

    def test_validate_workflow_id(self):
        self.assertTrue(validate_workflow_id("clip-url-md5"))
        self.assertFalse(validate_workflow_id("ClipURL"))
        self.assertFalse(validate_workflow_id("bad id"))

    def test_step_filtering(self):
        workflows = normalize_workflows(
            [
                {
                    "id": "wf-1",
                    "name": "Workflow",
                    "description": "desc",
                    "steps": [
                        {"command": "  hash abc  ", "pick": "  MD5  "},
                        {"command": "   ", "pick": "MD5"},
                        {"command": None, "pick": "MD5"},
                        {"command": "url abc", "pick": 1},
                        "invalid-step",
                    ],
                }
            ]
        )

        self.assertEqual(
            workflows,
            [
                {
                    "id": "wf-1",
                    "name": "Workflow",
                    "description": "desc",
                    "steps": [
                        {"command": "hash abc", "pick": "MD5"},
                        {"command": "url abc"},
                    ],
                }
            ],
        )
