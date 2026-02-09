from abc import ABC, abstractmethod


class PluginBase(ABC):
    @abstractmethod
    def get_keywords(self):
        """Returns a list of keywords or regex to trigger this plugin."""
        pass

    @abstractmethod
    def execute(self, query):
        """Executes the plugin logic for a given query."""
        pass

    @abstractmethod
    def on_enter(self):
        """Called when plugin mode is activated."""
        pass

    @abstractmethod
    def on_exit(self):
        """Called when plugin mode is deactivated."""
        pass
