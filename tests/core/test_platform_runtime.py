import unittest
from unittest.mock import patch

from src.core.plugin_manager import PluginManager
from src.platform.runtime import (
    CAPABILITY_HOSTS,
    CAPABILITY_OPEN_PATH,
    PLATFORM_LINUX,
    PLATFORM_WINDOWS,
    plugin_supported,
    unsupported_plugin_reason,
)


class _FakePlugin:
    def __init__(
        self,
        name="fake",
        supported_platforms=("all",),
        required_capabilities=(),
    ):
        self._name = name
        self.supported_platforms = supported_platforms
        self.required_capabilities = required_capabilities

    def get_name(self):
        return self._name

    def get_supported_platforms(self):
        return self.supported_platforms

    def get_required_capabilities(self):
        return self.required_capabilities


class TestPlatformRuntime(unittest.TestCase):
    def test_plugin_supported_by_capability(self):
        plugin = _FakePlugin(required_capabilities=(CAPABILITY_HOSTS,))

        self.assertTrue(
            plugin_supported(
                plugin,
                platform_id=PLATFORM_WINDOWS,
                capabilities={CAPABILITY_HOSTS, CAPABILITY_OPEN_PATH},
            )
        )
        self.assertFalse(
            plugin_supported(
                plugin,
                platform_id=PLATFORM_LINUX,
                capabilities={CAPABILITY_OPEN_PATH},
            )
        )

    def test_unsupported_reason_mentions_missing_capability(self):
        plugin = _FakePlugin(required_capabilities=(CAPABILITY_HOSTS,))

        reason = unsupported_plugin_reason(
            plugin,
            platform_id=PLATFORM_LINUX,
            capabilities={CAPABILITY_OPEN_PATH},
        )

        self.assertIn(CAPABILITY_HOSTS, reason)

    def test_plugin_manager_filters_unsupported_plugins(self):
        manager = PluginManager()
        manager.plugins = [
            _FakePlugin("visible", required_capabilities=(CAPABILITY_OPEN_PATH,)),
            _FakePlugin("hidden", required_capabilities=(CAPABILITY_HOSTS,)),
        ]

        with patch(
            "src.core.plugin_manager.plugin_supported",
            side_effect=lambda plugin: plugin.get_name() == "visible",
        ):
            plugins = manager.get_plugins(enabled_only=False)

        self.assertEqual([plugin.get_name() for plugin in plugins], ["visible"])


if __name__ == "__main__":
    unittest.main()

