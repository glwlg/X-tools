import ctypes
import os


def inspect():
    path = os.path.abspath("Everything64.dll")
    print(f"Loading {path}")
    try:
        # Try WinDLL
        dll = ctypes.WinDLL(path)
    except Exception as e:
        print(f"WinDLL failed: {e}")
        return

    functions = [
        "Everything_SetSearchW",
        "Everything_SetSearch",
        "Everything_Query",
        "Everything_QueryW",
        "Everything_GetNumResults",
        "Everything_GetNumResultsW",
    ]

    for func in functions:
        try:
            f = getattr(dll, func)
            print(f"[OK] {func} found: {f}")
        except AttributeError:
            print(f"[FAIL] {func} not found")


if __name__ == "__main__":
    inspect()
