from __future__ import annotations

from dataclasses import dataclass
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
class ArtworkUploadRequest:
    target_path: str
    image_path: str
    art_type: str = "COV"
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
