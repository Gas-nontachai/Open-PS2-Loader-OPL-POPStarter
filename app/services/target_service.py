from __future__ import annotations

import os
from pathlib import Path

from app.core.constants import REQUIRED_FOLDERS, SPACE_BUFFER_MIN_BYTES, SPACE_BUFFER_RATIO


def resolve_target(target_path: str) -> Path:
    return Path(target_path).expanduser().resolve()


def validate_target_access(target: Path) -> tuple[bool, str]:
    if not target.exists():
        return False, "target path does not exist"
    if not target.is_dir():
        return False, "target path is not a directory"
    if not os.access(target, os.R_OK | os.W_OK | os.X_OK):
        return False, "target path is not writable"
    return True, "ok"


def ensure_required_folders(target: Path) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    created: list[str] = []
    for folder in REQUIRED_FOLDERS:
        folder_path = target / folder
        if folder_path.exists() and not folder_path.is_dir():
            raise NotADirectoryError(f"required path exists but is not a directory: {folder_path}")
        if not folder_path.exists():
            missing.append(folder)
            folder_path.mkdir(parents=True, exist_ok=True)
            created.append(folder)
    return missing, created


def compute_buffer(total_iso_bytes: int) -> int:
    return max(int(total_iso_bytes * SPACE_BUFFER_RATIO), SPACE_BUFFER_MIN_BYTES)


def human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{size} B"
