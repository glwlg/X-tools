import hashlib
import json
import os
import time
import uuid

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from src.core.logger import get_logger


logger = get_logger(__name__)

APPDATA_DIR = os.getenv("APPDATA") or os.path.expanduser("~")
XTOOLS_DIR = os.path.join(APPDATA_DIR, "x-tools")
HISTORY_FILE = os.path.join(XTOOLS_DIR, "clipboard_history.json")
IMAGE_DIR = os.path.join(XTOOLS_DIR, "clipboard_images")


class ClipboardHistoryManager(QObject):
    entries_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._entries = []
        self._clipboard = None
        self._is_started = False
        self._is_applying = False
        self._max_entries = 200
        self._last_signature = ""
        self._load()

    def _load(self):
        os.makedirs(XTOOLS_DIR, exist_ok=True)
        os.makedirs(IMAGE_DIR, exist_ok=True)

        if not os.path.exists(HISTORY_FILE):
            self._entries = []
            return

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)

            entries = []
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue

                    entry_type = str(item.get("type", "")).strip()
                    if entry_type not in {"text", "image"}:
                        continue

                    entry = {
                        "id": str(item.get("id", "")).strip() or str(uuid.uuid4()),
                        "type": entry_type,
                        "text": str(item.get("text", "")),
                        "image_path": str(item.get("image_path", "")),
                        "created_at": float(item.get("created_at", time.time())),
                        "pinned": bool(item.get("pinned", False)),
                        "signature": str(item.get("signature", "")),
                        "width": int(item.get("width", 0) or 0),
                        "height": int(item.get("height", 0) or 0),
                    }

                    if entry["type"] == "image" and (
                        not entry["image_path"]
                        or not os.path.exists(entry["image_path"])
                    ):
                        continue

                    entries.append(entry)

            self._entries = entries[: self._max_entries]
        except Exception as e:
            logger.warning("Failed to load clipboard history: %s", e)
            self._entries = []

    def _save(self):
        try:
            os.makedirs(XTOOLS_DIR, exist_ok=True)
            os.makedirs(IMAGE_DIR, exist_ok=True)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Failed to save clipboard history: %s", e)

    def start(self, clipboard=None):
        if self._is_started:
            return

        self._clipboard = clipboard or QApplication.clipboard()
        if self._clipboard is None:
            return

        self._clipboard.dataChanged.connect(self._on_clipboard_changed)
        self._is_started = True

    def _make_text_entry(self, text):
        content = text.strip()
        if not content:
            return None

        digest = hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()
        return {
            "id": str(uuid.uuid4()),
            "type": "text",
            "text": content,
            "image_path": "",
            "created_at": time.time(),
            "pinned": False,
            "signature": f"txt:{digest}",
            "width": 0,
            "height": 0,
        }

    def _make_image_entry(self, image):
        if not isinstance(image, QImage) or image.isNull():
            return None

        os.makedirs(IMAGE_DIR, exist_ok=True)
        image_id = str(uuid.uuid4())
        image_path = os.path.join(IMAGE_DIR, f"{image_id}.png")

        if not image.save(image_path, "PNG"):
            return None

        try:
            with open(image_path, "rb") as f:
                digest = hashlib.sha1(f.read()).hexdigest()
        except Exception:
            digest_source = (
                f"{image.width()}x{image.height()}:{os.path.getsize(image_path)}"
            )
            digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()
        return {
            "id": image_id,
            "type": "image",
            "text": "",
            "image_path": image_path,
            "created_at": time.time(),
            "pinned": False,
            "signature": f"img:{digest}",
            "width": image.width(),
            "height": image.height(),
        }

    def _on_clipboard_changed(self):
        if self._is_applying:
            return

        if self._clipboard is None:
            return

        mime = self._clipboard.mimeData()
        if mime is None:
            return

        entry = None
        if mime.hasImage():
            image = self._clipboard.image()
            if image is not None and not image.isNull():
                entry = self._make_image_entry(image)
        elif mime.hasText():
            entry = self._make_text_entry(self._clipboard.text())

        if not entry:
            return

        signature = entry.get("signature", "")
        if signature and signature == self._last_signature:
            if entry.get("type") == "image":
                self._safe_remove_file(entry.get("image_path", ""))
            return

        if (
            self._entries
            and signature
            and self._entries[0].get("signature") == signature
        ):
            if entry.get("type") == "image":
                self._safe_remove_file(entry.get("image_path", ""))
            return

        self._last_signature = signature
        self._entries.insert(0, entry)
        self._trim()
        self._save()
        self.entries_changed.emit()

    def _trim(self):
        while len(self._entries) > self._max_entries:
            removed = self._entries.pop()
            if removed.get("type") == "image":
                self._safe_remove_file(removed.get("image_path", ""))

    @staticmethod
    def _safe_remove_file(path):
        if not path:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def get_entries(self, query="", limit=200):
        text = query.strip().lower()
        items = self._entries
        if text:
            filtered = []
            for entry in items:
                if entry.get("type") == "text":
                    value = str(entry.get("text", "")).lower()
                    if text in value:
                        filtered.append(entry)
                else:
                    marker = f"{entry.get('width', 0)}x{entry.get('height', 0)}"
                    if text in marker or text in "image 图片":
                        filtered.append(entry)
            items = filtered

        sorted_items = sorted(
            items,
            key=lambda e: (
                0 if e.get("pinned", False) else 1,
                -float(e.get("created_at", 0)),
            ),
        )
        return [dict(item) for item in sorted_items[: max(1, limit)]]

    def get_entry(self, entry_id):
        key = str(entry_id).strip()
        if not key:
            return None
        for entry in self._entries:
            if entry.get("id") == key:
                return dict(entry)
        return None

    def toggle_pin(self, entry_id):
        key = str(entry_id).strip()
        if not key:
            return False
        for entry in self._entries:
            if entry.get("id") == key:
                entry["pinned"] = not bool(entry.get("pinned", False))
                self._save()
                self.entries_changed.emit()
                return bool(entry["pinned"])
        return False

    def delete_entry(self, entry_id):
        key = str(entry_id).strip()
        if not key:
            return False

        for idx, entry in enumerate(self._entries):
            if entry.get("id") == key:
                removed = self._entries.pop(idx)
                if removed.get("type") == "image":
                    self._safe_remove_file(removed.get("image_path", ""))
                self._save()
                self.entries_changed.emit()
                return True
        return False

    def clear_unpinned(self):
        remaining = []
        removed_count = 0
        for entry in self._entries:
            if entry.get("pinned", False):
                remaining.append(entry)
            else:
                removed_count += 1
                if entry.get("type") == "image":
                    self._safe_remove_file(entry.get("image_path", ""))

        if removed_count > 0:
            self._entries = remaining
            self._save()
            self.entries_changed.emit()
        return removed_count

    def copy_entry_to_clipboard(self, entry_id):
        entry = self.get_entry(entry_id)
        if not entry:
            return False

        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False

        self._is_applying = True
        try:
            if entry.get("type") == "text":
                clipboard.setText(str(entry.get("text", "")))
            elif entry.get("type") == "image":
                path = str(entry.get("image_path", ""))
                if not path or not os.path.exists(path):
                    return False
                image = QImage(path)
                if image.isNull():
                    return False
                clipboard.setImage(image)
            else:
                return False
        finally:
            self._last_signature = str(entry.get("signature", ""))
            QTimer.singleShot(120, self._clear_apply_flag)

        return True

    def _clear_apply_flag(self):
        self._is_applying = False

    @staticmethod
    def _entry_display_name(entry):
        if entry.get("type") == "text":
            text = str(entry.get("text", "")).replace("\n", " ").strip()
            if len(text) > 80:
                text = text[:77] + "..."
            return f"📋 {text}"

        w = int(entry.get("width", 0) or 0)
        h = int(entry.get("height", 0) or 0)
        return f"🖼️ 图片 {w}x{h}"

    def as_search_results(self, query="", limit=20):
        results = []
        for entry in self.get_entries(query=query, limit=limit):
            name = self._entry_display_name(entry)
            if entry.get("pinned", False):
                name = f"★ {name}"

            results.append(
                {
                    "type": "clipboard_entry",
                    "name": name,
                    "path": str(entry.get("id", "")),
                    "clipboard_id": str(entry.get("id", "")),
                    "clipboard_type": str(entry.get("type", "")),
                    "clipboard_text": str(entry.get("text", "")),
                    "clipboard_image_path": str(entry.get("image_path", "")),
                    "clipboard_pinned": bool(entry.get("pinned", False)),
                    "clipboard_size": f"{entry.get('width', 0)}x{entry.get('height', 0)}",
                }
            )

        return results


clipboard_history_manager = ClipboardHistoryManager()
