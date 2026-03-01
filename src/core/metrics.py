import json
import os
import statistics
import threading
import time
from typing import Any

from src.core.logger import get_logger


logger = get_logger(__name__)

APPDATA_DIR = os.getenv("APPDATA") or os.path.expanduser("~")
XTOOLS_DIR = os.path.join(APPDATA_DIR, "x-tools")
METRICS_FILE = os.path.join(XTOOLS_DIR, "metrics.json")


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    rank = (len(values) - 1) * q
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    if lower == upper:
        return float(values[lower])

    weight = rank - lower
    return float(values[lower] * (1 - weight) + values[upper] * weight)


class MetricsStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._max_events = 300
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._dirty_count = 0
        self._load()

    def _load(self):
        if not os.path.exists(METRICS_FILE):
            return

        try:
            with open(METRICS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for key, events in raw.items():
                    if isinstance(events, list):
                        normalized = []
                        for event in events[-self._max_events :]:
                            if not isinstance(event, dict):
                                continue
                            duration = event.get("duration_ms")
                            if not isinstance(duration, (int, float)):
                                continue
                            normalized.append(
                                {
                                    "ts": event.get("ts", 0),
                                    "duration_ms": float(duration),
                                    "extra": event.get("extra", {}),
                                }
                            )
                        self._events[key] = normalized
        except Exception as e:
            logger.warning("Failed to load metrics file: %s", e)

    def _save(self):
        try:
            os.makedirs(XTOOLS_DIR, exist_ok=True)
            with open(METRICS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._events, f, ensure_ascii=False, indent=2)
            self._dirty_count = 0
        except Exception as e:
            logger.warning("Failed to save metrics file: %s", e)

    def record(
        self, metric: str, duration_ms: float, extra: dict[str, Any] | None = None
    ):
        if not metric:
            return

        if not isinstance(duration_ms, (int, float)):
            return

        with self._lock:
            events = self._events.setdefault(metric, [])
            events.append(
                {
                    "ts": time.time(),
                    "duration_ms": float(duration_ms),
                    "extra": extra or {},
                }
            )
            if len(events) > self._max_events:
                del events[: len(events) - self._max_events]

            self._dirty_count += 1
            if self._dirty_count >= 8:
                self._save()

    def flush(self):
        with self._lock:
            if self._dirty_count > 0:
                self._save()

    def clear(self):
        with self._lock:
            self._events.clear()
            self._save()

    def get_events(self, metric: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            events = self._events.get(metric, [])
            return list(events[-max(1, limit) :])

    def get_summary(self, metric: str) -> dict[str, float | int]:
        with self._lock:
            events = self._events.get(metric, [])
            if not events:
                return {
                    "count": 0,
                    "avg_ms": 0.0,
                    "median_ms": 0.0,
                    "p95_ms": 0.0,
                    "max_ms": 0.0,
                    "last_ms": 0.0,
                }

            durations = sorted(float(e["duration_ms"]) for e in events)
            avg = float(sum(durations) / len(durations))
            median = float(statistics.median(durations))
            p95 = _percentile(durations, 0.95)
            maximum = float(durations[-1])
            last = float(events[-1]["duration_ms"])

            return {
                "count": len(durations),
                "avg_ms": avg,
                "median_ms": median,
                "p95_ms": p95,
                "max_ms": maximum,
                "last_ms": last,
            }

    def format_summary(self, metrics: list[str]) -> str:
        lines = []
        for metric in metrics:
            summary = self.get_summary(metric)
            lines.append(f"[{metric}]")
            lines.append(f"count : {summary['count']}")
            lines.append(f"avg   : {summary['avg_ms']:.1f} ms")
            lines.append(f"median: {summary['median_ms']:.1f} ms")
            lines.append(f"p95   : {summary['p95_ms']:.1f} ms")
            lines.append(f"max   : {summary['max_ms']:.1f} ms")
            lines.append(f"last  : {summary['last_ms']:.1f} ms")
            lines.append("")
        return "\n".join(lines).strip()


metrics_store = MetricsStore()
