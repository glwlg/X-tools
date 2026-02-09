
import sys
import os
import zipfile
import shutil
from win32com.client import Dispatch
from win32com.shell import shell, shellcon
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt

def get_special_folder(csidl):
    return shell.SHGetFolderPath(0, csidl, None, 0)

def message_box(title, text, icon=QMessageBox.Icon.Information):
    msg = QMessageBox()
    msg.setIcon(icon)
    msg.setText(text)
    msg.setWindowTitle(title)
    msg.exec()

def create_shortcut(target, location, name, icon=None):
    try:
        shell = Dispatch('WScript.Shell')
        shortcut_path = os.path.join(location, f"{name}.lnk")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = target
        shortcut.WorkingDirectory = os.path.dirname(target)
        if icon:
            shortcut.IconLocation = icon
        shortcut.save()
    except Exception as e:
        print(f"Failed to create shortcut: {e}")

def main():
    app = QApplication(sys.argv)
    
    install_dir = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "x-tools")
    
    reply = QMessageBox.question(
        None, 
        "Install x-tools", 
        f"Do you want to install x-tools to {install_dir}?\n\nThis will overwrite existing installation.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    
    if reply == QMessageBox.StandardButton.No:
        sys.exit(0)

    desktop_shortcut = QMessageBox.question(
        None,
        "Create Desktop Shortcut",
        "Create a desktop shortcut?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    ) == QMessageBox.StandardButton.Yes

    progress = QProgressDialog("Installing x-tools...", "Cancel", 0, 100)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setAutoClose(False)
    progress.show()
    
    try:
        archive_path = os.path.join(sys._MEIPASS, "app_archive.zip") if hasattr(sys, '_MEIPASS') else "app_archive.zip"
        
        if os.path.exists(install_dir):
            shutil.rmtree(install_dir, ignore_errors=True)
        os.makedirs(install_dir, exist_ok=True)
        
        progress.setValue(20)
        QApplication.processEvents()

        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(install_dir)
            
        progress.setValue(80)
        QApplication.processEvents()

        exe_path = os.path.join(install_dir, "x-tools.exe")
        icon_path = os.path.join(install_dir, "logo.ico") # Use the standalone ico file
        programs_path = get_special_folder(shellcon.CSIDL_PROGRAMS)

        if not os.path.exists(programs_path):
             os.makedirs(programs_path, exist_ok=True)
        
        # Main App Shortcut
        create_shortcut(exe_path, programs_path, "x-tools", icon=icon_path)
        
        # Uninstaller Shortcut
        uninstall_path = os.path.join(install_dir, "uninstall.exe")
        create_shortcut(uninstall_path, programs_path, "Uninstall x-tools", icon=uninstall_path)
        
        if desktop_shortcut:
            desktop_path = get_special_folder(shellcon.CSIDL_DESKTOPDIRECTORY)
            create_shortcut(exe_path, desktop_path, "x-tools", icon=icon_path)
            
        progress.setValue(100)
        
        # Force Windows to refresh icon cache
        try:
            import ctypes
            # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except:
            pass

        message_box("Installation Complete", "x-tools has been successfully installed.", QMessageBox.Icon.Information)

    except Exception as e:
        message_box("Installation Failed", f"Error: {e}", QMessageBox.Icon.Critical)
        
    sys.exit(0)

if __name__ == "__main__":
    main()
