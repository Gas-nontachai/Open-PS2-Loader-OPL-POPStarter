from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from app.core.constants import ART_ALLOWED_EXT, ART_TYPES
from app.services import art_service, game_service, target_service

StepCB = Callable[[str, str], None]


def _emit(on_step: StepCB | None, status: str, message: str) -> None:
    if on_step:
        on_step(status, message)


def search_art(
    target_path: str | None,
    game_name: str | None,
    source_filename: str | None,
    max_results: int,
    on_step: StepCB | None = None,
) -> dict:
    try:
        game_query = game_service.derive_game_name(game_name, source_filename)
        target = target_service.resolve_target(target_path) if target_path else None
        game_id, generated, id_source = game_service.resolve_game_id_for_target(target, game_query, source_filename)
        query = f"{game_query} PS2 cover art"

        now_ts = time.time()
        provider = "rawg"
        cache_key = art_service.art_search_cache_key(provider, game_id, query, max_results)
        cached = art_service.get_cached_art_search(cache_key, now_ts)
        if cached is not None:
            return {
                "status": "success",
                "message": "art candidates ready",
                "details": {
                    "game_id": game_id,
                    "generated_game_id": generated,
                    "id_source": id_source,
                    "game_query": game_query,
                    "art_types": ART_TYPES,
                    "candidates": cached,
                    "cache_hit": True,
                    "provider_used": provider,
                },
            }

        allowed, reason, retry_after = art_service.enforce_art_search_rate_limit("desktop", now_ts)
        if not allowed:
            return {
                "status": "error",
                "message": reason,
                "details": {"retry_after_seconds": retry_after},
            }

        _emit(on_step, "info", f"searching art: {query}")
        provider_used, candidates = art_service.search_art_candidates(query, max_results)
        if not candidates:
            return {"status": "error", "message": "no art candidates found", "details": {"query": query}}

        art_service.store_cached_art_search(cache_key, candidates, now_ts)
        return {
            "status": "success",
            "message": "art candidates ready",
            "details": {
                "game_id": game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "game_query": game_query,
                "art_types": ART_TYPES,
                "candidates": candidates,
                "cache_hit": False,
                "provider_used": provider_used,
            },
        }
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during art search", "details": {"error": str(exc)}}


def save_art_auto(
    target_path: str,
    game_name: str | None,
    source_filename: str | None,
    selections: list[dict],
    on_step: StepCB | None = None,
) -> dict:
    try:
        target = target_service.resolve_target(target_path)
        game_id, generated, id_source = game_service.resolve_game_id_for_target(target, game_name, source_filename)
        if not selections:
            return {"status": "error", "message": "no selected images", "details": {}}

        ok, reason = target_service.validate_target_access(target)
        if not ok:
            return {"status": "error", "message": "target validation failed", "details": {"reason": reason}}

        target_service.ensure_required_folders(target)
        art_dir = target / "ART"

        seen_types: set[str] = set()
        unique_selections: list[dict] = []
        skipped_duplicates: list[dict] = []
        for idx, selection in enumerate(selections, start=1):
            art_type = str(selection.get("art_type", "")).strip().upper()
            image_url = str(selection.get("image_url", "")).strip()
            if art_type not in ART_TYPES:
                return {"status": "error", "message": f"invalid art type: {art_type}", "details": {}}
            if not image_url:
                return {"status": "error", "message": "missing image_url", "details": {"index": idx}}
            if art_type in seen_types:
                skipped_duplicates.append({"art_type": art_type, "position": idx})
                continue
            seen_types.add(art_type)
            unique_selections.append({"art_type": art_type, "image_url": image_url})

        if not unique_selections:
            return {"status": "error", "message": "no unique art type selected", "details": {}}

        saved: list[dict] = []
        for selection in unique_selections:
            art_type = selection["art_type"]
            content, ext = art_service.download_image(selection["image_url"], art_type)
            optimized_content, optimized_ext, optimize_info = art_service.optimize_art_image(content, art_type, ext)
            destination = art_dir / f"{game_id}_{art_type}{optimized_ext}"
            destination.write_bytes(optimized_content)
            saved.append({"art_type": art_type, "path": str(destination), "optimize": optimize_info})
            _emit(on_step, "success", f"saved {art_type}")

        return {
            "status": "success",
            "message": "selected auto art saved",
            "details": {
                "game_id": game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "saved": saved,
                "skipped_duplicates": skipped_duplicates,
            },
        }
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during auto art save", "details": {"error": str(exc)}}


def upload_art_manual(
    target_path: str,
    game_name: str | None,
    source_filename: str | None,
    art_files: dict[str, str],
    on_step: StepCB | None = None,
) -> dict:
    try:
        target = target_service.resolve_target(target_path)
        game_id, generated, id_source = game_service.resolve_game_id_for_target(target, game_name, source_filename)

        ok, reason = target_service.validate_target_access(target)
        if not ok:
            return {"status": "error", "message": "target validation failed", "details": {"reason": reason}}

        target_service.ensure_required_folders(target)
        art_dir = target / "ART"

        saved: list[dict] = []
        for art_type, file_path in art_files.items():
            normalized_type = art_type.strip().upper()
            if normalized_type not in ART_TYPES:
                continue
            if not file_path:
                continue
            src = Path(file_path).expanduser().resolve()
            if not src.exists() or not src.is_file():
                return {"status": "error", "message": "art file not found", "details": {"file": str(src)}}
            src_ext = src.suffix.lower()
            if src_ext not in ART_ALLOWED_EXT:
                return {"status": "error", "message": f"unsupported extension for {normalized_type}", "details": {}}

            raw = src.read_bytes()
            optimized_content, dst_ext, optimize_info = art_service.optimize_art_image(raw, normalized_type, src_ext)
            dst = art_dir / f"{game_id}_{normalized_type}{dst_ext}"
            dst.write_bytes(optimized_content)
            saved.append({"art_type": normalized_type, "path": str(dst), "optimize": optimize_info})
            _emit(on_step, "success", f"uploaded {normalized_type}")

        if not saved:
            return {"status": "error", "message": "no art files provided", "details": {}}

        return {
            "status": "success",
            "message": "manual art upload completed",
            "details": {
                "game_id": game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "saved": saved,
            },
        }
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during manual art upload", "details": {"error": str(exc)}}
