import ctypes

from src.platform.runtime import PLATFORM_WINDOWS, current_platform


class SingleInstanceLock:
    def __init__(self, name: str):
        self.name = name
        self.handle = None

    def acquire(self) -> bool:
        if current_platform() != PLATFORM_WINDOWS:
            return True

        kernel32 = ctypes.windll.kernel32
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        return kernel32.GetLastError() != 183

