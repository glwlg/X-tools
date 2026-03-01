import os
import re
import importlib
import win32com.client
import pythoncom

lazy_pinyin = None
try:
    _pypinyin = importlib.import_module("pypinyin")
    lazy_pinyin = getattr(_pypinyin, "lazy_pinyin", None)
except Exception:
    lazy_pinyin = None


INITIAL_RANGES = [
    (-20319, "a"),
    (-20284, "b"),
    (-19776, "c"),
    (-19219, "d"),
    (-18711, "e"),
    (-18527, "f"),
    (-18240, "g"),
    (-17923, "h"),
    (-17418, "j"),
    (-16475, "k"),
    (-16213, "l"),
    (-15641, "m"),
    (-15166, "n"),
    (-14923, "o"),
    (-14915, "p"),
    (-14631, "q"),
    (-14150, "r"),
    (-14091, "s"),
    (-13319, "t"),
    (-12839, "w"),
    (-12557, "x"),
    (-11848, "y"),
    (-11056, "z"),
]


class AppScanner:
    def __init__(self):
        self.apps = []
        # Shell is created per thread if needed, or we initialize here but
        # strictly speaking WScript.Shell is apartment threaded.
        # Safer to create it inside the thread that uses it.

    @staticmethod
    def _normalize(text):
        return text.lower().strip()

    @staticmethod
    def _compact(text):
        return re.sub(r"\s+", "", text)

    @staticmethod
    def _char_initial(ch):
        if not ch:
            return ""

        lower = ch.lower()
        if "a" <= lower <= "z" or "0" <= lower <= "9":
            return lower

        try:
            gbk = ch.encode("gbk")
        except Exception:
            return ""

        if len(gbk) < 2:
            return ""

        code = gbk[0] * 256 + gbk[1] - 65536
        for i in range(len(INITIAL_RANGES) - 1):
            lower_bound, initial = INITIAL_RANGES[i]
            upper_bound, _ = INITIAL_RANGES[i + 1]
            if lower_bound <= code < upper_bound:
                return initial

        if code >= INITIAL_RANGES[-1][0]:
            return INITIAL_RANGES[-1][1]

        return ""

    def _build_search_fields(self, name):
        lower = self._normalize(name)
        compact = self._compact(lower)
        initials = "".join(self._char_initial(ch) for ch in name)

        pinyin_full = ""
        if lazy_pinyin is not None:
            try:
                pinyin_full = "".join(lazy_pinyin(name)).lower()
            except Exception:
                pinyin_full = ""

        return {
            "_search_lower": lower,
            "_search_compact": compact,
            "_search_initials": initials,
            "_search_pinyin": pinyin_full,
        }

    @staticmethod
    def _score_match(app, query_lower, query_compact):
        score = 0

        lower = app.get("_search_lower", "")
        compact = app.get("_search_compact", "")
        initials = app.get("_search_initials", "")
        pinyin = app.get("_search_pinyin", "")

        if query_lower in lower:
            score = max(score, 100 if lower.startswith(query_lower) else 80)

        if query_compact and query_compact in compact:
            score = max(score, 95 if compact.startswith(query_compact) else 75)

        if query_compact and initials and query_compact in initials:
            score = max(score, 110 if initials.startswith(query_compact) else 85)

        if query_compact and pinyin and query_compact in pinyin:
            score = max(score, 105 if pinyin.startswith(query_compact) else 82)

        return score

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
                                    app_item = {
                                        "name": name,
                                        "path": target,
                                        "type": "app",
                                        "icon": full_path,
                                    }
                                    app_item.update(self._build_search_fields(name))
                                    self.apps.append(app_item)
                            except Exception:
                                continue
        finally:
            pythoncom.CoUninitialize()

        return self.apps

    def search(self, query):
        if not query:
            return []

        query_lower = self._normalize(query)
        query_compact = self._compact(query_lower)

        scored = []
        for app in self.apps:
            score = self._score_match(app, query_lower, query_compact)
            if score > 0:
                scored.append((score, app))

        scored.sort(
            key=lambda item: (
                -item[0],
                len(item[1].get("name", "")),
                item[1].get("name", "").lower(),
            )
        )

        return [app for _, app in scored]


# Basic caching could be added here
app_scanner = AppScanner()
