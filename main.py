import sys
import ctypes
from PyQt6.QtWidgets import QApplication
from src.ui.search_window import SearchWindow


def main():
    # Single Instance Check
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Global\\XToolsSingletonMutex"
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # App is already running. For simplicity, just exit.
        # Ideally would bring existing window to front, but that requires more complex IPC.
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Important for tray app

    window = SearchWindow()
    # window.show() # Uncomment for debugging startup

    print("x-tools started. Press Alt+Q to search.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
