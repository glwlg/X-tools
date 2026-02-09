import ctypes
import os
import sys


def check_everything_dll():
    dll_name = "Everything64.dll"
    possible_paths = [
        dll_name,
        os.path.join(os.getcwd(), dll_name),
        r"C:\Program Files\Everything\Everything64.dll",
        r"C:\Program Files (x86)\Everything\Everything64.dll",
    ]

    found = False
    for path in possible_paths:
        if os.path.exists(path):
            try:
                ctypes.WinDLL(path)
                print(f"[OK] Found and loaded {dll_name} at {path}")
                found = True
                break
            except Exception as e:
                print(f"[ERROR] Found {path} but failed to load: {e}")

    if not found:
        print(f"[MISSING] Could not find {dll_name}.")
        print(
            "Please download the 'Everything SDK' from voidtools.com and place 'Everything64.dll' in this folder:"
        )
        print(f"  {os.getcwd()}")
        return False

    return True


if __name__ == "__main__":
    if check_everything_dll():
        sys.exit(0)
    else:
        sys.exit(1)
