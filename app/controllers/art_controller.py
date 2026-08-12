from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from app.core.constants import ART_ALLOWED_EXT, ART_TYPES
from app.services import art_service, drive_service, game_service, target_service

StepCB = Callable[[str, str], None]
logger = logging.getLogger("ps2_toolkit.artwork")


def _emit(callback: StepCB | None, status: str, message: str) -> None:
    if callback:
        callback(status, message)


def upload_art_manual(
    target_path: str,
    game_name: str | None,
    source_filename: str | None,
    art_files: dict[str, str],
    on_step: StepCB | None = None,
    expected_device_id: str | None = None,
) -> dict:
    try:
        drive_service.validate_external_storage(target_path, expected_device_id)
        target = target_service.resolve_target(target_path)
        game_id, _, _ = game_service.resolve_game_id_for_target(target, game_name, source_filename)
        ok, reason = target_service.validate_target_access(target)
        if not ok:
            return {"status": "error", "message": "The selected storage is unavailable.", "details": {"reason": reason}}
        target_service.ensure_required_folders(target)
        saved: list[dict] = []
        for art_type, file_path in art_files.items():
            normalized_type = art_type.strip().upper()
            if normalized_type not in ART_TYPES or not file_path:
                continue
            source = Path(file_path).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in ART_ALLOWED_EXT:
                return {"status": "error", "message": "Choose a valid PNG, JPG, JPEG, or WEBP image.", "details": {}}
            drive_service.validate_external_storage(target, expected_device_id)
            optimized, extension, info = art_service.optimize_art_image(source.read_bytes(), normalized_type, source.suffix)
            destination = target / "ART" / f"{game_id}_{normalized_type}{extension}"
            temporary = destination.with_name(destination.name + ".part")
            temporary.write_bytes(optimized)
            temporary.replace(destination)
            saved.append({"art_type": normalized_type, "path": str(destination), "optimize": info})
            _emit(on_step, "success", f"Artwork saved for {game_id}.")
        if not saved:
            return {"status": "error", "message": "Choose an image before saving.", "details": {}}
        return {"status": "success", "message": "Artwork saved.", "details": {"game_id": game_id, "saved": saved}}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Artwork write failed")
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": str(exc), "details": {}}


def remove_artwork(
    target_path: str,
    game_id: str,
    art_type: str = "COV",
    on_step: StepCB | None = None,
    expected_device_id: str | None = None,
) -> dict:
    try:
        drive_service.validate_external_storage(target_path, expected_device_id)
        target = target_service.resolve_target(target_path)
        normalized_id = game_service.normalize_game_id(game_id)
        normalized_type = art_type.strip().upper()
        if normalized_type not in ART_TYPES:
            raise ValueError("Unsupported artwork type.")
        deleted: list[str] = []
        for extension in ART_ALLOWED_EXT:
            candidate = target / "ART" / f"{normalized_id}_{normalized_type}{extension}"
            if candidate.is_file():
                candidate.unlink()
                deleted.append(str(candidate))
        if not deleted:
            return {"status": "error", "message": "No artwork was found for this game.", "details": {}}
        _emit(on_step, "success", "Artwork removed.")
        return {"status": "success", "message": "Artwork removed.", "details": {"deleted": deleted}}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Artwork removal failed")
        return {"status": "error", "message": str(exc), "details": {}}
