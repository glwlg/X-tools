import os
import win32com.client
import pythoncom


class AppScanner:
    def __init__(self):
        self.apps = []
        # Shell is created per thread if needed, or we initialize here but
        # strictly speaking WScript.Shell is apartment threaded.
        # Safer to create it inside the thread that uses it.

    def scan(self):
        """Scans Start Menu folders for shortcuts."""
        pythoncom.CoInitialize()  # Initialize COM for this thread
        try:
            shell = win32com.client.Dispatch("WScript.Shell")
            self.apps = []
            paths = [
                os.path.expandvars(
                    r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"
                ),
                os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
            ]

            for path in paths:
                if not os.path.exists(path):
                    continue

                for root, dirs, files in os.walk(path):
                    for file in files:
                        if file.endswith(".lnk"):
                            full_path = os.path.join(root, file)
                            try:
                                # Resolve shortcut
                                shortcut = shell.CreateShortCut(full_path)
                                target = shortcut.Targetpath
                                if target:
                                    name = os.path.splitext(file)[0]
                                    self.apps.append(
                                        {
                                            "name": name,
                                            "path": target,
                                            "type": "app",
                                            "icon": full_path,
                                        }
                                    )
                            except Exception:
                                continue
        finally:
            pythoncom.CoUninitialize()

        return self.apps

    def search(self, query):
        if not query:
            return []

        query = query.lower()
        results = []
        for app in self.apps:
            if query in app["name"].lower():
                results.append(app)
        return results


# Basic caching could be added here
app_scanner = AppScanner()
