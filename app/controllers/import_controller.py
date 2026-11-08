from __future__ import annotations

import shutil
import logging
import os
from pathlib import Path
from threading import Event
from typing import Callable

from app.core.exceptions import OperationCancelledError
from app.services import drive_service, format_service, game_service, target_service, usbextreme_service

StepCB = Callable[[str, str], None]
logger = logging.getLogger("ps2_toolkit.import")


def _import_error(message: str, message_th: str, exc: Exception | None = None, **details: object) -> dict:
    if exc is not None:
        details["technical_error"] = str(exc)
    return {"status": "error", "message": message, "message_th": message_th, "details": details}


def _emit(on_step: StepCB | None, status: str, message: str) -> None:
    if on_step:
        on_step(status, message)


def validate_target(
    target_path: str,
    ensure_folders: bool,
    on_step: StepCB | None = None,
    expected_device_id: str | None = None,
) -> dict:
    try:
        drive_service.validate_external_storage(target_path, expected_device_id)
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
    expected_device_id: str | None = None,
) -> dict:
    try:
        if confirm_phrase != "FORMAT":
            _emit(on_step, "error", "confirmation phrase mismatch")
            return {"status": "error", "message": "confirmation phrase mismatch", "details": {"expected": "FORMAT"}}

        drive_service.validate_external_storage(target_path, expected_device_id)
        target = target_service.resolve_target(target_path)
        if not target.exists():
            return {"status": "error", "message": "target path does not exist", "details": {"target": str(target)}}

        mounted_path = format_service.format_target(target, volume_label, lambda s, m: _emit(on_step, s, m), expected_device_id)
        _, created = target_service.ensure_required_folders(mounted_path)
        _emit(on_step, "success", "required folders created after format")
        return {
            "status": "success",
            "message": "usb formatted and prepared successfully",
            "details": {"target": str(mounted_path), "created": created},
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Format failed for external storage")
        _emit(on_step, "error", str(exc))
        return {"status": "error", "message": str(exc), "details": {"error": str(exc)}}


def _copy_with_progress(src: Path, dst: Path, on_step: StepCB | None = None, cancel_event: Event | None = None, on_progress: Callable[[int], None] | None = None) -> None:
    total = src.stat().st_size
    copied = 0
    chunk = 4 * 1024 * 1024
    with src.open("rb") as rfh, dst.open("xb") as wfh:
        while True:
            if cancel_event and cancel_event.is_set():
                raise OperationCancelledError("Import cancelled.")
            data = rfh.read(chunk)
            if not data:
                break
            wfh.write(data)
            copied += len(data)
            pct = int((copied / total) * 100) if total > 0 else 100
            if on_progress:
                on_progress(pct)
            _emit(
                on_step,
                "info",
                f"copying {src.name}: {target_service.human_bytes(copied)} / "
                f"{target_service.human_bytes(total)} ({pct}%)",
            )
        wfh.flush()
        os.fsync(wfh.fileno())
    shutil.copystat(src, dst, follow_symlinks=True)


def import_isos(
    target_path: str,
    iso_paths: list[str],
    overwrite: bool,
    on_step: StepCB | None = None,
    cancel_event: Event | None = None,
    expected_device_id: str | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    imported: list[dict] = []
    try:
        if not iso_paths:
            return {"status": "error", "message": "no files selected", "details": {}}

        device = drive_service.validate_external_storage(target_path, expected_device_id)
        target = target_service.resolve_target(target_path)
        ok, reason = target_service.validate_target_access(target)
        if not ok:
            return {"status": "error", "message": "target validation failed", "details": {"reason": reason}}
        target_service.ensure_required_folders(target)

        prepared: list[dict] = []
        for source_index, iso in enumerate(iso_paths, start=1):
            src = Path(iso).expanduser().resolve()

            def validation(state: str) -> None:
                if on_progress:
                    on_progress({"index": source_index, "total": len(iso_paths), "path": str(src), "percent": 0, "state": state})

            validation("Checking")
            if not src.exists() or not src.is_file():
                validation("Failed: source file not found")
                return {"status": "error", "message": "source file not found", "details": {"file": str(src)}}
            if src.suffix.lower() != ".iso":
                validation("Failed: only ISO files are supported")
                return {"status": "error", "message": "only .iso is allowed", "details": {"file": src.name}}

            size = src.stat().st_size
            folder = game_service.classify_iso_media(size)
            game_name = game_service.derive_game_name(None, src.name)
            game_id = game_service.extract_game_id_from_iso(src)
            id_source = "iso"
            if not game_id:
                game_id = game_service.extract_game_id_from_filename(src.name)
                id_source = "filename"
            if not game_id:
                validation("Failed: no PS2 Game ID found")
                return {
                    "status": "error",
                    "message": "Unable to read PS2 game ID from this ISO.",
                    "details": {"file": src.name},
                }
            validation("Validated")
            filesystem = device.filesystem.upper()
            file_limit = (
                usbextreme_service.FAT16_MAX_FILE_BYTES
                if filesystem in {"FAT", "FAT16"}
                else usbextreme_service.FAT32_MAX_FILE_BYTES
            )
            split_for_fat = filesystem in {"FAT", "FAT16", "FAT32"} and size > file_limit
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
                    "split_for_fat": split_for_fat,
                }
            )

        total_iso_bytes = sum(p["size"] for p in prepared)
        usage = shutil.disk_usage(target)
        required = total_iso_bytes + target_service.compute_buffer(total_iso_bytes)
        if usage.free < required:
            required_human = target_service.human_bytes(required)
            free_human = target_service.human_bytes(usage.free)
            return _import_error(
                f"Not enough space on the USB. Required: {required_human}; available: {free_human}.",
                f"พื้นที่บน USB ไม่พอ ต้องใช้ {required_human} แต่เหลือ {free_human}",
                required=required_human,
                free=free_human,
            )

        skipped_count = 0
        prepared.sort(key=lambda x: int(x["size"]), reverse=True)
        for idx, item in enumerate(prepared, start=1):
            drive_service.validate_external_storage(target, expected_device_id)
            if cancel_event and cancel_event.is_set():
                return {
                    "status": "cancelled",
                    "message": "import cancelled",
                    "details": {"imported_count": len(imported), "imported": imported},
                }
            src = item["src"]

            def report(percent: int, state: str = "Copying") -> None:
                if on_progress:
                    on_progress({"index": idx, "total": len(prepared), "path": str(src), "percent": percent, "state": state})

            report(0)
            if item["split_for_fat"]:
                entries = usbextreme_service.read_entries(target)
                duplicate = next(
                    (entry for entry in entries if entry.game_id.upper() == item["game_id"].upper()),
                    None,
                )
                if duplicate and not overwrite:
                    skipped_count += 1
                    report(100, "Skipped")
                    _emit(on_step, "info", f"skipped duplicate: {item['game_name']}")
                    continue
                if duplicate:
                    usbextreme_service.remove_entry(target, item["game_id"])

                _emit(on_step, "info", f"[{idx}/{len(prepared)}] preparing large game for FAT32: {src.name}")

                def split_progress(copied: int, total: int) -> None:
                    pct = int((copied / total) * 100) if total else 100
                    report(pct)
                    _emit(
                        on_step,
                        "info",
                        f"copying {src.name}: {target_service.human_bytes(copied)} / "
                        f"{target_service.human_bytes(total)} ({pct}%)",
                    )

                entry, part_files = usbextreme_service.install_iso(
                    source=src,
                    target=target,
                    title=item["game_name"],
                    game_id=item["game_id"],
                    media=item["folder"],
                    progress=split_progress,
                    cancel_event=cancel_event,
                )
                try:
                    current_entries = [
                        existing
                        for existing in usbextreme_service.read_entries(target)
                        if existing.game_id.upper() != item["game_id"].upper()
                    ]
                    usbextreme_service.write_entries(target, current_entries + [entry])
                except Exception:
                    for part_file in part_files:
                        part_file.unlink(missing_ok=True)
                    raise

                destination_name = part_files[0].name
                game_service.upsert_manifest_entry(
                    target=target,
                    source_filename=src.name,
                    game_name=entry.name,
                    game_id=item["game_id"],
                    id_source=item["id_source"],
                    target_folder="USBExtreme",
                    destination_filename=destination_name,
                )
                imported.append(
                    {
                        "file": destination_name,
                        "source_filename": src.name,
                        "game_name": entry.name,
                        "game_id": item["game_id"],
                        "id_source": item["id_source"],
                        "target_folder": "USBExtreme",
                        "destination": str(part_files[0]),
                        "size": target_service.human_bytes(item["size"]),
                    }
                )
                report(100, "Imported")
                _emit(on_step, "success", f"imported {entry.name} in {entry.parts} FAT32-safe parts")
                continue

            destination = target / item["folder"] / item["dest_name"]
            if destination.exists() and not overwrite:
                skipped_count += 1
                report(100, "Skipped")
                _emit(on_step, "info", f"skipped duplicate: {item['dest_name']}")
                continue

            _emit(on_step, "info", f"[{idx}/{len(prepared)}] importing {src.name}")
            temporary = destination.with_name(destination.name + ".part")
            temporary.unlink(missing_ok=True)
            try:
                _copy_with_progress(src, temporary, on_step=on_step, cancel_event=cancel_event, on_progress=report)
                temporary.replace(destination)
            except OperationCancelledError:
                report(0, "Cancelled")
                temporary.unlink(missing_ok=True)
                return {
                    "status": "cancelled",
                    "message": "Import cancelled.",
                    "details": {"imported_count": len(imported), "imported": imported},
                }
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
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
            report(100, "Imported")
            _emit(on_step, "success", f"imported {item['dest_name']}")

        return {
            "status": "success",
            "message": "Import finished (existing games may have been skipped)",
            "details": {
                "target": str(target),
                "imported_count": len(imported),
                "imported": imported,
                "skipped_count": skipped_count,
                "manifest_path": str(game_service.manifest_path(target)),
            },
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Import failed")
        if "report" in locals():
            report(0, "Cancelled" if isinstance(exc, OperationCancelledError) else "Failed")
        no_space = isinstance(exc, OSError) and (getattr(exc, "errno", None) == 28 or getattr(exc, "winerror", None) == 112)
        if no_space:
            message = "The USB does not have enough usable free space. Remove a game or use a larger USB, then try again."
            message_th = "พื้นที่ว่างบน USB ไม่พอ กรุณาลบเกมที่ไม่ใช้หรือเปลี่ยน USB ที่ใหญ่ขึ้น แล้วลองอีกครั้ง"
        elif isinstance(exc, OperationCancelledError):
            return {
                "status": "cancelled",
                "message": "Import cancelled. Incomplete files were removed.",
                "message_th": "ยกเลิกการนำเข้าแล้ว และลบไฟล์ที่คัดลอกไม่เสร็จเรียบร้อย",
                "details": {"imported_count": len(imported), "imported": imported},
            }
        else:
            message = f"Could not import the game: {exc}"
            message_th = f"นำเข้าเกมไม่ได้: {exc}"
        _emit(on_step, "error", message)
        return _import_error(message, message_th, exc, imported_count=len(imported), imported=imported)
