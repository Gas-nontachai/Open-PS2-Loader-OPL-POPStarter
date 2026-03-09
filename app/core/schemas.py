from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ValidateTargetRequest:
    target_path: str
    ensure_folders: bool = True


@dataclass
class FormatTargetRequest:
    target_path: str
    confirm_phrase: str
    volume_label: str = "PS2USB"


@dataclass
class ArtSearchRequest:
    target_path: Optional[str] = None
    game_name: Optional[str] = None
    source_filename: Optional[str] = None
    max_results: int = 10


@dataclass
class ArtSelection:
    art_type: str
    image_url: str


@dataclass
class ArtSaveRequest:
    target_path: str
    selections: list[ArtSelection] = field(default_factory=list)
    game_name: Optional[str] = None
    source_filename: Optional[str] = None


@dataclass
class ScanGamesRequest:
    target_path: str


@dataclass
class DeleteGameRequest:
    target_path: str
    game_id: str
    destination_filename: Optional[str] = None
