import json
import os
import tempfile
import unittest
import copy
from unittest.mock import patch

from src.core.config import ConfigManager, DEFAULT_CONFIG
from src.core.workflow_schema import DEFAULT_WORKFLOWS, normalize_workflows


class TestWorkflowConfig(unittest.TestCase):
    def test_default_config_contains_workflows(self):
        self.assertIn("workflows", DEFAULT_CONFIG)
        self.assertEqual(DEFAULT_CONFIG["workflows"], DEFAULT_WORKFLOWS)

    def test_load_config_normalizes_workflows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "config.json")
            theme_file = os.path.join(temp_dir, "themes.json")
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump({"workflows": {"bad": "value"}}, f)

            with (
                patch("src.core.config.CONFIG_FILE", config_file),
                patch("src.core.config.THEME_FILE", theme_file),
            ):
                manager = ConfigManager()

            self.assertEqual(
                manager.get_value("workflows"),
                normalize_workflows({"bad": "value"}),
            )

    def test_set_and_get_workflows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "config.json")
            theme_file = os.path.join(temp_dir, "themes.json")
            with (
                patch("src.core.config.CONFIG_FILE", config_file),
                patch("src.core.config.THEME_FILE", theme_file),
            ):
                manager = ConfigManager()

                workflows = [
                    {
                        "id": "clip-url-md5",
                        "name": "Clipboard URL to MD5",
                        "description": "Chain workflow",
                        "steps": [
                            {"command": "url {clipboard}", "pick": "编码结果"},
                            {"command": "hash {prev}", "pick": "MD5"},
                        ],
                    }
                ]
                manager.set_workflows(workflows)

                self.assertEqual(
                    manager.get_workflows(), normalize_workflows(workflows)
                )

    def test_manager_config_workflows_mutation_does_not_mutate_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "config.json")
            theme_file = os.path.join(temp_dir, "themes.json")
            with (
                patch("src.core.config.CONFIG_FILE", config_file),
                patch("src.core.config.THEME_FILE", theme_file),
            ):
                manager = ConfigManager()
                original_defaults = copy.deepcopy(DEFAULT_CONFIG["workflows"])

                manager.config["workflows"][0]["steps"][0]["command"] = "mutated"

                self.assertEqual(DEFAULT_CONFIG["workflows"], original_defaults)

    def test_get_workflows_returns_mutation_safe_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "config.json")
            theme_file = os.path.join(temp_dir, "themes.json")
            with (
                patch("src.core.config.CONFIG_FILE", config_file),
                patch("src.core.config.THEME_FILE", theme_file),
            ):
                manager = ConfigManager()

                first = manager.get_workflows()
                first[0]["name"] = "changed"
                first[0]["steps"][0]["command"] = "changed"

                second = manager.get_workflows()

                self.assertNotEqual(second[0]["name"], "changed")
                self.assertNotEqual(second[0]["steps"][0]["command"], "changed")

    def test_set_workflows_persists_across_new_manager_instance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "config.json")
            theme_file = os.path.join(temp_dir, "themes.json")
            workflows = [
                {
                    "id": "clip-url-md5",
                    "name": "Clipboard URL to MD5",
                    "description": "Chain workflow",
                    "steps": [
                        {"command": "url {clipboard}", "pick": "编码结果"},
                        {"command": "hash {prev}", "pick": "MD5"},
                    ],
                }
            ]

            with (
                patch("src.core.config.CONFIG_FILE", config_file),
                patch("src.core.config.THEME_FILE", theme_file),
            ):
                manager = ConfigManager()
                manager.set_workflows(workflows)

                reloaded = ConfigManager()

                self.assertEqual(
                    reloaded.get_workflows(), normalize_workflows(workflows)
                )
