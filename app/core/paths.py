from __future__ import annotations

import os
import sys
from pathlib import Path

from app.core.constants import APP_SLUG


def app_resource_path(relative_path: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])
    return Path(bundle_root) / relative_path


def app_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / APP_SLUG


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def config_file() -> Path:
    return app_data_dir() / "settings.json"


def artwork_cache_dir() -> Path:
    return app_data_dir() / "artwork-cache"
