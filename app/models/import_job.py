from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImportJob:
    source: str
    destination: str
    game_id: str
    title: str
    media_type: str
    size_bytes: int


@dataclass(frozen=True)
class ImportProgress:
    filename: str
    copied_bytes: int
    total_bytes: int

    @property
    def percent(self) -> int:
        return int(self.copied_bytes * 100 / self.total_bytes) if self.total_bytes else 100
