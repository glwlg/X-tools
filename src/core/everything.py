import ctypes
import os
import threading
import sys


# Define constants
EVERYTHING_REQUEST_FILE_NAME = 0x00000001
EVERYTHING_REQUEST_PATH = 0x00000002
EVERYTHING_REQUEST_FULL_PATH_AND_FILE_NAME = 0x00000004
EVERYTHING_REQUEST_EXTENSION = 0x00000008
EVERYTHING_REQUEST_SIZE = 0x00000010
EVERYTHING_REQUEST_DATE_CREATED = 0x00000020
EVERYTHING_REQUEST_DATE_MODIFIED = 0x00000040
EVERYTHING_REQUEST_DATE_ACCESSED = 0x00000080
EVERYTHING_REQUEST_ATTRIBUTES = 0x00000100
EVERYTHING_REQUEST_FILE_LIST_FILE_NAME = 0x00000200
EVERYTHING_REQUEST_RUN_COUNT = 0x00000400
EVERYTHING_REQUEST_DATE_RUN = 0x00000800
EVERYTHING_REQUEST_DATE_RECENTLY_CHANGED = 0x00001000
EVERYTHING_REQUEST_HIGHLIGHTED_FILE_NAME = 0x00002000
EVERYTHING_REQUEST_HIGHLIGHTED_PATH = 0x00004000
EVERYTHING_REQUEST_HIGHLIGHTED_FULL_PATH_AND_FILE_NAME = 0x00008000


class Everything:
    def __init__(self):
        self.dll = None
        self.lock = threading.Lock()
        self._load_dll()

    def _load_dll(self):
        # Try to find Everything64.dll in standard locations or user provided path
        possible_paths = [
            os.path.abspath("Everything64.dll"),
            "Everything64.dll",
            r"C:\Program Files\Everything\Everything64.dll",
            r"C:\Program Files (x86)\Everything\Everything64.dll",
        ]

        if getattr(sys, "frozen", False):
            possible_paths.insert(
                0, os.path.join(os.path.dirname(sys.executable), "Everything64.dll")
            )

        for path in possible_paths:
            if os.path.exists(path):
                try:
                    # On Python 3.8+, we might need to add directory to DLL search path
                    dll_dir = os.path.dirname(os.path.abspath(path))
                    if hasattr(os, "add_dll_directory"):
                        try:
                            os.add_dll_directory(dll_dir)
                        except Exception:
                            pass

                    self.dll = ctypes.WinDLL(path)
                    self._setup_signatures()
                    print(f"Everything SDK loaded from: {path}")
                    return
                except Exception as e:
                    print(f"Failed to load {path}: {e}")

        # If not found, try loading without path (if in PATH)
        try:
            self.dll = ctypes.WinDLL("Everything64.dll")
            self._setup_signatures()
        except OSError:
            raise FileNotFoundError(
                "Could not find Everything64.dll. Please ensure Everything is installed and the DLL is accessible."
            )

    def _setup_signatures(self):
        # Setup return types and argument types
        self.dll.Everything_SetSearchW.argtypes = [ctypes.c_wchar_p]
        self.dll.Everything_SetRequestFlags.argtypes = [ctypes.c_uint32]
        self.dll.Everything_QueryW.argtypes = [ctypes.c_bool]
        self.dll.Everything_QueryW.restype = ctypes.c_bool
        self.dll.Everything_GetNumResults.restype = ctypes.c_uint32
        self.dll.Everything_GetResultFileNameW.argtypes = [ctypes.c_uint32]
        self.dll.Everything_GetResultFileNameW.restype = ctypes.c_wchar_p
        self.dll.Everything_GetResultPathW.argtypes = [ctypes.c_uint32]
        self.dll.Everything_GetResultPathW.restype = ctypes.c_wchar_p
        self.dll.Everything_SetMax.argtypes = [ctypes.c_uint32]

    def search(self, query, max_results=20):
        with self.lock:
            if not self.dll:
                return []

            try:
                self.dll.Everything_SetSearchW(query)
                self.dll.Everything_SetRequestFlags(
                    EVERYTHING_REQUEST_FILE_NAME | EVERYTHING_REQUEST_PATH
                )
                self.dll.Everything_SetMax(max_results)

                # Execute query
                self.dll.Everything_QueryW(True)

                results = []
                num_results = self.dll.Everything_GetNumResults()

                for i in range(num_results):
                    filename = self.dll.Everything_GetResultFileNameW(i)
                    path = self.dll.Everything_GetResultPathW(i)
                    full_path = os.path.join(path, filename)
                    results.append(
                        {"name": filename, "path": full_path, "type": "file"}
                    )

                return results
            except Exception as e:
                print(f"Everything search error: {e}")
                return []


# Singleton instance
everything_client = None
try:
    everything_client = Everything()
except FileNotFoundError:
    print("Warning: Everything DLL not found. Search will not work.")
