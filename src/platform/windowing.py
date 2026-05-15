import ctypes

from src.platform.runtime import PLATFORM_WINDOWS, current_platform


def force_foreground_window(hwnd: int) -> bool:
    if current_platform() != PLATFORM_WINDOWS:
        return False

    try:
        foreground_window = ctypes.windll.user32.GetForegroundWindow()
        current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        foreground_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(
            foreground_window, None
        )

        if current_thread_id != foreground_thread_id:
            ctypes.windll.user32.AttachThreadInput(
                foreground_thread_id, current_thread_id, True
            )
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.AttachThreadInput(
                foreground_thread_id, current_thread_id, False
            )
        else:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False

