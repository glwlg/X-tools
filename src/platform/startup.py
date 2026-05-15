def set_startup_enabled(app_name: str, command: str, enable: bool) -> bool:
    try:
        import winreg
    except ImportError:
        return False

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS
        )
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
