from src.platform.runtime import CAPABILITY_FILE_SEARCH, supports_capabilities


class NullFileSearchProvider:
    def search(self, query, max_results=20):
        return []


class WindowsEverythingFileSearchProvider:
    def __init__(self):
        from src.core.everything import everything_client

        self.client = everything_client

    def search(self, query, max_results=20):
        if self.client is None:
            return []
        return self.client.search(query, max_results=max_results)


def create_file_search_provider():
    if not supports_capabilities((CAPABILITY_FILE_SEARCH,)):
        return NullFileSearchProvider()

    try:
        return WindowsEverythingFileSearchProvider()
    except Exception:
        return NullFileSearchProvider()


file_search_provider = create_file_search_provider()

