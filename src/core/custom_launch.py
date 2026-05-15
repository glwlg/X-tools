import os
import re
import shlex
import subprocess
import uuid

from PyQt6.QtCore import QObject, pyqtSignal

from src.core.config import config_manager
from src.core.logger import get_logger
from src.platform.shell import open_path


logger = get_logger(__name__)

URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def _split_keywords(value):
    if isinstance(value, list):
        raw_parts = value
    else:
        raw_parts = re.split(r"[,，;；\s]+", str(value or ""))
    return [str(part).strip() for part in raw_parts if str(part).strip()]


def normalize_launch_item(item):
    if not isinstance(item, dict):
        return None

    name = str(item.get("name", "")).strip()
    target = str(item.get("target") or item.get("path") or "").strip()
    if not name and target:
        name = os.path.splitext(os.path.basename(target.rstrip("\\/")))[0] or target

    if not name or not target:
        return None

    entry_id = str(item.get("id", "")).strip() or str(uuid.uuid4())
    return {
        "id": entry_id,
        "name": name,
        "target": target,
        "args": str(item.get("args", "")).strip(),
        "working_dir": str(item.get("working_dir", "")).strip(),
        "keywords": _split_keywords(item.get("keywords", [])),
        "enabled": bool(item.get("enabled", True)),
    }


def normalize_launch_items(items):
    if not isinstance(items, list):
        return []

    normalized = []
    seen = set()
    for item in items:
        entry = normalize_launch_item(item)
        if not entry:
            continue
        if entry["id"] in seen:
            entry["id"] = str(uuid.uuid4())
        seen.add(entry["id"])
        normalized.append(entry)
    return normalized


class CustomLaunchManager(QObject):
    items_changed = pyqtSignal()

    def get_items(self, enabled_only=False):
        raw = config_manager.get_value("custom_launch_items", [])
        items = normalize_launch_items(raw)
        if raw != items:
            config_manager.set_value("custom_launch_items", items)
        if enabled_only:
            items = [item for item in items if item.get("enabled", True)]
        return items

    def set_items(self, items):
        config_manager.set_value("custom_launch_items", normalize_launch_items(items))
        self.items_changed.emit()

    def get_item(self, entry_id):
        key = str(entry_id).strip()
        if not key:
            return None
        for item in self.get_items(enabled_only=False):
            if item.get("id") == key:
                return dict(item)
        return None

    def save_item(self, payload):
        entry = normalize_launch_item(payload)
        if not entry:
            return None

        items = self.get_items(enabled_only=False)
        replaced = False
        for idx, item in enumerate(items):
            if item.get("id") == entry["id"]:
                items[idx] = entry
                replaced = True
                break
        if not replaced:
            items.append(entry)

        self.set_items(items)
        return dict(entry)

    def delete_item(self, entry_id):
        key = str(entry_id).strip()
        if not key:
            return False
        items = self.get_items(enabled_only=False)
        updated = [item for item in items if item.get("id") != key]
        if len(updated) == len(items):
            return False
        self.set_items(updated)
        return True

    @staticmethod
    def _score_match(item, query):
        text = str(query or "").strip().lower()
        if not text:
            return 50

        fields = [
            str(item.get("name", "")),
            str(item.get("target", "")),
            os.path.basename(str(item.get("target", ""))),
            " ".join(item.get("keywords", [])),
        ]
        score = 0
        for field in fields:
            value = field.lower()
            if not value:
                continue
            if value == text:
                score = max(score, 120)
            elif value.startswith(text):
                score = max(score, 100)
            elif text in value:
                score = max(score, 72)
        return score

    def search(self, query, limit=20):
        scored = []
        for item in self.get_items(enabled_only=True):
            score = self._score_match(item, query)
            if score > 0:
                scored.append((score, item))

        scored.sort(
            key=lambda pair: (
                -pair[0],
                len(pair[1].get("name", "")),
                pair[1].get("name", "").lower(),
            )
        )
        return [self._to_search_result(item) for _, item in scored[: max(1, limit)]]

    @staticmethod
    def _to_search_result(item):
        keywords = " ".join(item.get("keywords", []))
        return {
            "type": "custom_launch",
            "name": str(item.get("name", "")),
            "path": str(item.get("id", "")),
            "launch_id": str(item.get("id", "")),
            "launch_target": str(item.get("target", "")),
            "launch_args": str(item.get("args", "")),
            "launch_working_dir": str(item.get("working_dir", "")),
            "launch_keywords": keywords,
        }

    def launch(self, entry_or_id):
        entry = (
            dict(entry_or_id)
            if isinstance(entry_or_id, dict)
            else self.get_item(str(entry_or_id))
        )
        if not entry:
            return False

        target = str(entry.get("target", "")).strip()
        if not target:
            return False

        args = str(entry.get("args", "")).strip()
        cwd = str(entry.get("working_dir", "")).strip()
        cwd_value = cwd if cwd and os.path.isdir(cwd) else None

        try:
            if not args:
                return open_path(target)

            argv = [target] + shlex.split(args, posix=False)
            subprocess.Popen(argv, cwd=cwd_value)
            return True
        except Exception as e:
            logger.warning("Failed to launch custom item %s: %s", target, e)
            return False

    @staticmethod
    def is_url(target):
        return bool(URL_RE.match(str(target or "").strip()))


custom_launch_manager = CustomLaunchManager()
