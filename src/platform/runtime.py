import sys
from collections.abc import Iterable


PLATFORM_ALL = "all"
PLATFORM_WINDOWS = "windows"
PLATFORM_MACOS = "macos"
PLATFORM_LINUX = "linux"
PLATFORM_UNKNOWN = "unknown"

CAPABILITY_APP_SCAN = "app_scan"
CAPABILITY_CLIPBOARD = "clipboard"
CAPABILITY_CUSTOM_LAUNCH = "custom_launch"
CAPABILITY_FILE_SEARCH = "file_search"
CAPABILITY_GLOBAL_HOTKEY = "global_hotkey"
CAPABILITY_HOSTS = "hosts"
CAPABILITY_OPEN_PATH = "open_path"
CAPABILITY_PINNED_IMAGE = "pinned_image"
CAPABILITY_SCREENSHOT = "screenshot"
CAPABILITY_STARTUP = "startup"
CAPABILITY_SYSTEM_COMMANDS = "system_commands"
CAPABILITY_TRAY = "tray"


COMMON_QT_CAPABILITIES = {
    CAPABILITY_CLIPBOARD,
    CAPABILITY_CUSTOM_LAUNCH,
    CAPABILITY_OPEN_PATH,
    CAPABILITY_PINNED_IMAGE,
    CAPABILITY_SCREENSHOT,
    CAPABILITY_TRAY,
}

PLATFORM_CAPABILITIES = {
    PLATFORM_WINDOWS: COMMON_QT_CAPABILITIES
    | {
        CAPABILITY_APP_SCAN,
        CAPABILITY_FILE_SEARCH,
        CAPABILITY_GLOBAL_HOTKEY,
        CAPABILITY_HOSTS,
        CAPABILITY_STARTUP,
        CAPABILITY_SYSTEM_COMMANDS,
    },
    # Non-Windows adapters are intentionally conservative for now. They keep
    # the application importable and hide features that still need native work.
    PLATFORM_MACOS: COMMON_QT_CAPABILITIES,
    PLATFORM_LINUX: COMMON_QT_CAPABILITIES,
    PLATFORM_UNKNOWN: COMMON_QT_CAPABILITIES,
}


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return PLATFORM_WINDOWS
    if sys.platform == "darwin":
        return PLATFORM_MACOS
    if sys.platform.startswith("linux"):
        return PLATFORM_LINUX
    return PLATFORM_UNKNOWN


def platform_label(platform_id: str | None = None) -> str:
    labels = {
        PLATFORM_WINDOWS: "Windows",
        PLATFORM_MACOS: "macOS",
        PLATFORM_LINUX: "Linux",
        PLATFORM_UNKNOWN: "Unknown",
    }
    return labels.get(platform_id or current_platform(), "Unknown")


def _normalize_values(values: Iterable[str] | None, default: tuple[str, ...]):
    if values is None:
        return default
    if isinstance(values, str):
        values = (values,)
    normalized = tuple(str(item).strip().lower() for item in values if str(item).strip())
    return normalized or default


def get_platform_capabilities(platform_id: str | None = None) -> set[str]:
    return set(PLATFORM_CAPABILITIES.get(platform_id or current_platform(), set()))


def supports_platform(
    supported_platforms: Iterable[str] | None, platform_id: str | None = None
) -> bool:
    platform_key = platform_id or current_platform()
    supported = _normalize_values(supported_platforms, (PLATFORM_ALL,))
    return PLATFORM_ALL in supported or platform_key in supported


def supports_capabilities(
    required_capabilities: Iterable[str] | None,
    platform_id: str | None = None,
    capabilities: Iterable[str] | None = None,
) -> bool:
    required = set(_normalize_values(required_capabilities, ()))
    available = (
        set(capabilities)
        if capabilities is not None
        else get_platform_capabilities(platform_id)
    )
    return required.issubset(available)


def plugin_supported(
    plugin,
    platform_id: str | None = None,
    capabilities: Iterable[str] | None = None,
) -> bool:
    supported_platforms = getattr(plugin, "get_supported_platforms", lambda: ("all",))()
    required_capabilities = getattr(plugin, "get_required_capabilities", lambda: ())()
    return supports_platform(supported_platforms, platform_id) and supports_capabilities(
        required_capabilities, platform_id, capabilities
    )


def unsupported_plugin_reason(
    plugin,
    platform_id: str | None = None,
    capabilities: Iterable[str] | None = None,
) -> str:
    platform_key = platform_id or current_platform()
    supported_platforms = getattr(plugin, "get_supported_platforms", lambda: ("all",))()
    required_capabilities = getattr(plugin, "get_required_capabilities", lambda: ())()

    if not supports_platform(supported_platforms, platform_key):
        return f"not supported on {platform_label(platform_key)}"

    available = (
        set(capabilities)
        if capabilities is not None
        else get_platform_capabilities(platform_key)
    )
    missing = set(required_capabilities) - available
    if missing:
        return f"missing capabilities: {', '.join(sorted(missing))}"

    return ""
