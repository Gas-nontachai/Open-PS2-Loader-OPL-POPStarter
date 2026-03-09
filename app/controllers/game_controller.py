from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Callable

from app.core.constants import ART_ALLOWED_EXT, ART_TYPES
from app.services import game_service, target_service

StepCB = Callable[[str, str], None]


def _emit(on_step: StepCB | None, status: str, message: str) -> None:
    if on_step:
        on_step(status, message)


def _should_skip_scan_iso(file_path: Path) -> bool:
    return file_path.name.startswith(".") or file_path.name.startswith("._")


def scan_games(target_path: str, on_step: StepCB | None = None) -> dict:
    try:
        target = target_service.resolve_target(target_path)
        ok, reason = target_service.validate_target_access(target)
        if not ok:
            return {"status": "error", "message": "target validation failed", "details": {"reason": reason}}

        art_dir = target / "ART"
        games: list[dict] = []
        art_map: dict[str, list[str]] = {}
        art_id_pattern = re.compile(r"^([A-Z]{4}_[0-9]{3}\.[0-9]{2})_")
        if art_dir.exists():
            for art_file in sorted(art_dir.iterdir()):
                if not art_file.is_file() or art_file.suffix.lower() not in ART_ALLOWED_EXT:
                    continue
                match = art_id_pattern.match(art_file.stem.upper())
                if match:
                    art_map.setdefault(match.group(1), []).append(art_file.name)

        for folder in ("DVD", "CD"):
            folder_path = target / folder
            if not folder_path.exists() or not folder_path.is_dir():
                continue
            for iso_file in sorted(folder_path.iterdir()):
                if not iso_file.is_file() or iso_file.suffix.lower() != ".iso" or _should_skip_scan_iso(iso_file):
                    continue
                game_id = game_service.extract_game_id_from_filename(iso_file.name)
                try:
                    game_name = game_service.derive_game_name(None, iso_file.name)
                except ValueError:
                    game_name = iso_file.stem
                art_files = sorted(art_map.get(game_id or "", []))
                games.append(
                    {
                        "game_id": game_id,
                        "game_name": game_name,
                        "destination_filename": iso_file.name,
                        "target_folder": folder,
                        "path": str(iso_file),
                        "size_bytes": iso_file.stat().st_size,
                        "size_human": target_service.human_bytes(iso_file.stat().st_size),
                        "art_count": len(art_files),
                        "art_files": art_files,
                    }
                )

        total_games_bytes = sum(int(game.get("size_bytes", 0)) for game in games)
        usage = shutil.disk_usage(target)
        used_percent = round((usage.used / usage.total) * 100, 2) if usage.total > 0 else 0.0
        storage = {
            "games_bytes": total_games_bytes,
            "games_human": target_service.human_bytes(total_games_bytes),
            "total_bytes": usage.total,
            "total_human": target_service.human_bytes(usage.total),
            "used_bytes": usage.used,
            "used_human": target_service.human_bytes(usage.used),
            "free_bytes": usage.free,
            "free_human": target_service.human_bytes(usage.free),
            "used_percent": used_percent,
        }
        _emit(on_step, "success", f"scan completed ({len(games)} games)")
        return {
            "status": "success",
            "message": "scan completed",
            "details": {"games": games, "count": len(games), "storage": storage},
        }
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during game scan", "details": {"error": str(exc)}}


def delete_game(target_path: str, game_id: str, destination_filename: str | None, on_step: StepCB | None = None) -> dict:
    try:
        target = target_service.resolve_target(target_path)
        normalized_game_id = game_service.normalize_game_id(game_id)
        requested_filename = (destination_filename or "").strip()
        ok, reason = target_service.validate_target_access(target)
        if not ok:
            return {"status": "error", "message": "target validation failed", "details": {"reason": reason}}

        deleted_game_files: list[str] = []
        candidates: list[Path] = []
        for folder in ("DVD", "CD"):
            folder_path = target / folder
            if not folder_path.exists() or not folder_path.is_dir():
                continue
            if requested_filename:
                candidate = folder_path / Path(requested_filename).name
                if candidate.exists() and candidate.is_file():
                    candidates.append(candidate)
            else:
                candidates.extend(folder_path.glob(f"{normalized_game_id}*.iso"))

        seen: set[str] = set()
        unique_candidates: list[Path] = []
        for candidate in candidates:
            resolved = str(candidate.resolve())
            if resolved not in seen:
                seen.add(resolved)
                unique_candidates.append(candidate)

        for game_file in unique_candidates:
            if game_file.exists() and game_file.is_file():
                game_file.unlink()
                deleted_game_files.append(str(game_file))

        if not deleted_game_files:
            return {
                "status": "error",
                "message": "game file not found",
                "details": {"game_id": normalized_game_id, "destination_filename": requested_filename},
            }

        art_dir = target / "ART"
        deleted_art_files: list[str] = []
        if art_dir.exists() and art_dir.is_dir():
            for art_type in ART_TYPES:
                for ext in ART_ALLOWED_EXT:
                    art_file = art_dir / f"{normalized_game_id}_{art_type}{ext}"
                    if art_file.exists() and art_file.is_file():
                        art_file.unlink()
                        deleted_art_files.append(str(art_file))

        removed_manifest_entries = game_service.remove_manifest_entries(target, normalized_game_id, requested_filename or None)
        _emit(on_step, "success", f"deleted game {normalized_game_id}")
        return {
            "status": "success",
            "message": "game deleted",
            "details": {
                "game_id": normalized_game_id,
                "deleted_game_files": deleted_game_files,
                "deleted_art_files": deleted_art_files,
                "removed_manifest_entries": removed_manifest_entries,
            },
        }
    except ValueError as exc:
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": str(exc), "details": {}}
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during game deletion", "details": {"error": str(exc)}}
