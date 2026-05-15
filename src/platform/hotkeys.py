from src.core.logger import get_logger
from src.platform.runtime import CAPABILITY_GLOBAL_HOTKEY, supports_capabilities


logger = get_logger(__name__)


class UnsupportedHotkeyManager:
    def register(self, hotkey_str: str, callback) -> int:
        logger.info("Global hotkey ignored on this platform: %s", hotkey_str)
        return -1

    def start(self):
        return None

    def stop(self):
        return None

    def restart(self):
        return None


def create_hotkey_manager():
    if not supports_capabilities((CAPABILITY_GLOBAL_HOTKEY,)):
        return UnsupportedHotkeyManager()

    try:
        from src.core.hotkey_manager import HotkeyManager

        return HotkeyManager()
    except Exception as exc:
        logger.warning("Falling back to unsupported hotkey manager: %s", exc)
        return UnsupportedHotkeyManager()

