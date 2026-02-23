from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ValidateTargetRequest(BaseModel):
    target_path: str = Field(min_length=1)
    ensure_folders: bool = True


class FormatTargetRequest(BaseModel):
    target_path: str = Field(min_length=1)
    confirm_phrase: str = Field(min_length=1)
    volume_label: str = "PS2USB"


class ArtSearchRequest(BaseModel):
    target_path: Optional[str] = None
    game_name: Optional[str] = None
    source_filename: Optional[str] = None
    max_results: int = Field(default=10, ge=1, le=10)


class ArtSelection(BaseModel):
    art_type: str = Field(min_length=1)
    image_url: str = Field(min_length=1)


class ArtSaveRequest(BaseModel):
    target_path: str = Field(min_length=1)
    game_name: Optional[str] = None
    source_filename: Optional[str] = None
    selections: list[ArtSelection]


class ScanGamesRequest(BaseModel):
    target_path: str = Field(min_length=1)


class DeleteGameRequest(BaseModel):
    target_path: str = Field(min_length=1)
    game_id: str = Field(min_length=1)
    destination_filename: Optional[str] = None
