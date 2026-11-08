from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Iterable

from app.core.constants import ART_ALLOWED_EXT, ART_TYPES
from app.services import art_service, drive_service, game_service, target_service
from app.services.artwork_providers import ArtworkNetworkError, OplArtworkProvider, Ps2CoversProvider

StepCB = Callable[[str, str], None]
logger = logging.getLogger("ps2_toolkit.artwork")


def _emit(callback: StepCB | None, status: str, message: str) -> None:
    if callback:
        callback(status, message)


def get_artwork_status(target_path: str, game_id: str, expected_device_id: str | None = None) -> dict:
    try:
        drive_service.validate_external_storage(target_path, expected_device_id)
        target = target_service.resolve_target(target_path)
        normalized_id = game_service.normalize_game_id(game_id)
        metadata = art_service.load_metadata(target)
        types: dict[str, dict] = {}
        for art_type, spec in art_service.ARTWORK_SPECS.items():
            files = art_service.artwork_files(target, normalized_id, art_type)
            records = []
            for path in files:
                source = metadata.get(path.name, {}).get("provenance", "existing")
                records.append({"path": str(path), "preview_path": art_service.preview_thumbnail(path), "name": path.name, "provenance": source})
            custom = any(record["provenance"] == "custom" for record in records)
            types[art_type] = {
                "label": spec["label"],
                "multiple": spec["multiple"],
                "status": "Custom" if custom else ("Available" if records else "Missing"),
                "files": records,
            }
        return {"status": "success", "message": "Artwork refreshed.", "details": {"game_id": normalized_id, "types": types}}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Artwork status scan failed")
        return {"status": "error", "message": "Artwork could not be refreshed.", "details": {"error": str(exc)}}


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
            if source.stat().st_size > 20 * 1024 * 1024:
                return {"status": "error", "message": "Choose an image no larger than 20 MiB.", "details": {}}
            drive_service.validate_external_storage(target, expected_device_id)
            saved.append(
                art_service.write_artwork(
                    target,
                    game_id,
                    normalized_type,
                    source.read_bytes(),
                    source.suffix,
                    provenance="custom",
                    replace=normalized_type != "SCR",
                )
            )
            _emit(on_step, "success", f"{art_service.ARTWORK_SPECS[normalized_type]['label']} saved for {game_id}.")
        if not saved:
            return {"status": "error", "message": "Choose an image before saving.", "details": {}}
        return {"status": "success", "message": "Custom artwork saved.", "details": {"game_id": game_id, "saved": saved}}
    except PermissionError:
        return {"status": "error", "message": "Windows blocked access to the selected storage.", "details": {}}
    except OSError as exc:
        logger.exception("Artwork write failed")
        return {"status": "error", "message": "Artwork could not be saved. Check the storage connection and free space.", "details": {"error": str(exc)}}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Artwork write failed")
        return {"status": "error", "message": str(exc), "details": {}}


def _select_candidates(game_id: str, providers: Iterable | None = None) -> list:
    source_list = list(providers or [OplArtworkProvider(), Ps2CoversProvider()])
    selected: list = []
    has_cover = False
    for provider in source_list:
        if has_cover and isinstance(provider, Ps2CoversProvider):
            continue
        candidates = provider.find(game_id)
        for candidate in candidates:
            if candidate.art_type == "COV":
                if has_cover:
                    continue
                has_cover = True
            selected.append(candidate)
    # Single-value types use the first image. Screenshots remain multiple.
    result: list = []
    seen: set[str] = set()
    for candidate in selected:
        if candidate.art_type != "SCR" and candidate.art_type in seen:
            continue
        seen.add(candidate.art_type)
        result.append(candidate)
    return result


def download_artwork(
    target_path: str,
    game_id: str,
    replace: bool = False,
    on_step: StepCB | None = None,
    cancel_event: threading.Event | None = None,
    expected_device_id: str | None = None,
    providers: Iterable | None = None,
    invalidate_cache: bool = False,
) -> dict:
    try:
        drive_service.validate_external_storage(target_path, expected_device_id)
        target = target_service.resolve_target(target_path)
        normalized_id = game_service.normalize_game_id(game_id)
        target_service.ensure_required_folders(target)
        existing_status = get_artwork_status(str(target), normalized_id, expected_device_id)["details"]["types"]
        _emit(on_step, "working", f"Finding artwork for {normalized_id}…")
        candidates = _select_candidates(normalized_id, providers)
        if not candidates:
            return {"status": "error", "message": "No artwork was found for this Game ID. You can upload an image manually.", "details": {"game_id": normalized_id}}
        saved: list[dict] = []
        skipped: list[str] = []
        failures: list[dict] = []
        replaced_types: set[str] = set()
        for candidate in candidates:
            if cancel_event and cancel_event.is_set():
                return {"status": "cancelled", "message": "Artwork download cancelled.", "details": {"saved": saved, "skipped": skipped}}
            current = existing_status[candidate.art_type]
            if not replace:
                if candidate.art_type == "SCR":
                    expected_stem = f"{normalized_id}_{candidate.suffix}".upper()
                    if any(Path(item["path"]).stem.upper() == expected_stem for item in current["files"]):
                        skipped.append(candidate.suffix)
                        continue
                elif current["files"]:
                    skipped.append(candidate.art_type)
                    continue
            try:
                drive_service.validate_external_storage(target, expected_device_id)
                content, extension, cache_hit = art_service.cached_candidate(candidate, invalidate=invalidate_cache)
                saved.append(
                    art_service.write_artwork(
                        target,
                        normalized_id,
                        candidate.art_type,
                        content,
                        extension,
                        provenance=candidate.provider,
                        suffix=candidate.suffix,
                        replace=replace and candidate.art_type not in replaced_types,
                    )
                )
                replaced_types.add(candidate.art_type)
                logger.info("Artwork download game_id=%s type=%s provider=%s cache_hit=%s", normalized_id, candidate.art_type, candidate.provider, cache_hit)
                _emit(on_step, "working", f"Downloaded {art_service.ARTWORK_SPECS[candidate.art_type]['label']}.")
            except Exception as exc:  # one bad image must not block the rest
                logger.exception("Artwork candidate failed game_id=%s type=%s provider=%s", normalized_id, candidate.art_type, candidate.provider)
                failures.append({"art_type": candidate.art_type, "provider": candidate.provider, "error": str(exc)})
        if saved:
            return {
                "status": "success",
                "message": f"Downloaded {len(saved)} artwork image(s).",
                "details": {"game_id": normalized_id, "saved": saved, "skipped": skipped, "failures": failures},
            }
        if skipped and not failures:
            return {"status": "success", "message": "This game already has all available artwork.", "details": {"game_id": normalized_id, "saved": [], "skipped": skipped}}
        return {"status": "error", "message": "Artwork could not be downloaded. You can retry or upload an image manually.", "details": {"failures": failures}}
    except ArtworkNetworkError as exc:
        logger.exception("Artwork provider unavailable game_id=%s", game_id)
        return {"status": "error", "message": f"{exc} You can retry or upload an image manually.", "details": {}}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Artwork download failed game_id=%s", game_id)
        return {"status": "error", "message": "Artwork could not be downloaded. Check your internet connection and try again.", "details": {"error": str(exc)}}


def download_artwork_batch(
    target_path: str,
    games: list[dict],
    on_step: StepCB | None = None,
    cancel_event: threading.Event | None = None,
    expected_device_id: str | None = None,
    providers: Iterable | None = None,
) -> dict:
    results: list[dict] = []
    total = len(games)
    for index, game in enumerate(games, start=1):
        if cancel_event and cancel_event.is_set():
            return {"status": "cancelled", "message": f"Artwork download cancelled ({index - 1}/{total} games checked).", "details": {"results": results}}
        game_id = str(game.get("game_id") or "")
        _emit(on_step, "working", f"Scanning artwork {index}/{total}: {game_id}")
        result = download_artwork(target_path, game_id, False, on_step, cancel_event, expected_device_id, providers)
        results.append({"game_id": game_id, "result": result})
        if result.get("status") == "cancelled":
            return {"status": "cancelled", "message": "Artwork download cancelled.", "details": {"results": results}}
    downloaded = sum(len(item["result"].get("details", {}).get("saved", [])) for item in results)
    return {"status": "success", "message": f"Artwork scan complete: {downloaded} image(s) downloaded for {total} game(s).", "details": {"results": results, "downloaded": downloaded}}


def remove_artwork(
    target_path: str,
    game_id: str,
    art_type: str = "COV",
    on_step: StepCB | None = None,
    expected_device_id: str | None = None,
    filename: str | None = None,
) -> dict:
    try:
        drive_service.validate_external_storage(target_path, expected_device_id)
        target = target_service.resolve_target(target_path)
        normalized_id = game_service.normalize_game_id(game_id)
        normalized_type = art_type.strip().upper()
        if normalized_type not in ART_TYPES:
            raise ValueError("Unsupported artwork type.")
        candidates = art_service.artwork_files(target, normalized_id, normalized_type)
        if filename:
            safe_name = Path(filename).name
            candidates = [path for path in candidates if path.name == safe_name]
        deleted: list[str] = []
        metadata = art_service.load_metadata(target)
        for candidate in candidates:
            candidate.unlink()
            deleted.append(str(candidate))
            metadata.pop(candidate.name, None)
        if not deleted:
            return {"status": "error", "message": "No artwork was found for this game.", "details": {}}
        art_service.save_metadata(target, metadata)
        _emit(on_step, "success", "Artwork removed.")
        return {"status": "success", "message": "Artwork removed.", "details": {"deleted": deleted}}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Artwork removal failed")
        return {"status": "error", "message": str(exc), "details": {}}
