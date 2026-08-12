from __future__ import annotations

import os
from pathlib import Path

from app.core.constants import APP_SLUG


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
