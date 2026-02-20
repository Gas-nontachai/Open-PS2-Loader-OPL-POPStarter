from __future__ import annotations

import os
import platform
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

REQUIRED_FOLDERS = ["APPS", "ART", "CD", "CFG", "CHT", "DVD", "LNG", "POPS", "THM", "VMC"]
CD_THRESHOLD_BYTES = 700 * 1024 * 1024
SPACE_BUFFER_MIN_BYTES = 500 * 1024 * 1024
SPACE_BUFFER_RATIO = 0.05


class ValidateTargetRequest(BaseModel):
    target_path: str = Field(min_length=1)
    ensure_folders: bool = True


class FormatTargetRequest(BaseModel):
    target_path: str = Field(min_length=1)
    confirm_phrase: str = Field(min_length=1)
    volume_label: str = "PS2USB"


app = FastAPI(title="PS2 ISO Importer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _step(state: str, status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state": state,
        "status": status,
        "message": message,
    }
    if details:
        payload["details"] = details
    return payload


def _response(
    status: str,
    state: str,
    message: str,
    details: dict[str, Any] | None = None,
    next_action: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "state": state,
            "message": message,
            "details": details or {},
            "next_action": next_action,
            "steps": steps or [],
        },
    )


def _resolve_target(target_path: str) -> Path:
    return Path(target_path).expanduser().resolve()


def _validate_target_access(target: Path) -> tuple[bool, str]:
    if not target.exists():
        return False, "target path does not exist"
    if not target.is_dir():
        return False, "target path is not a directory"
    if not os.access(target, os.R_OK | os.W_OK | os.X_OK):
        return False, "target path is not writable"
    return True, "ok"


def _ensure_required_folders(target: Path) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    created: list[str] = []
    for folder in REQUIRED_FOLDERS:
        folder_path = target / folder
        if folder_path.exists() and not folder_path.is_dir():
            raise NotADirectoryError(f"required path exists but is not a directory: {folder_path}")
        if not folder_path.exists():
            missing.append(folder)
            folder_path.mkdir(parents=True, exist_ok=True)
            created.append(folder)
    return missing, created


def _compute_buffer(total_iso_bytes: int) -> int:
    return max(int(total_iso_bytes * SPACE_BUFFER_RATIO), SPACE_BUFFER_MIN_BYTES)


def _human_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{size} B"


def _sanitize_volume_label(label: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "", label).upper()
    if not sanitized:
        sanitized = "PS2USB"
    return sanitized[:11]


def _run_cmd(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, capture_output=True, text=True)


def _diskutil_info(path_or_device: str) -> dict[str, Any]:
    result = _run_cmd(["diskutil", "info", "-plist", path_or_device])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"diskutil info failed for {path_or_device}")
    return plistlib.loads(result.stdout.encode("utf-8"))


def _validate_format_target(path: Path) -> tuple[str, dict[str, Any], dict[str, Any]]:
    info = _diskutil_info(str(path))
    whole_disk = info.get("ParentWholeDisk") or info.get("DeviceIdentifier")
    if not whole_disk:
        raise RuntimeError("could not identify disk device from target path")

    whole_info = _diskutil_info(f"/dev/{whole_disk}")
    if whole_info.get("Internal", True):
        raise RuntimeError("refusing to format an internal disk")
    if not (whole_info.get("RemovableMedia", False) or info.get("RemovableMedia", False)):
        raise RuntimeError("target is not marked as removable media")

    return whole_disk, info, whole_info


def _wait_mount_point(device: str, retries: int = 12, delay_sec: float = 0.5) -> Path:
    for _ in range(retries):
        list_result = _run_cmd(["diskutil", "list", "-plist", f"/dev/{device}"])
        if list_result.returncode == 0:
            parsed = plistlib.loads(list_result.stdout.encode("utf-8"))
            partitions = parsed.get("Partitions", [])
            for partition in partitions:
                mount_point = partition.get("MountPoint")
                if mount_point:
                    return Path(mount_point)
        time.sleep(delay_sec)
    raise RuntimeError("formatted volume did not mount in time")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/pick-target-folder")
async def pick_target_folder():
    steps: list[dict[str, Any]] = []
    try:
        if platform.system().lower() != "darwin":
            return _response(
                status="error",
                state="failed",
                message="folder picker is supported only on macOS",
                details={},
                next_action="enter_path_manually",
                steps=steps,
                status_code=400,
            )

        result = _run_cmd(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Select PS2 target parent folder")',
            ]
        )
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout).strip()
            if "User canceled" in error_text:
                return _response(
                    status="error",
                    state="cancelled",
                    message="folder selection cancelled",
                    details={},
                    next_action="retry_or_enter_path_manually",
                    steps=steps,
                    status_code=400,
                )
            return _response(
                status="error",
                state="failed",
                message="failed to open folder picker",
                details={"error": error_text},
                next_action="retry_or_enter_path_manually",
                steps=steps,
                status_code=500,
            )

        selected = result.stdout.strip()
        return _response(
            status="success",
            state="completed",
            message="folder selected",
            details={"target": selected},
            next_action="ready_to_validate",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        return _response(
            status="error",
            state="failed",
            message="unexpected error during folder pick",
            details={"error": str(exc)},
            next_action="retry_or_enter_path_manually",
            steps=steps,
            status_code=500,
        )


@app.post("/api/format-target")
async def format_target(payload: FormatTargetRequest):
    steps: list[dict[str, Any]] = []
    try:
        if platform.system().lower() != "darwin":
            steps.append(_step("formatting", "error", "format endpoint currently supports macOS only"))
            return _response(
                status="error",
                state="failed",
                message="formatting is supported only on macOS",
                details={},
                next_action="use_macos_or_format_manually",
                steps=steps,
                status_code=400,
            )

        if payload.confirm_phrase.strip().upper() != "FORMAT":
            steps.append(_step("formatting", "error", "invalid confirm phrase"))
            return _response(
                status="error",
                state="failed",
                message="confirmation phrase mismatch",
                details={"expected": "FORMAT"},
                next_action="confirm_with_format_phrase",
                steps=steps,
                status_code=400,
            )

        target = _resolve_target(payload.target_path)
        steps.append(_step("formatting", "info", "resolving target path", {"target": str(target)}))
        if not target.exists():
            steps.append(_step("formatting", "error", "target path does not exist"))
            return _response(
                status="error",
                state="failed",
                message="target path does not exist",
                details={"target": str(target)},
                next_action="provide_valid_target_path",
                steps=steps,
                status_code=400,
            )

        steps.append(_step("formatting", "info", "inspecting disk metadata"))
        disk_device, volume_info, whole_info = _validate_format_target(target)
        steps.append(
            _step(
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

        label = _sanitize_volume_label(payload.volume_label)
        steps.append(
            _step(
                "formatting",
                "info",
                "erasing disk as FAT32 (MBR)",
                {"device": disk_device, "label": label},
            )
        )
        erase_result = _run_cmd(["diskutil", "eraseDisk", "MS-DOS", label, "MBRFormat", f"/dev/{disk_device}"])
        if erase_result.returncode != 0:
            steps.append(
                _step(
                    "formatting",
                    "error",
                    "diskutil erase failed",
                    {"stderr": erase_result.stderr.strip()},
                )
            )
            return _response(
                status="error",
                state="failed",
                message="format command failed",
                details={"error": erase_result.stderr.strip()},
                next_action="check_permissions_and_retry",
                steps=steps,
                status_code=500,
            )

        mounted_path = _wait_mount_point(disk_device)
        steps.append(
            _step(
                "formatting",
                "success",
                "disk formatted and mounted",
                {"mount_point": str(mounted_path), "device": disk_device, "label": label},
            )
        )

        try:
            missing, created = _ensure_required_folders(mounted_path)
        except NotADirectoryError as exc:
            steps.append(_step("ensuring_structure", "error", str(exc)))
            return _response(
                status="error",
                state="failed",
                message="formatted volume has invalid structure",
                details={"error": str(exc)},
                next_action="retry_format",
                steps=steps,
                status_code=500,
            )

        steps.append(
            _step(
                "ensuring_structure",
                "success",
                "required folders are ready after format",
                {"missing_before": missing, "created": created},
            )
        )

        return _response(
            status="success",
            state="completed",
            message="usb formatted and prepared successfully",
            details={"target": str(mounted_path), "label": label, "device": disk_device, "created": created},
            next_action="ready_to_import",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("failed", "error", "unexpected error", {"error": str(exc)}))
        return _response(
            status="error",
            state="failed",
            message="unexpected error during format",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@app.post("/api/validate-target")
async def validate_target(payload: ValidateTargetRequest):
    steps: list[dict[str, Any]] = []
    try:
        target = _resolve_target(payload.target_path)
        steps.append(_step("validating_target", "info", "checking target path", {"target": str(target)}))

        ok, reason = _validate_target_access(target)
        if not ok:
            steps.append(_step("validating_target", "error", reason))
            return _response(
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
            steps.append(_step("ensuring_structure", "info", "ensuring required folders"))
            try:
                missing, created = _ensure_required_folders(target)
            except NotADirectoryError as exc:
                steps.append(_step("ensuring_structure", "error", str(exc)))
                return _response(
                    status="error",
                    state="failed",
                    message="invalid target structure",
                    details={"error": str(exc)},
                    next_action="fix_target_structure_then_retry",
                    steps=steps,
                    status_code=400,
                )
            steps.append(
                _step(
                    "ensuring_structure",
                    "success",
                    "required folders are ready",
                    {"missing_before": missing, "created": created},
                )
            )

        existing = sorted([f for f in REQUIRED_FOLDERS if (target / f).exists()])
        steps.append(_step("validated", "success", "target is ready"))
        return _response(
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
        steps.append(_step("failed", "error", "unexpected error", {"error": str(exc)}))
        return _response(
            status="error",
            state="failed",
            message="unexpected error during validation",
            details={"error": str(exc)},
            next_action="retry",
            steps=steps,
            status_code=500,
        )


@app.post("/api/import")
async def import_iso(
    target_path: str = Form(...),
    overwrite: bool = Form(False),
    files: list[UploadFile] = File(...),
):
    steps: list[dict[str, Any]] = []
    tmp_dir: str | None = None
    prepared_files: list[dict[str, Any]] = []

    try:
        steps.append(_step("initializing", "info", "starting import job"))
        target = _resolve_target(target_path)

        steps.append(_step("validating_target", "info", "checking target path", {"target": str(target)}))
        ok, reason = _validate_target_access(target)
        if not ok:
            steps.append(_step("validating_target", "error", reason))
            return _response(
                status="error",
                state="failed",
                message="target validation failed",
                details={"target": str(target), "reason": reason},
                next_action="fix_target_path_or_permissions",
                steps=steps,
                status_code=400,
            )

        steps.append(_step("ensuring_structure", "info", "ensuring required folders"))
        try:
            missing, created = _ensure_required_folders(target)
        except NotADirectoryError as exc:
            steps.append(_step("ensuring_structure", "error", str(exc)))
            return _response(
                status="error",
                state="failed",
                message="invalid target structure",
                details={"error": str(exc)},
                next_action="fix_target_structure_then_retry",
                steps=steps,
                status_code=400,
            )
        steps.append(
            _step(
                "ensuring_structure",
                "success",
                "required folders are ready",
                {"missing_before": missing, "created": created},
            )
        )

        if not files:
            steps.append(_step("validating_files", "error", "no files uploaded"))
            return _response(
                status="error",
                state="failed",
                message="no files uploaded",
                details={},
                next_action="upload_iso_files",
                steps=steps,
                status_code=400,
            )

        steps.append(_step("validating_files", "info", "validating and staging uploads"))
        tmp_dir = tempfile.mkdtemp(prefix="ps2_iso_import_")

        for upload in files:
            original_name = Path(upload.filename or "").name
            if not original_name:
                steps.append(_step("validating_files", "error", "found file with empty filename"))
                return _response(
                    status="error",
                    state="failed",
                    message="invalid file name",
                    details={"file": upload.filename},
                    next_action="upload_valid_iso_files",
                    steps=steps,
                    status_code=400,
                )

            if Path(original_name).suffix.lower() != ".iso":
                steps.append(
                    _step("validating_files", "error", "non-iso file detected", {"file": original_name})
                )
                return _response(
                    status="error",
                    state="failed",
                    message="only .iso files are allowed",
                    details={"file": original_name},
                    next_action="remove_non_iso_files",
                    steps=steps,
                    status_code=400,
                )

            staged_path = Path(tmp_dir) / original_name
            # Handle duplicate names from upload set.
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

            file_size = staged_path.stat().st_size
            prepared_files.append(
                {
                    "name": staged_path.name,
                    "size": file_size,
                    "staged_path": staged_path,
                    "target_folder": "CD" if file_size < CD_THRESHOLD_BYTES else "DVD",
                }
            )
            await upload.close()

        total_iso_bytes = sum(f["size"] for f in prepared_files)
        if total_iso_bytes == 0:
            steps.append(_step("validating_files", "error", "uploaded files are empty"))
            return _response(
                status="error",
                state="failed",
                message="uploaded files are empty",
                details={},
                next_action="upload_valid_iso_files",
                steps=steps,
                status_code=400,
            )

        steps.append(
            _step(
                "validating_files",
                "success",
                "files staged successfully",
                {
                    "file_count": len(prepared_files),
                    "total_iso_bytes": total_iso_bytes,
                    "total_iso_human": _human_bytes(total_iso_bytes),
                },
            )
        )

        steps.append(_step("checking_space", "info", "checking available disk space"))
        usage = shutil.disk_usage(target)
        buffer_bytes = _compute_buffer(total_iso_bytes)
        required_bytes = total_iso_bytes + buffer_bytes
        free_bytes = usage.free

        if free_bytes < required_bytes:
            deficit = required_bytes - free_bytes
            steps.append(
                _step(
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
            return _response(
                status="error",
                state="failed",
                message="insufficient disk space",
                details={
                    "target": str(target),
                    "required": _human_bytes(required_bytes),
                    "free": _human_bytes(free_bytes),
                    "deficit": _human_bytes(deficit),
                    "buffer": _human_bytes(buffer_bytes),
                },
                next_action="free_up_space_then_retry",
                steps=steps,
                status_code=400,
            )

        steps.append(
            _step(
                "checking_space",
                "success",
                "disk space is sufficient",
                {
                    "required": _human_bytes(required_bytes),
                    "free": _human_bytes(free_bytes),
                    "buffer": _human_bytes(buffer_bytes),
                },
            )
        )

        steps.append(_step("importing", "info", "copying files to target"))
        imported: list[dict[str, Any]] = []

        for item in prepared_files:
            # Detect unplug/mount issues during long copy jobs.
            if not target.exists():
                steps.append(_step("importing", "error", "target path disappeared during import"))
                return _response(
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
                    _step(
                        "importing",
                        "error",
                        "destination file already exists",
                        {"file": item["name"], "destination": str(destination)},
                    )
                )
                return _response(
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
            dynamic_required = remaining_bytes + _compute_buffer(remaining_bytes)
            if usage.free < dynamic_required:
                steps.append(
                    _step(
                        "importing",
                        "error",
                        "disk space dropped during import",
                        {
                            "file": item["name"],
                            "required": _human_bytes(dynamic_required),
                            "free": _human_bytes(usage.free),
                        },
                    )
                )
                return _response(
                    status="error",
                    state="failed",
                    message="disk space dropped during import",
                    details={"file": item["name"]},
                    next_action="free_up_space_then_retry",
                    steps=steps,
                    status_code=400,
                )

            shutil.copy2(item["staged_path"], destination)
            imported.append(
                {
                    "file": item["name"],
                    "target_folder": item["target_folder"],
                    "destination": str(destination),
                    "size": _human_bytes(item["size"]),
                }
            )
            steps.append(
                _step(
                    "importing",
                    "success",
                    "file copied",
                    {"file": item["name"], "destination": str(destination)},
                )
            )

        steps.append(_step("completed", "success", "import completed"))
        return _response(
            status="success",
            state="completed",
            message="all files imported successfully",
            details={
                "target": str(target),
                "imported_count": len(imported),
                "imported": imported,
            },
            next_action="done",
            steps=steps,
        )
    except Exception as exc:  # noqa: BLE001
        steps.append(_step("failed", "error", "unexpected error", {"error": str(exc)}))
        return _response(
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
