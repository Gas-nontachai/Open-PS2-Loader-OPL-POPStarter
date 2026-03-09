from __future__ import annotations

import shutil
from pathlib import Path
from threading import Event
from typing import Callable

from app.core.constants import CD_THRESHOLD_BYTES
from app.services import format_service, game_service, target_service

StepCB = Callable[[str, str], None]


def _emit(on_step: StepCB | None, status: str, message: str) -> None:
    if on_step:
        on_step(status, message)


def validate_target(target_path: str, ensure_folders: bool, on_step: StepCB | None = None) -> dict:
    try:
        target = target_service.resolve_target(target_path)
        _emit(on_step, "info", f"checking target: {target}")
        ok, reason = target_service.validate_target_access(target)
        if not ok:
            _emit(on_step, "error", reason)
            return {"status": "error", "message": "target validation failed", "details": {"reason": reason}}

        missing: list[str] = []
        created: list[str] = []
        if ensure_folders:
            missing, created = target_service.ensure_required_folders(target)
            _emit(on_step, "success", f"required folders ready (created: {len(created)})")

        return {
            "status": "success",
            "message": "target path is valid and ready",
            "details": {"target": str(target), "missing_before": missing, "created": created},
        }
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during validation", "details": {"error": str(exc)}}


def format_target(
    target_path: str,
    confirm_phrase: str,
    volume_label: str,
    on_step: StepCB | None = None,
) -> dict:
    try:
        if confirm_phrase.strip().upper() != "FORMAT":
            _emit(on_step, "error", "confirmation phrase mismatch")
            return {"status": "error", "message": "confirmation phrase mismatch", "details": {"expected": "FORMAT"}}

        target = target_service.resolve_target(target_path)
        if not target.exists():
            return {"status": "error", "message": "target path does not exist", "details": {"target": str(target)}}

        mounted_path = format_service.format_target(target, volume_label, lambda s, m: _emit(on_step, s, m))
        _, created = target_service.ensure_required_folders(mounted_path)
        _emit(on_step, "success", "required folders created after format")
        return {
            "status": "success",
            "message": "usb formatted and prepared successfully",
            "details": {"target": str(mounted_path), "created": created},
        }
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during format", "details": {"error": str(exc)}}


def _copy_with_progress(src: Path, dst: Path, on_step: StepCB | None = None, cancel_event: Event | None = None) -> None:
    total = src.stat().st_size
    copied = 0
    chunk = 4 * 1024 * 1024
    with src.open("rb") as rfh, dst.open("wb") as wfh:
        while True:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("cancelled")
            data = rfh.read(chunk)
            if not data:
                break
            wfh.write(data)
            copied += len(data)
            pct = int((copied / total) * 100) if total > 0 else 100
            _emit(on_step, "info", f"copying {src.name}: {pct}%")
    shutil.copystat(src, dst, follow_symlinks=True)


def import_isos(
    target_path: str,
    iso_paths: list[str],
    overwrite: bool,
    on_step: StepCB | None = None,
    cancel_event: Event | None = None,
) -> dict:
    try:
        if not iso_paths:
            return {"status": "error", "message": "no files selected", "details": {}}

        target = target_service.resolve_target(target_path)
        ok, reason = target_service.validate_target_access(target)
        if not ok:
            return {"status": "error", "message": "target validation failed", "details": {"reason": reason}}
        target_service.ensure_required_folders(target)

        prepared: list[dict] = []
        for iso in iso_paths:
            src = Path(iso).expanduser().resolve()
            if not src.exists() or not src.is_file():
                return {"status": "error", "message": "source file not found", "details": {"file": str(src)}}
            if src.suffix.lower() != ".iso":
                return {"status": "error", "message": "only .iso is allowed", "details": {"file": src.name}}

            size = src.stat().st_size
            folder = "CD" if size < CD_THRESHOLD_BYTES else "DVD"
            game_name = game_service.derive_game_name(None, src.name)
            game_id = game_service.extract_game_id_from_iso(src)
            id_source = "iso"
            if not game_id:
                game_id, _ = game_service.resolve_game_id(None, game_name)
                id_source = "generated"
            dest_name = game_service.build_opl_iso_filename(game_id=game_id, source_filename=src.name, game_name=game_name)
            prepared.append(
                {
                    "src": src,
                    "size": size,
                    "folder": folder,
                    "game_name": game_name,
                    "game_id": game_id,
                    "id_source": id_source,
                    "dest_name": dest_name,
                }
            )

        total_iso_bytes = sum(p["size"] for p in prepared)
        usage = shutil.disk_usage(target)
        required = total_iso_bytes + target_service.compute_buffer(total_iso_bytes)
        if usage.free < required:
            return {
                "status": "error",
                "message": "insufficient disk space",
                "details": {
                    "required": target_service.human_bytes(required),
                    "free": target_service.human_bytes(usage.free),
                },
            }

        imported: list[dict] = []
        prepared.sort(key=lambda x: int(x["size"]), reverse=True)
        for idx, item in enumerate(prepared, start=1):
            if cancel_event and cancel_event.is_set():
                return {
                    "status": "cancelled",
                    "message": "import cancelled",
                    "details": {"imported_count": len(imported), "imported": imported},
                }
            src = item["src"]
            destination = target / item["folder"] / item["dest_name"]
            if destination.exists() and not overwrite:
                return {
                    "status": "error",
                    "message": "destination file already exists",
                    "details": {"file": item["dest_name"], "overwrite": False},
                }

            _emit(on_step, "info", f"[{idx}/{len(prepared)}] importing {src.name}")
            _copy_with_progress(src, destination, on_step=on_step, cancel_event=cancel_event)
            game_service.upsert_manifest_entry(
                target=target,
                source_filename=src.name,
                game_name=item["game_name"],
                game_id=item["game_id"],
                id_source=item["id_source"],
                target_folder=item["folder"],
                destination_filename=item["dest_name"],
            )
            imported.append(
                {
                    "file": item["dest_name"],
                    "source_filename": src.name,
                    "game_name": item["game_name"],
                    "game_id": item["game_id"],
                    "id_source": item["id_source"],
                    "target_folder": item["folder"],
                    "destination": str(destination),
                    "size": target_service.human_bytes(item["size"]),
                }
            )
            _emit(on_step, "success", f"imported {item['dest_name']}")

        return {
            "status": "success",
            "message": "all files imported successfully",
            "details": {
                "target": str(target),
                "imported_count": len(imported),
                "imported": imported,
                "manifest_path": str(game_service.manifest_path(target)),
            },
        }
    except Exception as exc:  # noqa: BLE001
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": "unexpected error during import", "details": {"error": str(exc)}}
