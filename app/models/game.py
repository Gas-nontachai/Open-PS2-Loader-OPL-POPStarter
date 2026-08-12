from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Game:
    game_id: str | None
    title: str
    filename: str
    path: str
    media_type: str
    size_bytes: int
    cover_path: str | None = None
    config_path: str | None = None
    artwork: tuple[str, ...] = field(default_factory=tuple)

