import sys
import time
import atexit
from PyQt6.QtWidgets import QApplication
from src.core.logger import setup_logging, get_logger
from src.core.metrics import metrics_store
from src.platform.single_instance import SingleInstanceLock


setup_logging()

from src.ui.search_window import SearchWindow


def main():
    startup_start = time.perf_counter()

    single_instance = SingleInstanceLock("Global\\XToolsSingletonMutex")
    if not single_instance.acquire():
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
