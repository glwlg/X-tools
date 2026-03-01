import logging
import os
import platform
import sys
import zipfile
from datetime import datetime
from logging.handlers import RotatingFileHandler


APPDATA_DIR = os.getenv("APPDATA") or os.path.expanduser("~")
XTOOLS_DIR = os.path.join(APPDATA_DIR, "x-tools")
LOG_DIR = os.path.join(XTOOLS_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "x-tools.log")

_IS_LOGGING_READY = False


def setup_logging():
    global _IS_LOGGING_READY

    if _IS_LOGGING_READY:
        return LOG_FILE

    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    _IS_LOGGING_READY = True
    root.info("Logging initialized: %s", LOG_FILE)
    return LOG_FILE


def get_logger(name):
    return logging.getLogger(name)


def get_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)
    return LOG_DIR


def export_diagnostics(target_dir=None):
    os.makedirs(LOG_DIR, exist_ok=True)

    if target_dir is None:
        target_dir = os.path.join(os.path.expanduser("~"), "Desktop")

    os.makedirs(target_dir, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_path = os.path.join(target_dir, f"x-tools-diagnostics-{stamp}.zip")

    config_file = os.path.join(XTOOLS_DIR, "config.json")
    theme_file = os.path.join(XTOOLS_DIR, "themes.json")

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(LOG_FILE):
            zf.write(LOG_FILE, arcname="logs/x-tools.log")

        for i in range(1, 6):
            rotated = f"{LOG_FILE}.{i}"
            if os.path.exists(rotated):
                zf.write(rotated, arcname=f"logs/x-tools.log.{i}")

        if os.path.exists(config_file):
            zf.write(config_file, arcname="config/config.json")
        if os.path.exists(theme_file):
            zf.write(theme_file, arcname="config/themes.json")

        env_text = "\n".join(
            [
                f"time={datetime.now().isoformat()}",
                f"python={sys.version}",
                f"platform={platform.platform()}",
                f"executable={sys.executable}",
                f"cwd={os.getcwd()}",
            ]
        )
        zf.writestr("meta/environment.txt", env_text)

    return archive_path
