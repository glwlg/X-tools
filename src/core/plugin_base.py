from abc import ABC, abstractmethod
from typing import Any


class PluginBase(ABC):
    @abstractmethod
    def get_name(self) -> str:
        """Returns the human-readable name of the plugin."""
        raise NotImplementedError

    @abstractmethod
    def get_description(self) -> str:
        """Returns a short description of the plugin."""
        raise NotImplementedError

    @abstractmethod
    def get_keywords(self) -> list[str]:
        """Returns a list of keywords or regex to trigger this plugin."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, query: str) -> list[dict[str, Any]]:
        """Executes the plugin logic for a given query."""
        raise NotImplementedError

    def is_direct_action(self) -> bool:
        """Returns True if this plugin should display items directly in the main list instead of entering a mode first."""
        return False

    def get_command_schema(self) -> dict[str, Any]:
        """Returns schema metadata for command hints and auto-fill forms."""
        return {
            "usage": "",
            "examples": [],
            "params": [],
        }

    @abstractmethod
    def on_enter(self) -> None:
        """Called when plugin mode is activated."""
        raise NotImplementedError

    @abstractmethod
    def on_exit(self) -> None:
        """Called when plugin mode is deactivated."""
        raise NotImplementedError
