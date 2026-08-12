from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.paths import config_file


@dataclass
class AppConfig:
    last_selected_drive: str = ""
    theme: str = "dark"
    duplicate_behavior: str = "skip"


def load_config(path: Path | None = None) -> AppConfig:
    source = path or config_file()
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        allowed = {key: data[key] for key in asdict(AppConfig()) if key in data}
        return AppConfig(**allowed)
    except (OSError, ValueError, TypeError):
        return AppConfig()


def save_config(config: AppConfig, path: Path | None = None) -> None:
    destination = path or config_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    temporary.replace(destination)
