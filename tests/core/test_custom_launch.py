import unittest
from unittest.mock import patch

from src.core.custom_launch import CustomLaunchManager


class TestCustomLaunchManager(unittest.TestCase):
    def setUp(self):
        self.store = {"custom_launch_items": []}
        self.get_value_patch = patch(
            "src.core.custom_launch.config_manager.get_value",
            side_effect=lambda key, default=None: self.store.get(key, default),
        )
        self.set_value_patch = patch(
            "src.core.custom_launch.config_manager.set_value",
            side_effect=lambda key, value: self.store.__setitem__(key, value),
        )
        self.get_value_patch.start()
        self.set_value_patch.start()
        self.manager = CustomLaunchManager()

    def tearDown(self):
        self.set_value_patch.stop()
        self.get_value_patch.stop()

    def test_save_and_search_launch_item(self):
        entry = self.manager.save_item(
            {
                "name": "Docs",
                "target": "C:/Docs",
                "keywords": "notes wiki",
                "enabled": True,
            }
        )

        self.assertIsNotNone(entry)
        results = self.manager.search("wiki")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["type"], "custom_launch")
        self.assertEqual(results[0]["launch_target"], "C:/Docs")

    def test_disabled_launch_item_is_not_returned(self):
        self.manager.save_item(
            {
                "name": "Hidden",
                "target": "C:/Hidden",
                "keywords": "secret",
                "enabled": False,
            }
        )

        self.assertEqual(self.manager.search("secret"), [])

    def test_launch_uses_platform_shell_without_args(self):
        entry = self.manager.save_item({"name": "Docs", "target": "C:/Docs"})

        with patch("src.core.custom_launch.open_path", return_value=True) as open_mock:
            self.assertTrue(self.manager.launch(entry["id"]))

        open_mock.assert_called_once_with("C:/Docs")


if __name__ == "__main__":
    unittest.main()
