import sys
import os
import shutil
import ctypes
import subprocess
from PyQt6.QtWidgets import QApplication, QMessageBox
from win32com.shell import shell, shellcon


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def main():
    app = QApplication(sys.argv)

    if getattr(sys, "frozen", False):
        install_dir = os.path.dirname(sys.executable)
    else:
        install_dir = os.path.dirname(os.path.abspath(__file__))

    reply = QMessageBox.question(
        None,
        "Uninstall x-tools",
        "Are you sure you want to completely remove x-tools?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )

    if reply == QMessageBox.StandardButton.No:
        sys.exit(0)

    # 1. Remove Shortcuts
    try:
        programs_path = shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAMS, None, 0)
        start_link = os.path.join(programs_path, "x-tools.lnk")
        if os.path.exists(start_link):
            os.remove(start_link)

        desktop_path = shell.SHGetFolderPath(
            0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0
        )
        desktop_link = os.path.join(desktop_path, "x-tools.lnk")
        if os.path.exists(desktop_link):
            os.remove(desktop_link)

    except Exception as e:
        print(f"Failed to remove shortcuts: {e}")

    # 2. Schedule Self-Deletion via Batch file
    try:
        batch_file = os.path.join(os.environ["TEMP"], "x-tools-uninstall.bat")

        # Need to handle path with spaces
        safe_install_dir = install_dir.replace("/", "\\")

        with open(batch_file, "w") as f:
            f.write(f"@echo off\n")
            f.write(f"timeout /t 2 /nobreak > NUL\n")
            f.write(f'rmdir /s /q "{safe_install_dir}"\n')
            f.write(f'del "%~f0"\n')

        # subprocess.CREATE_NO_WINDOW is 0x08000000
        creation_flags = 0x08000000
        subprocess.Popen([batch_file], shell=True, creationflags=creation_flags)

        QMessageBox.information(
            None,
            "Uninstalled",
            "x-tools has been removed.",
            QMessageBox.StandardButton.Ok,
        )

    except Exception as e:
        QMessageBox.critical(None, "Error", f"Uninstall fail: {e}")

    sys.exit(0)


if __name__ == "__main__":
    main()
