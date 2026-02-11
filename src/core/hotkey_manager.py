"""
Native Windows hotkey manager using RegisterHotKey API.

Unlike the `keyboard` library which uses SetWindowsHookEx (low-level hooks),
RegisterHotKey is a system-level API that:
- Does NOT get silently removed by Windows on timeout
- Does NOT require a message pump in a separate thread hook
- Is the recommended way for global hotkeys on Windows

The trade-off is it's Windows-only, but x-tools is a Windows-only app anyway.
"""

import ctypes
import ctypes.wintypes
import threading
from PyQt6.QtCore import QObject, pyqtSignal

# Windows constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000  # Prevents repeated hotkey events when key is held

WM_HOTKEY = 0x0312

# Virtual key codes
VK_MAP = {
    "a": 0x41,
    "b": 0x42,
    "c": 0x43,
    "d": 0x44,
    "e": 0x45,
    "f": 0x46,
    "g": 0x47,
    "h": 0x48,
    "i": 0x49,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "m": 0x4D,
    "n": 0x4E,
    "o": 0x4F,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
    "s": 0x53,
    "t": 0x54,
    "u": 0x55,
    "v": 0x56,
    "w": 0x57,
    "x": 0x58,
    "y": 0x59,
    "z": 0x5A,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "space": 0x20,
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}

MOD_MAP = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}


class HotkeyManager(QObject):
    """Manages global hotkeys using Windows RegisterHotKey API."""

    hotkey_triggered = pyqtSignal(int)  # Emits the hotkey ID

    def __init__(self):
        super().__init__()
        self._hotkey_id_counter = 1
        self._callbacks = {}  # {hotkey_id: callback}
        self._thread = None
        self._thread_id = None
        self._running = False

    def register(self, hotkey_str: str, callback) -> int:
        """
        Register a global hotkey.

        Args:
            hotkey_str: Hotkey string like "alt+q", "ctrl+shift+f"
            callback: Function to call when hotkey is pressed

        Returns:
            Hotkey ID for later unregistration, or -1 on failure
        """
        parts = hotkey_str.lower().split("+")
        key_name = parts[-1].strip()
        mod_names = [p.strip() for p in parts[:-1]]

        vk = VK_MAP.get(key_name)
        if vk is None:
            print(f"[HotkeyManager] Unknown key: {key_name}")
            return -1

        modifiers = MOD_NOREPEAT  # Always include NOREPEAT
        for mod in mod_names:
            mod_val = MOD_MAP.get(mod)
            if mod_val is None:
                print(f"[HotkeyManager] Unknown modifier: {mod}")
                return -1
            modifiers |= mod_val

        hotkey_id = self._hotkey_id_counter
        self._hotkey_id_counter += 1
        self._callbacks[hotkey_id] = (callback, modifiers, vk)

        # Start the listener thread if not already running
        if not self._running:
            self._start_listener()

        return hotkey_id

    def _start_listener(self):
        """Start the background thread that listens for hotkey events."""
        self._running = True
        self._thread = threading.Thread(target=self._listener_loop, daemon=True)
        self._thread.start()

    def _listener_loop(self):
        """
        Background thread: registers hotkeys and runs a Windows message loop.

        RegisterHotKey must be called from the same thread that runs the
        message loop (GetMessage), so everything happens here.
        """
        user32 = ctypes.windll.user32

        # Register all pending hotkeys
        for hk_id, (callback, modifiers, vk) in self._callbacks.items():
            result = user32.RegisterHotKey(None, hk_id, modifiers, vk)
            if result:
                print(
                    f"[HotkeyManager] Registered hotkey ID={hk_id} (mod=0x{modifiers:04x}, vk=0x{vk:02x})"
                )
            else:
                error = ctypes.GetLastError()
                print(
                    f"[HotkeyManager] Failed to register hotkey ID={hk_id}, error={error}"
                )

        # Message loop
        msg = ctypes.wintypes.MSG()
        while self._running:
            # GetMessage blocks until a message is available
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break

            if msg.message == WM_HOTKEY:
                hk_id = msg.wParam
                if hk_id in self._callbacks:
                    callback = self._callbacks[hk_id][0]
                    try:
                        callback()
                    except Exception as e:
                        print(f"[HotkeyManager] Error in hotkey callback: {e}")

        # Cleanup: unregister all hotkeys
        for hk_id in self._callbacks:
            user32.UnregisterHotKey(None, hk_id)

        print("[HotkeyManager] Listener stopped.")

    def stop(self):
        """Stop the hotkey listener."""
        self._running = False
        # Post WM_QUIT to unblock GetMessage
        if self._thread and self._thread.is_alive():
            ctypes.windll.user32.PostThreadMessageW(
                self._thread.ident,
                0x0012,
                0,
                0,  # WM_QUIT
            )
