from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates

from app.core.constants import ART_ALLOWED_EXT, ART_TYPES, CD_THRESHOLD_BYTES, REQUIRED_FOLDERS
from app.core.http import api_response, step
from app.core.schemas import ArtSaveRequest, ArtSearchRequest, FormatTargetRequest, ValidateTargetRequest
from app.services.art_service import (
    art_search_cache_key,
    download_image,
    enforce_art_search_rate_limit,
    get_cached_art_search,
    search_art_candidates,
    store_cached_art_search,
)
from app.services.format_service import is_macos, run_cmd, sanitize_volume_label, validate_format_target, wait_mount_point
from app.services.game_service import (
    derive_game_name,
    extract_game_id_from_iso,
    manifest_path,
    resolve_game_id,
    resolve_game_id_for_target,
    upsert_manifest_entry,
)
from app.services.target_service import compute_buffer, ensure_required_folders, human_bytes, resolve_target, validate_target_access

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/pick-target-folder")
async def pick_target_folder():
    steps: list[dict[str, Any]] = []
    try:
        if not is_macos():
            return api_response(
                status="error",
                state="failed",
                message="folder picker is supported only on macOS",
                details={},
                next_action="enter_path_manually",
                steps=steps,
                status_code=400,
            )

        result = run_cmd(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Select PS2 target parent folder")',
            ]
        )
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout).strip()
            if "User canceled" in error_text:
                return api_response(
                    status="error",
                    state="cancelled",
                    message="folder selection cancelled",
                    details={},
                    next_action="retry_or_enter_path_manually",
                    steps=steps,
                    status_code=400,
                )
            return api_response(
                status="error",
                state="failed",
                message="failed to open folder picker",
                details={"error": error_text},
                next_action="retry_or_enter_path_manually",
                steps=steps,
                status_code=500,
            )

        selected = result.stdout.strip()
        return api_response(
            status="success",
            state="completed",
            message="folder selected",
            details={"target": selected},
            next_action="ready_to_validate",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        return api_response(
            status="error",
            state="failed",
            message="unexpected error during folder pick",
            details={"error": str(exc)},
            next_action="retry_or_enter_path_manually",
            steps=steps,
            status_code=500,
        )


@router.post("/api/format-target")
async def format_target(payload: FormatTargetRequest):
    steps: list[dict[str, Any]] = []
    try:
        if not is_macos():
            steps.append(step("formatting", "error", "format endpoint currently supports macOS only"))
            return api_response(
                status="error",
                state="failed",
                message="formatting is supported only on macOS",
                details={},
                next_action="use_macos_or_format_manually",
                steps=steps,
                status_code=400,
            )

        if payload.confirm_phrase.strip().upper() != "FORMAT":
            steps.append(step("formatting", "error", "invalid confirm phrase"))
            return api_response(
                status="error",
                state="failed",
                message="confirmation phrase mismatch",
                details={"expected": "FORMAT"},
                next_action="confirm_with_format_phrase",
                steps=steps,
                status_code=400,
            )

        target = resolve_target(payload.target_path)
        steps.append(step("formatting", "info", "resolving target path", {"target": str(target)}))
        if not target.exists():
            steps.append(step("formatting", "error", "target path does not exist"))
            return api_response(
                status="error",
                state="failed",
                message="target path does not exist",
                details={"target": str(target)},
                next_action="provide_valid_target_path",
                steps=steps,
                status_code=400,
            )

        steps.append(step("formatting", "info", "inspecting disk metadata"))
        disk_device, volume_info, whole_info = validate_format_target(target)
        steps.append(
            step(
                "formatting",
                "info",
                "target disk validated",
                {
                    "device": disk_device,
                    "volume_name": volume_info.get("VolumeName"),
                    "bus_protocol": whole_info.get("BusProtocol"),
                },
            )
        )

        label = sanitize_volume_label(payload.volume_label)
        steps.append(
            step(
                "formatting",
                "info",
                "erasing disk as FAT32 (MBR)",
                {"device": disk_device, "label": label},
            )
        )
        erase_result = run_cmd(["diskutil", "eraseDisk", "MS-DOS", label, "MBRFormat", f"/dev/{disk_device}"])
        if erase_result.returncode != 0:
            steps.append(
                step(
                    "formatting",
                    "error",
                    "diskutil erase failed",
                    {"stderr": erase_result.stderr.strip()},
                )
            )
            return api_response(
                status="error",
                state="failed",
                message="format command failed",
                details={"error": erase_result.stderr.strip()},
                next_action="check_permissions_and_retry",
                steps=steps,
                status_code=500,
            )

        mounted_path = wait_mount_point(disk_device)
        steps.append(
            step(
                "formatting",
                "success",
                "disk formatted and mounted",
                {"mount_point": str(mounted_path), "device": disk_device, "label": label},
            )
        )

        try:
            missing, created = ensure_required_folders(mounted_path)
        except NotADirectoryError as exc:
            steps.append(step("ensuring_structure", "error", str(exc)))
            return api_response(
                status="error",
                state="failed",
                message="formatted volume has invalid structure",
                details={"error": str(exc)},
                next_action="retry_format",
                steps=steps,
                status_code=500,
            )

        steps.append(
            step(
                "ensuring_structure",
                "success",
                "required folders are ready after format",
                {"missing_before": missing, "created": created},
            )
        )

        return api_response(
            status="success",
            state="completed",
            message="usb formatted and prepared successfully",
            details={"target": str(mounted_path), "label": label, "device": disk_device, "created": created},
            next_action="ready_to_import",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(step("failed", "error", "unexpected error", {"error": str(exc)}))
        return api_response(
            status="error",
            state="failed",
            message="unexpected error during format",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@router.post("/api/validate-target")
async def validate_target(payload: ValidateTargetRequest):
    steps: list[dict[str, Any]] = []
    try:
        target = resolve_target(payload.target_path)
        steps.append(step("validating_target", "info", "checking target path", {"target": str(target)}))

        ok, reason = validate_target_access(target)
        if not ok:
            steps.append(step("validating_target", "error", reason))
            return api_response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )

        missing: list[str] = []
        created: list[str] = []
        if payload.ensure_folders:
            steps.append(step("ensuring_structure", "info", "ensuring required folders"))
            try:
                missing, created = ensure_required_folders(target)
            except NotADirectoryError as exc:
                steps.append(step("ensuring_structure", "error", str(exc)))
                return api_response(
                    status="error",
                    state="failed",
                    message="invalid target structure",
                    details={"error": str(exc)},
                    next_action="fix_target_structure_then_retry",
                    steps=steps,
                    status_code=400,
                )
            steps.append(
                step(
                    "ensuring_structure",
                    "success",
                    "required folders are ready",
                    {"missing_before": missing, "created": created},
                )
            )

        existing = sorted([f for f in REQUIRED_FOLDERS if (target / f).exists()])
        steps.append(step("validated", "success", "target is ready"))
        return api_response(
            status="success",
            state="validated",
            message="target path is valid and ready",
            details={
                "target": str(target),
                "required_folders": REQUIRED_FOLDERS,
                "existing": existing,
                "created": created,
            },
            next_action="ready_to_import",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(step("failed", "error", "unexpected error", {"error": str(exc)}))
        return api_response(
            status="error",
            state="failed",
            message="unexpected error during validation",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@router.post("/api/art/search")
async def search_art(payload: ArtSearchRequest, request: Request):
    steps: list[dict[str, Any]] = []
    try:
        game_query = derive_game_name(payload.game_name, payload.source_filename)
        target: Optional[Path] = None
        if payload.target_path and payload.target_path.strip():
            target = resolve_target(payload.target_path)
        game_id, generated, id_source = resolve_game_id_for_target(target, game_query, payload.source_filename)
        query = f"{game_query} PS2 cover art"
        now_ts = time.time()
        provider_name = "rawg"
        cache_key = art_search_cache_key(provider_name, game_id, query, payload.max_results)
        cached = get_cached_art_search(cache_key, now_ts)
        if cached is not None:
            steps.append(
                step(
                    "searching_art",
                    "success",
                    "loaded art candidates from cache",
                    {"count": len(cached), "provider": provider_name},
                )
            )
            return api_response(
                status="success",
                state="searching_art",
                message="art candidates ready for preview",
                details={
                    "game_id": game_id,
                    "generated_game_id": generated,
                    "id_source": id_source,
                    "game_query": game_query,
                    "art_types": ART_TYPES,
                    "candidates": cached,
                    "cache_hit": True,
                    "provider_used": provider_name,
                },
                next_action="preview_and_select_images",
                steps=steps,
            )

        client_id = request.client.host if request.client else "unknown"
        allowed, reason, retry_after = enforce_art_search_rate_limit(client_id, now_ts)
        if not allowed:
            return api_response(
                status="error",
                state="failed",
                message=reason,
                details={"retry_after_seconds": retry_after},
                next_action="wait_then_retry",
                steps=steps,
                status_code=429,
            )

        steps.append(step("searching_art", "info", "searching images", {"query": query, "provider": provider_name}))
        provider_used, candidates = search_art_candidates(query, payload.max_results)
        if not candidates:
            steps.append(step("searching_art", "error", "no image candidates found"))
            return api_response(
                status="error",
                state="failed",
                message="no art candidates found",
                details={"query": query},
                next_action="try_another_game_name",
                steps=steps,
                status_code=404,
            )

        cache_key = art_search_cache_key(provider_used, game_id, query, payload.max_results)
        store_cached_art_search(cache_key, candidates, now_ts)
        steps.append(step("searching_art", "success", "art candidates found", {"count": len(candidates)}))
        return api_response(
            status="success",
            state="searching_art",
            message="art candidates ready for preview",
            details={
                "game_id": game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "game_query": game_query,
                "art_types": ART_TYPES,
                "candidates": candidates,
                "cache_hit": False,
                "provider_used": provider_used,
            },
            next_action="preview_and_select_images",
            steps=steps,
        )
    except ValueError as exc:
        return api_response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="fix_request_and_retry",
            steps=steps,
            status_code=400,
        )
    except RuntimeError as exc:
        return api_response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="set_rawg_api_key_then_retry",
            steps=steps,
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(step("failed", "error", "unexpected error", {"error": str(exc)}))
        return api_response(
            status="error",
            state="failed",
            message="unexpected error during art search",
            details={"error": str(exc)},
            next_action="check_api_config_or_retry",
            steps=steps,
            status_code=500,
        )


@router.post("/api/art/manual")
async def upload_art_manual(
    target_path: str = Form(...),
    game_name: str = Form(""),
    source_filename: str = Form(""),
    cov: Optional[UploadFile] = File(None),
    cov2: Optional[UploadFile] = File(None),
    bg: Optional[UploadFile] = File(None),
    scr: Optional[UploadFile] = File(None),
    scr2: Optional[UploadFile] = File(None),
    lgo: Optional[UploadFile] = File(None),
    ico: Optional[UploadFile] = File(None),
    lab: Optional[UploadFile] = File(None),
):
    steps: list[dict[str, Any]] = []
    try:
        target = resolve_target(target_path)
        normalized_game_id, generated, id_source = resolve_game_id_for_target(target, game_name.strip(), source_filename.strip())
        ok, reason = validate_target_access(target)
        if not ok:
            return api_response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )

        ensure_required_folders(target)
        art_dir = target / "ART"

        uploads = {
            "COV": cov,
            "COV2": cov2,
            "BG": bg,
            "SCR": scr,
            "SCR2": scr2,
            "LGO": lgo,
            "ICO": ico,
            "LAB": lab,
        }

        saved: list[dict[str, str]] = []
        for art_type, upload in uploads.items():
            if not upload or not upload.filename:
                continue
            src_ext = Path(upload.filename).suffix.lower()
            if src_ext not in ART_ALLOWED_EXT:
                return api_response(
                    status="error",
                    state="failed",
                    message=f"unsupported extension for {art_type}",
                    details={"file": upload.filename, "allowed": sorted(ART_ALLOWED_EXT)},
                    next_action="upload_png_or_jpg",
                    steps=steps,
                    status_code=400,
                )

            dst_ext = ".jpg" if src_ext == ".jpeg" else src_ext
            dst = art_dir / f"{normalized_game_id}_{art_type}{dst_ext}"
            with dst.open("wb") as fh:
                shutil.copyfileobj(upload.file, fh)
            await upload.close()
            saved.append({"art_type": art_type, "path": str(dst)})

        if not saved:
            return api_response(
                status="error",
                state="failed",
                message="no art files provided",
                details={},
                next_action="upload_at_least_one_art_file",
                steps=steps,
                status_code=400,
            )

        return api_response(
            status="success",
            state="completed",
            message="manual art upload completed",
            details={
                "game_id": normalized_game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "saved": saved,
            },
            next_action="done",
            steps=steps,
        )
    except ValueError as exc:
        return api_response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="fix_request_and_retry",
            steps=steps,
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        return api_response(
            status="error",
            state="failed",
            message="unexpected error during manual art upload",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@router.post("/api/art/save-auto")
async def save_art_auto(payload: ArtSaveRequest):
    steps: list[dict[str, Any]] = []
    try:
        target = resolve_target(payload.target_path)
        game_id, generated, id_source = resolve_game_id_for_target(
            target,
            (payload.game_name or "").strip(),
            (payload.source_filename or "").strip(),
        )
        if not payload.selections:
            return api_response(
                status="error",
                state="failed",
                message="no selected images",
                details={},
                next_action="select_images_from_preview",
                steps=steps,
                status_code=400,
            )

        ok, reason = validate_target_access(target)
        if not ok:
            return api_response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )
        ensure_required_folders(target)
        art_dir = target / "ART"

        seen_types: set[str] = set()
        skipped_duplicates: list[dict[str, Any]] = []
        unique_selections = []
        for idx, selection in enumerate(payload.selections, start=1):
            art_type = selection.art_type.strip().upper()
            if art_type not in ART_TYPES:
                return api_response(
                    status="error",
                    state="failed",
                    message=f"invalid art type: {art_type}",
                    details={"valid_types": ART_TYPES},
                    next_action="choose_valid_art_type",
                    steps=steps,
                    status_code=400,
                )
            if art_type in seen_types:
                skipped_duplicates.append({"art_type": art_type, "position": idx})
                continue
            seen_types.add(art_type)
            unique_selections.append(selection)

        if not unique_selections:
            return api_response(
                status="error",
                state="failed",
                message="no unique art type selected",
                details={"valid_types": ART_TYPES},
                next_action="select_at_least_one_unique_art_type",
                steps=steps,
                status_code=400,
            )

        saved: list[dict[str, str]] = []
        for selection in unique_selections:
            art_type = selection.art_type.strip().upper()
            content, ext = download_image(selection.image_url.strip(), art_type)
            destination = art_dir / f"{game_id}_{art_type}{ext}"
            with destination.open("wb") as fh:
                fh.write(content)
            saved.append({"art_type": art_type, "path": str(destination)})

        return api_response(
            status="success",
            state="completed",
            message="selected auto art saved",
            details={
                "game_id": game_id,
                "generated_game_id": generated,
                "id_source": id_source,
                "saved": saved,
                "skipped_duplicates": skipped_duplicates,
            },
            next_action="done",
            steps=steps,
        )
    except ValueError as exc:
        return api_response(
            status="error",
            state="failed",
            message=str(exc),
            details={},
            next_action="fix_request_and_retry",
            steps=steps,
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001
        return api_response(
            status="error",
            state="failed",
            message="unexpected error during auto art save",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@router.post("/api/import")
async def import_iso(
    target_path: str = Form(...),
    overwrite: bool = Form(False),
    files: list[UploadFile] = File(...),
):
    steps: list[dict[str, Any]] = []
    tmp_dir: Optional[str] = None
    prepared_files: list[dict[str, Any]] = []

    try:
        steps.append(step("initializing", "info", "starting import job"))
        target = resolve_target(target_path)

        steps.append(step("validating_target", "info", "checking target path", {"target": str(target)}))
        ok, reason = validate_target_access(target)
        if not ok:
            steps.append(step("validating_target", "error", reason))
            return api_response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )

        steps.append(step("ensuring_structure", "info", "ensuring required folders"))
        try:
            missing, created = ensure_required_folders(target)
        except NotADirectoryError as exc:
            steps.append(step("ensuring_structure", "error", str(exc)))
            return api_response(
                status="error",
                state="failed",
                message="invalid target structure",
                details={"error": str(exc)},
                next_action="fix_target_structure_then_retry",
                steps=steps,
                status_code=400,
            )
        steps.append(
            step(
                "ensuring_structure",
                "success",
                "required folders are ready",
                {"missing_before": missing, "created": created},
            )
        )

        if not files:
            steps.append(step("validating_files", "error", "no files uploaded"))
            return api_response(
                status="error",
                state="failed",
                message="no files uploaded",
                details={},
                next_action="upload_iso_files",
                steps=steps,
                status_code=400,
            )

        steps.append(step("validating_files", "info", "validating and staging uploads"))
        tmp_dir = tempfile.mkdtemp(prefix="ps2_iso_import_")

        for upload in files:
            original_name = Path(upload.filename or "").name
            if not original_name:
                steps.append(step("validating_files", "error", "found file with empty filename"))
                return api_response(
                    status="error",
                    state="failed",
                    message="invalid file name",
                    details={"file": upload.filename},
                    next_action="upload_valid_iso_files",
                    steps=steps,
                    status_code=400,
                )

            if Path(original_name).suffix.lower() != ".iso":
                steps.append(step("validating_files", "error", "non-iso file detected", {"file": original_name}))
                return api_response(
                    status="error",
                    state="failed",
                    message="only .iso files are allowed",
                    details={"file": original_name},
                    next_action="remove_non_iso_files",
                    steps=steps,
                    status_code=400,
                )

            staged_path = Path(tmp_dir) / original_name
            if staged_path.exists():
                base = staged_path.stem
                suffix = staged_path.suffix
                counter = 1
                while True:
                    candidate = Path(tmp_dir) / f"{base}_{counter}{suffix}"
                    if not candidate.exists():
                        staged_path = candidate
                        break
                    counter += 1

            with staged_path.open("wb") as temp_file:
                shutil.copyfileobj(upload.file, temp_file)

            try:
                inferred_game_name = derive_game_name(None, original_name)
            except ValueError:
                inferred_game_name = Path(original_name).stem
            iso_game_id = extract_game_id_from_iso(staged_path)
            if iso_game_id:
                resolved_game_id = iso_game_id
                id_source = "iso"
            else:
                resolved_game_id, _ = resolve_game_id(None, inferred_game_name)
                id_source = "generated"

            normalized_original_name = original_name
            if not normalized_original_name.upper().startswith(f"{resolved_game_id}_"):
                normalized_original_name = f"{resolved_game_id}_{original_name}"

            file_size = staged_path.stat().st_size
            prepared_files.append(
                {
                    "name": normalized_original_name,
                    "source_filename": original_name,
                    "game_name": inferred_game_name,
                    "game_id": resolved_game_id,
                    "id_source": id_source,
                    "size": file_size,
                    "staged_path": staged_path,
                    "target_folder": "CD" if file_size < CD_THRESHOLD_BYTES else "DVD",
                }
            )
            await upload.close()

        total_iso_bytes = sum(f["size"] for f in prepared_files)
        if total_iso_bytes == 0:
            steps.append(step("validating_files", "error", "uploaded files are empty"))
            return api_response(
                status="error",
                state="failed",
                message="uploaded files are empty",
                details={},
                next_action="upload_valid_iso_files",
                steps=steps,
                status_code=400,
            )

        steps.append(
            step(
                "validating_files",
                "success",
                "files staged successfully",
                {
                    "file_count": len(prepared_files),
                    "total_iso_bytes": total_iso_bytes,
                    "total_iso_human": human_bytes(total_iso_bytes),
                },
            )
        )

        steps.append(step("checking_space", "info", "checking available disk space"))
        usage = shutil.disk_usage(target)
        buffer_bytes = compute_buffer(total_iso_bytes)
        required_bytes = total_iso_bytes + buffer_bytes
        free_bytes = usage.free

        if free_bytes < required_bytes:
            deficit = required_bytes - free_bytes
            steps.append(
                step(
                    "checking_space",
                    "error",
                    "not enough free space",
                    {
                        "required_bytes": required_bytes,
                        "free_bytes": free_bytes,
                        "deficit_bytes": deficit,
                    },
                )
            )
            return api_response(
                status="error",
                state="failed",
                message="insufficient disk space",
                details={
                    "target": str(target),
                    "required": human_bytes(required_bytes),
                    "free": human_bytes(free_bytes),
                    "deficit": human_bytes(deficit),
                    "buffer": human_bytes(buffer_bytes),
                },
                next_action="free_up_space_then_retry",
                steps=steps,
                status_code=400,
            )

        steps.append(
            step(
                "checking_space",
                "success",
                "disk space is sufficient",
                {
                    "required": human_bytes(required_bytes),
                    "free": human_bytes(free_bytes),
                    "buffer": human_bytes(buffer_bytes),
                },
            )
        )

        steps.append(step("importing", "info", "copying files to target"))
        imported: list[dict[str, Any]] = []

        for item in prepared_files:
            if not target.exists():
                steps.append(step("importing", "error", "target path disappeared during import"))
                return api_response(
                    status="error",
                    state="failed",
                    message="target path disappeared during import",
                    details={"target": str(target)},
                    next_action="reconnect_target_and_retry",
                    steps=steps,
                    status_code=400,
                )

            destination = target / item["target_folder"] / item["name"]
            if destination.exists() and not overwrite:
                steps.append(
                    step(
                        "importing",
                        "error",
                        "destination file already exists",
                        {"file": item["name"], "destination": str(destination)},
                    )
                )
                return api_response(
                    status="error",
                    state="failed",
                    message="destination file already exists",
                    details={"file": item["name"], "destination": str(destination), "overwrite": False},
                    next_action="enable_overwrite_or_rename_file",
                    steps=steps,
                    status_code=409,
                )

            remaining_bytes = sum(f["size"] for f in prepared_files if f["name"] not in {i["name"] for i in imported})
            usage = shutil.disk_usage(target)
            dynamic_required = remaining_bytes + compute_buffer(remaining_bytes)
            if usage.free < dynamic_required:
                steps.append(
                    step(
                        "importing",
                        "error",
                        "disk space dropped during import",
                        {
                            "file": item["name"],
                            "required": human_bytes(dynamic_required),
                            "free": human_bytes(usage.free),
                        },
                    )
                )
                return api_response(
                    status="error",
                    state="failed",
                    message="disk space dropped during import",
                    details={"file": item["name"]},
                    next_action="free_up_space_then_retry",
                    steps=steps,
                    status_code=400,
                )

            shutil.copy2(item["staged_path"], destination)
            upsert_manifest_entry(
                target=target,
                source_filename=item["source_filename"],
                game_name=item["game_name"],
                game_id=item["game_id"],
                id_source=item["id_source"],
                target_folder=item["target_folder"],
                destination_filename=item["name"],
            )
            imported.append(
                {
                    "file": item["name"],
                    "source_filename": item["source_filename"],
                    "game_name": item["game_name"],
                    "game_id": item["game_id"],
                    "id_source": item["id_source"],
                    "target_folder": item["target_folder"],
                    "destination": str(destination),
                    "size": human_bytes(item["size"]),
                }
            )
            steps.append(step("importing", "success", "file copied", {"file": item["name"], "destination": str(destination)}))

        steps.append(step("completed", "success", "import completed"))
        return api_response(
            status="success",
            state="completed",
            message="all files imported successfully",
            details={
                "target": str(target),
                "imported_count": len(imported),
                "imported": imported,
                "manifest_path": str(manifest_path(target)),
            },
            next_action="done",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(step("failed", "error", "unexpected error", {"error": str(exc)}))
        return api_response(
            status="error",
            state="failed",
            message="unexpected error during import",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )
    finally:
        if tmp_dir and Path(tmp_dir).exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
