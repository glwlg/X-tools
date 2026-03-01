import sys
import ctypes
import time
import atexit
from PyQt6.QtWidgets import QApplication
from src.core.logger import setup_logging, get_logger
from src.core.metrics import metrics_store


setup_logging()

from src.ui.search_window import SearchWindow


def main():
    startup_start = time.perf_counter()

    # Single Instance Check
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Global\\XToolsSingletonMutex"
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # App is already running. For simplicity, just exit.
        # Ideally would bring existing window to front, but that requires more complex IPC.
        sys.exit(0)

    setup_logging()
    logger = get_logger(__name__)
    atexit.register(metrics_store.flush)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Important for tray app

    window = SearchWindow()
    startup_elapsed = (time.perf_counter() - startup_start) * 1000
    metrics_store.record("startup.total", startup_elapsed)
    # window.show() # Uncomment for debugging startup

    logger.info("x-tools started. Press Alt+Q to search.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
