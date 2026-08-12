from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Drive:
    path: str
    letter: str
    label: str
    filesystem: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    kind: str
    is_safe_target: bool
    model: str = ""
    connection_type: str = ""
    storage_type: str = "External storage"
    disk_number: int | None = None
    device_id: str = ""
    rejection_reason: str = ""
