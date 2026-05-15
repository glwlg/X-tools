from src.platform.runtime import CAPABILITY_APP_SCAN, supports_capabilities


class NullApplicationScanner:
    def scan(self):
        return []

    def search(self, query):
        return []


def create_application_scanner():
    if not supports_capabilities((CAPABILITY_APP_SCAN,)):
        return NullApplicationScanner()

    try:
        from src.core.app_scanner import AppScanner

        return AppScanner()
    except Exception:
        return NullApplicationScanner()


app_scanner = create_application_scanner()

